"""
Shared utilities for the GitHub Mining pipeline.
Used by search.py, code_analysis.py, non_code_analysis.py, analysis.py, report.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any

import requests

from config import (
    GITHUB_TOKEN, GITHUB_API_BASE, GITHUB_GRAPHQL_URL,
    RATE_LIMIT_PAUSE, CODE_SEARCH_PAUSE, GRAPHQL_PAUSE,
    RETRY_ATTEMPTS, RETRY_BACKOFF_BASE, RETRY_BACKOFF_JITTER,
    MAX_PATH_LENGTH, RESULTS_DIR, INPUTS_DIR,
    TECHNIQUE_SLUGS, TECHNIQUE_DISPLAY_NAMES, TECHNIQUE_INPUT_PREFIXES,
)


# ---------------------------------------------------------------------------
# Technique resolution
# ---------------------------------------------------------------------------

def resolve_technique(name: str) -> str:
    """Map a technique alias (mt, fuzz, pbt, or full slug) to its canonical slug."""
    slug = TECHNIQUE_SLUGS.get(name.lower().replace("-", "_"))
    if slug is None:
        raise ValueError(
            f"Unknown technique {name!r}. Valid: "
            + ", ".join(sorted(set(TECHNIQUE_SLUGS.values())))
        )
    return slug


def technique_dirs(slug: str) -> dict[str, Path]:
    base = RESULTS_DIR / slug
    return {
        "base":     base,
        "search":   base / "search",
        "cloned":   base / "cloned",
        "analysis": base / "analysis",
        "report":   base / "report",
        "plots":    base / "report" / "plots",
    }


def ensure_dirs(slug: str) -> None:
    for d in technique_dirs(slug).values():
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(slug: str, phase: str) -> logging.Logger:
    """Create a logger that writes to results/<slug>/<phase>.log."""
    log_dir = RESULTS_DIR / slug
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{phase}.log"

    name = f"{slug}.{phase}"
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_path.resolve())
               for h in logger.handlers):
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))
        logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def load_json(path: Path, default: Any = None) -> Any:
    """Load JSON from path; return default if file missing or corrupt."""
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data: Any) -> None:
    """Atomically write JSON (via temp file rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    tmp.replace(path)


def append_to_json_list(path: Path, record: dict) -> None:
    """Append a record to a JSON file containing a list."""
    existing = load_json(path, [])
    if not isinstance(existing, list):
        existing = []
    existing.append(record)
    save_json(path, existing)


# ---------------------------------------------------------------------------
# GitHub API — REST
# ---------------------------------------------------------------------------

def _gh_headers(accept: str = "application/vnd.github+json") -> dict:
    h = {
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def gh_get(
    url: str,
    params: dict | None = None,
    delay: float | None = None,
    is_code_search: bool = False,
    logger: logging.Logger | None = None,
) -> dict:
    """
    GET with exponential backoff on rate-limit (403/429) and transient errors.
    Respects X-RateLimit-Remaining / X-RateLimit-Reset headers.
    """
    if delay is None:
        delay = CODE_SEARCH_PAUSE if is_code_search else RATE_LIMIT_PAUSE
    time.sleep(delay)

    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.get(
                url, headers=_gh_headers(), params=params, timeout=30
            )
        except requests.exceptions.RequestException as exc:
            wait = RETRY_BACKOFF_BASE ** (attempt + 1) + random.uniform(0, RETRY_BACKOFF_JITTER)
            _log(logger, "warning",
                 f"Request error ({exc.__class__.__name__}) — sleeping {wait:.1f}s (attempt {attempt+1})")
            time.sleep(wait)
            continue

        if resp.status_code == 200:
            _check_remaining(resp.headers, logger)
            return resp.json()

        if resp.status_code in (403, 429):
            reset_ts = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset_ts - time.time(), 5) + random.uniform(0, RETRY_BACKOFF_JITTER)
            _log(logger, "warning",
                 f"Rate limited (HTTP {resp.status_code}) — sleeping {wait:.0f}s")
            time.sleep(wait)
            continue

        if resp.status_code in (500, 502, 503, 504):
            wait = RETRY_BACKOFF_BASE ** (attempt + 1) + random.uniform(0, RETRY_BACKOFF_JITTER)
            _log(logger, "warning",
                 f"Server error {resp.status_code} — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        resp.raise_for_status()

    raise RuntimeError(f"gh_get failed after {RETRY_ATTEMPTS} attempts: GET {url}")


def gh_graphql(
    query: str,
    variables: dict | None = None,
    logger: logging.Logger | None = None,
) -> dict:
    """POST to GitHub GraphQL API with retry."""
    time.sleep(GRAPHQL_PAUSE)
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.post(
                GITHUB_GRAPHQL_URL,
                headers=_gh_headers("application/json"),
                json=payload,
                timeout=30,
            )
        except requests.exceptions.RequestException as exc:
            wait = RETRY_BACKOFF_BASE ** (attempt + 1) + random.uniform(0, RETRY_BACKOFF_JITTER)
            _log(logger, "warning", f"GraphQL request error — sleeping {wait:.1f}s")
            time.sleep(wait)
            continue

        if resp.status_code == 200:
            return resp.json()

        wait = RETRY_BACKOFF_BASE ** (attempt + 1) + random.uniform(0, RETRY_BACKOFF_JITTER)
        _log(logger, "warning", f"GraphQL HTTP {resp.status_code} — sleeping {wait:.1f}s")
        time.sleep(wait)

    raise RuntimeError(f"gh_graphql failed after {RETRY_ATTEMPTS} attempts")


def _check_remaining(headers: dict, logger: logging.Logger | None) -> None:
    remaining = headers.get("X-RateLimit-Remaining")
    if remaining is not None and int(remaining) < 5:
        reset_ts = int(headers.get("X-RateLimit-Reset", time.time() + 60))
        wait = max(reset_ts - time.time(), 1)
        _log(logger, "warning", f"Rate limit nearly exhausted — sleeping {wait:.0f}s")
        time.sleep(wait)


def _log(logger: logging.Logger | None, level: str, msg: str) -> None:
    if logger:
        getattr(logger, level)(msg)


# ---------------------------------------------------------------------------
# Path helpers (Windows MAX_PATH workaround)
# ---------------------------------------------------------------------------

def safe_clone_path(base: Path, repo_full_name: str) -> Path:
    """Return a safe local path for a cloned repo, hashing if too long."""
    owner, name = repo_full_name.split("/", 1)
    candidate = base / owner / name
    if len(str(candidate)) > MAX_PATH_LENGTH:
        hashed = hashlib.md5(repo_full_name.encode()).hexdigest()[:16]
        candidate = base / hashed
    return candidate


def safe_file_path(base: Path, relative: str) -> Path:
    """Return a safe path for a file, truncating the filename hash if too long."""
    full = base / relative
    if len(str(full)) <= MAX_PATH_LENGTH:
        return full
    suffix = Path(relative).suffix
    stem = hashlib.md5(relative.encode()).hexdigest()[:16]
    return base / (stem + suffix)


# ---------------------------------------------------------------------------
# Keyword file loading
# ---------------------------------------------------------------------------

def load_search_keywords(slug: str) -> list[str]:
    """Load search keyword file; each line is a raw GitHub API query string."""
    prefix = TECHNIQUE_INPUT_PREFIXES[slug]
    path = INPUTS_DIR / f"{prefix}_search_keywords.txt"
    if not path.exists():
        raise FileNotFoundError(f"Search keyword file not found: {path}")
    keywords = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keywords.append(line)
    return keywords


def load_analysis_keywords(slug: str) -> list[dict]:
    """Load and return raw analysis keyword entries (not compiled)."""
    prefix = TECHNIQUE_INPUT_PREFIXES[slug]
    path = INPUTS_DIR / f"{prefix}_analysis_keywords.json"
    if not path.exists():
        raise FileNotFoundError(f"Analysis keyword file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compile_analysis_keywords(keywords: list[dict]) -> list[dict]:
    """Add a compiled `re` object to each keyword entry."""
    result = []
    for kw in keywords:
        entry = dict(kw)
        flags = 0
        for flag_name in re.split(r"[|,\s]+", kw.get("flags", "")):
            flag_name = flag_name.strip().upper()
            if flag_name == "IGNORECASE":
                flags |= re.IGNORECASE
            elif flag_name == "MULTILINE":
                flags |= re.MULTILINE
        try:
            entry["compiled"] = re.compile(kw["regex"], flags)
        except re.error as exc:
            raise ValueError(f"Invalid regex for keyword {kw['id']!r}: {exc}") from exc
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def descriptive_stats(values: list[float]) -> dict:
    """Return avg/median/max/min/range for a list of numbers."""
    if not values:
        return {"avg": 0, "median": 0, "max": 0, "min": 0, "range": 0, "count": 0}
    sorted_v = sorted(values)
    n = len(sorted_v)
    mid = n // 2
    median = sorted_v[mid] if n % 2 else (sorted_v[mid - 1] + sorted_v[mid]) / 2
    return {
        "avg":    round(sum(values) / n, 2),
        "median": round(median, 2),
        "max":    round(max(values), 2),
        "min":    round(min(values), 2),
        "range":  round(max(values) - min(values), 2),
        "count":  n,
    }
