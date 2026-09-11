"""
Code Analysis Phase
===================
Clones repos from the Code search surface in batches, scans each file with
analysis keywords, commits full git history via PyDriller, classifies repos,
then deletes clones before the next batch.

Output:
  results/<slug>/analysis/code_repos.json   — per-repo results (appended as completed)
  results/<slug>/analysis/code_history.json — tracks cloned/analysed repos (resume)
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from tqdm import tqdm

import config as cfg
from utils import (
    resolve_technique, technique_dirs, ensure_dirs,
    setup_logging, load_json, save_json,
    safe_clone_path, load_analysis_keywords, compile_analysis_keywords,
)

try:
    from pydriller import Repository
    _PYDRILLER = True
except ImportError:
    _PYDRILLER = False

try:
    import git as gitpython
    _GITPYTHON = True
except ImportError:
    _GITPYTHON = False


# ---------------------------------------------------------------------------
# Language detection (extension-based)
# ---------------------------------------------------------------------------

_EXT_LANG: dict[str, str] = {
    ".py": "Python", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".scala": "Scala", ".clj": "Clojure", ".cljs": "Clojure",
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cxx": "C++", ".cc": "C++", ".hpp": "C++",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".php": "PHP", ".swift": "Swift", ".dart": "Dart",
    ".hs": "Haskell", ".ml": "OCaml", ".mli": "OCaml",
    ".fs": "F#", ".fsx": "F#", ".erl": "Erlang", ".ex": "Elixir", ".exs": "Elixir",
    ".r": "R", ".jl": "Julia", ".lua": "Lua",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".ps1": "PowerShell",
}

def detect_language(path: Path) -> str | None:
    return _EXT_LANG.get(path.suffix.lower())


# ---------------------------------------------------------------------------
# File category classification
# ---------------------------------------------------------------------------

def classify_file(
    path: Path,
    content: str,
    tfd_keywords: list[dict],
    detected_language: str | None,
) -> str:
    """
    Returns: test_code | source_code | docs | config | other
    test_file_detection takes precedence; then extension-based.
    No directory name checks.
    """
    fname = path.name
    for kw in tfd_keywords:
        pat: re.Pattern = kw["compiled"]
        apply_to = kw.get("apply_to", "filename")
        lang_guard = kw.get("language")

        if lang_guard and detected_language != lang_guard:
            continue

        if apply_to == "filename":
            if pat.search(fname):
                return "test_code"
        else:  # content
            if pat.search(content):
                return "test_code"

    ext = path.suffix.lower()
    if ext in cfg.CODE_EXTENSIONS:
        return "source_code"
    if ext in cfg.DOC_EXTENSIONS:
        return "docs"
    if ext in cfg.CONFIG_EXTENSIONS:
        return "config"
    return "other"


# ---------------------------------------------------------------------------
# Worker-process: scan one file
# ---------------------------------------------------------------------------

_W_KWS: list[dict] = []       # compiled keyword list (set in worker init)

def _worker_init(keywords_raw: list[dict]) -> None:
    global _W_KWS
    _W_KWS = compile_analysis_keywords(keywords_raw)


def _scan_file(args: tuple) -> dict | None:
    """
    args: (file_path_str, repo_root_str, detected_language_or_None)
    Returns a per-file result dict or None if the file should be skipped.
    """
    file_path_str, repo_root_str, detected_language = args
    path = Path(file_path_str)
    repo_root = Path(repo_root_str)

    ext = path.suffix.lower()
    if ext in cfg.IGNORED_EXTENSIONS:
        return None

    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0 or size > cfg.MAX_FILE_SIZE_BYTES:
        return None

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    lines = content.splitlines()
    n_lines = len(lines)

    tfd_kws = [k for k in _W_KWS if k["category"] == "test_file_detection"]
    category = classify_file(path, content, tfd_kws, detected_language)

    general_hits: dict[str, int] = defaultdict(int)
    specific_hits: dict[str, int] = defaultdict(int)
    hit_lines: set[int] = set()

    for lineno, line in enumerate(lines, 1):
        for kw in _W_KWS:
            if kw["category"] == "test_file_detection":
                continue
            if kw["compiled"].search(line):
                if kw["category"] == "general_test":
                    general_hits[kw["id"]] += 1
                else:
                    specific_hits[kw["id"]] += 1
                hit_lines.add(lineno)

    rel_path = str(path.relative_to(repo_root))
    return {
        "rel_path":       rel_path,
        "category":       category,
        "language":       detected_language,
        "n_lines":        n_lines,
        "n_hit_lines":    len(hit_lines),
        "general_hits":   dict(general_hits),
        "specific_hits":  dict(specific_hits),
        "total_general":  sum(general_hits.values()),
        "total_specific": sum(specific_hits.values()),
    }


# ---------------------------------------------------------------------------
# Repository scanning
# ---------------------------------------------------------------------------

def scan_repo(
    repo_path: Path,
    keywords_raw: list[dict],
    workers: int = cfg.ANALYSIS_WORKERS,
) -> dict:
    """
    Walk repo_path, scan all eligible files, return aggregate stats.
    """
    compiled_kws = compile_analysis_keywords(keywords_raw)
    tfd_kws = [k for k in compiled_kws if k["category"] == "test_file_detection"]

    tasks = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in cfg.SKIP_DIRS]
        for fname in files:
            fp = Path(root) / fname
            lang = detect_language(fp)
            tasks.append((str(fp), str(repo_path), lang))

    file_results: list[dict] = []
    if workers <= 1:
        _worker_init(keywords_raw)
        for task in tasks:
            result = _scan_file(task)
            if result:
                file_results.append(result)
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_worker_init,
            initargs=(keywords_raw,),
        ) as pool:
            futures = {pool.submit(_scan_file, t): t for t in tasks}
            for fut in as_completed(futures):
                try:
                    result = fut.result()
                    if result:
                        file_results.append(result)
                except Exception as exc:
                    pass  # logged at higher level

    return _aggregate_file_results(file_results, keywords_raw)


def _aggregate_file_results(file_results: list[dict], keywords_raw: list[dict]) -> dict:
    kw_labels = {k["id"]: k["label"] for k in keywords_raw}

    categories = ["test_code", "source_code", "docs", "config", "other"]
    by_cat: dict[str, list[dict]] = {c: [] for c in categories}
    for fr in file_results:
        by_cat[fr["category"]].append(fr)

    # Per-file category stats
    cat_stats: dict[str, dict] = {}
    for cat, items in by_cat.items():
        total_general  = sum(i["total_general"]  for i in items)
        total_specific = sum(i["total_specific"] for i in items)
        hit_files      = sum(1 for i in items if i["total_specific"] > 0)
        total_lines    = sum(i["n_lines"] for i in items)
        hit_lines      = sum(i["n_hit_lines"] for i in items)
        cat_stats[cat] = {
            "file_count":          len(items),
            "hit_file_count":      hit_files,
            "total_lines":         total_lines,
            "hit_line_count":      hit_lines,
            "total_general_hits":  total_general,
            "total_specific_hits": total_specific,
        }

    # Keyword hit totals (with labels)
    hits_by_kw_id: dict[str, int] = defaultdict(int)
    for fr in file_results:
        for kw_id, cnt in fr["specific_hits"].items():
            hits_by_kw_id[kw_id] += cnt

    hits_by_keyword = {
        kw_id: {"count": cnt, "label": kw_labels.get(kw_id, kw_id)}
        for kw_id, cnt in hits_by_kw_id.items()
    }

    # Language distribution
    langs: dict[str, int] = defaultdict(int)
    for fr in file_results:
        if fr.get("language"):
            langs[fr["language"]] += 1

    total_files    = len(file_results)
    total_hit_files = sum(1 for f in file_results if f["total_specific"] > 0)
    total_lines    = sum(f["n_lines"] for f in file_results)
    total_hit_lines = sum(f["n_hit_lines"] for f in file_results)
    total_general  = sum(f["total_general"] for f in file_results)
    total_specific = sum(f["total_specific"] for f in file_results)

    return {
        "total_files":         total_files,
        "total_hit_files":     total_hit_files,
        "total_lines":         total_lines,
        "total_hit_lines":     total_hit_lines,
        "total_general_hits":  total_general,
        "total_specific_hits": total_specific,
        "by_category":         cat_stats,
        "hits_by_keyword":     hits_by_keyword,
        "language_distribution": dict(langs),
        "file_details":        file_results,
    }


# ---------------------------------------------------------------------------
# Commit analysis (PyDriller or git log fallback)
# ---------------------------------------------------------------------------

def analyse_commits(
    repo_path: Path,
    technique_keywords: list[str],
    logger,
) -> dict:
    """
    Analyse full git commit history for timeline data (RQ3).
    Returns commit timeline statistics.
    """
    if _PYDRILLER:
        return _commits_pydriller(repo_path, technique_keywords, logger)
    return _commits_git_log(repo_path, technique_keywords, logger)


def _commits_pydriller(repo_path: Path, keywords: list[str], logger) -> dict:
    from pydriller import Repository
    kw_patterns = [re.compile(re.escape(k), re.IGNORECASE) for k in keywords]

    total_commits = 0
    technique_commits = 0
    first_commit_date = None
    last_commit_date  = None
    commits_by_month: dict[str, int] = defaultdict(int)
    technique_by_month: dict[str, int] = defaultdict(int)
    commit_dates: list[str] = []
    technique_commit_dates: list[str] = []

    try:
        for commit in Repository(str(repo_path)).traverse_commits():
            dt = commit.committer_date or commit.author_date
            if dt is None:
                continue
            total_commits += 1
            dt_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            month  = dt.strftime("%Y-%m")
            commit_dates.append(dt_str)
            commits_by_month[month] += 1

            if first_commit_date is None or dt_str < first_commit_date:
                first_commit_date = dt_str
            if last_commit_date is None or dt_str > last_commit_date:
                last_commit_date = dt_str

            msg = commit.msg or ""
            if any(p.search(msg) for p in kw_patterns):
                technique_commits += 1
                technique_by_month[month] += 1
                technique_commit_dates.append(dt_str)
    except Exception as exc:
        logger.warning(f"PyDriller error on {repo_path}: {exc}")

    return _build_commit_result(
        total_commits, technique_commits,
        commit_dates, commits_by_month, technique_by_month,
        first_commit_date, last_commit_date,
        technique_commit_dates,
    )


def _commits_git_log(repo_path: Path, keywords: list[str], logger) -> dict:
    kw_patterns = [re.compile(re.escape(k), re.IGNORECASE) for k in keywords]
    total_commits = 0
    technique_commits = 0
    first_commit_date = None
    last_commit_date  = None
    commits_by_month: dict[str, int] = defaultdict(int)
    technique_by_month: dict[str, int] = defaultdict(int)
    commit_dates: list[str] = []
    technique_commit_dates: list[str] = []

    try:
        result = subprocess.run(
            ["git", "log", "--format=%H %aI %s"],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=120,
        )
        for line in result.stdout.splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 2:
                continue
            dt_str = parts[1]
            msg = parts[2] if len(parts) > 2 else ""
            month = dt_str[:7]
            total_commits += 1
            commit_dates.append(dt_str)
            commits_by_month[month] += 1
            if first_commit_date is None or dt_str < first_commit_date:
                first_commit_date = dt_str
            if last_commit_date is None or dt_str > last_commit_date:
                last_commit_date = dt_str
            if any(p.search(msg) for p in kw_patterns):
                technique_commits += 1
                technique_by_month[month] += 1
                technique_commit_dates.append(dt_str)
    except Exception as exc:
        logger.warning(f"git log error on {repo_path}: {exc}")

    return _build_commit_result(
        total_commits, technique_commits,
        commit_dates, commits_by_month, technique_by_month,
        first_commit_date, last_commit_date,
        technique_commit_dates,
    )


def _build_commit_result(
    total: int, technique: int,
    commit_dates: list[str],
    commits_by_month: dict[str, int],
    tech_by_month: dict[str, int],
    first: str | None,
    last: str | None,
    technique_commit_dates: list[str] | None = None,
) -> dict:
    span_days = None
    if first and last and first != last:
        from datetime import datetime, timezone
        try:
            t0 = datetime.fromisoformat(first.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last.replace("Z", "+00:00"))
            span_days = abs((t1 - t0).days)
        except ValueError:
            pass

    avg_commit_interval_days = None
    if total > 1 and span_days is not None:
        avg_commit_interval_days = round(span_days / (total - 1), 2)

    # Technique Commit Span = avg interval between consecutive technique commits
    technique_commit_span_avg_days = None
    if technique_commit_dates and len(technique_commit_dates) >= 2:
        from datetime import datetime
        parsed = []
        for ds in technique_commit_dates:
            try:
                parsed.append(datetime.fromisoformat(ds.replace("Z", "+00:00")))
            except ValueError:
                pass
        parsed.sort()
        if len(parsed) >= 2:
            intervals = [(parsed[i+1] - parsed[i]).days for i in range(len(parsed)-1)]
            technique_commit_span_avg_days = round(sum(intervals) / len(intervals), 2)

    return {
        "total_commits":                    total,
        "technique_commits":                technique,
        "first_commit_date":                first,
        "last_commit_date":                 last,
        "commit_span_days":                 span_days,
        "avg_commit_interval_days":         avg_commit_interval_days,
        "technique_commit_span_avg_days":   technique_commit_span_avg_days,
        "commits_by_month":                 dict(commits_by_month),
        "technique_commits_by_month":       dict(tech_by_month),
    }


# ---------------------------------------------------------------------------
# Repo classification
# ---------------------------------------------------------------------------

_RESEARCH_CONFERENCE_PATTERN = re.compile(
    r"\b(?:ICSE|FSE|ISSTA|ASE|EMSE|TSE|PLDI|OOPSLA|SOSP|OSDI|CCS|NDSS|IEEE|ACM|USENIX)\b"
)
_DOI_PATTERN     = re.compile(r"\bdoi\.org/\S+|\barXiv:\d{4}\.\d{4,}", re.IGNORECASE)
_RESEARCH_KW     = re.compile(
    r"\b(?:replication\s+package|empirical\s+(?:study|evaluation)|zenodo|figshare"
    r"|conference|journal|artifact\s+evaluation)\b", re.IGNORECASE
)
_REPO_RESEARCH_KW = re.compile(
    r"\b(?:study|empirical|evaluation|experiment|replication|artifact|benchmark)\b",
    re.IGNORECASE,
)


def classify_repo(
    repo_path: Path,
    scan_result: dict,
    repo_meta: dict,
    logger,
) -> dict:
    """
    Ordered decision tree:
      1. Research artifact
      2. Framework / library
      3. Actual usage
      4. Unclassified
    A repo can satisfy multiple classifications.
    """
    signals: list[str] = []
    classifications: list[str] = []

    # ---- Read README ----
    readme_text = ""
    for fname in ("README.md", "README.rst", "README.txt", "README"):
        readme_path = repo_path / fname
        if readme_path.exists():
            try:
                readme_text = readme_path.read_text(encoding="utf-8", errors="ignore")[:50000]
            except OSError:
                pass
            break

    description = repo_meta.get("description", "") or ""
    name = repo_meta.get("full_name", "").split("/")[-1]

    # ---- 1. Research ----
    research_score = 0
    if _DOI_PATTERN.search(readme_text):
        signals.append("doi_arxiv_in_readme")
        research_score += 3
    if _RESEARCH_CONFERENCE_PATTERN.search(readme_text):
        signals.append("conference_name_in_readme")
        research_score += 2
    if _RESEARCH_KW.search(readme_text):
        signals.append("research_keywords_in_readme")
        research_score += 2
    if _REPO_RESEARCH_KW.search(f"{name} {description}"):
        signals.append("research_keywords_in_name_desc")
        research_score += 1
    # Check for data/ and rq*/ directories
    has_data = (repo_path / "data").is_dir() or (repo_path / "results").is_dir()
    has_rq   = any(repo_path.glob("rq*/"))
    if has_data and has_rq:
        signals.append("data_rq_dirs")
        research_score += 3
    if any(repo_path.rglob("*.ipynb")) or any(repo_path.rglob("*.R")):
        signals.append("notebook_or_R_files")
        research_score += 2

    if research_score >= 3:
        classifications.append("research_artifact")

    # ---- 2. Framework ----
    framework_score = 0
    by_cat = scan_result.get("by_category", {})
    source_hits = by_cat.get("source_code", {}).get("total_specific_hits", 0)
    test_hits   = by_cat.get("test_code",   {}).get("total_specific_hits", 0)
    total_hits  = scan_result.get("total_specific_hits", 0)

    if total_hits > 0 and source_hits / max(total_hits, 1) >= 0.5:
        signals.append("50pct_hits_in_source")
        framework_score += 2

    # Check manifests for runtime (not dev) technique dependency
    runtime_dep = _check_runtime_dependency(repo_path, logger)
    if runtime_dep:
        signals.append(f"runtime_dep:{runtime_dep}")
        framework_score += 3

    readme_framework = re.search(
        r"\b(?:testing\s+framework|test\s+framework|testing\s+library)\b",
        readme_text, re.IGNORECASE
    )
    if readme_framework:
        signals.append("readme_testing_framework")
        framework_score += 1

    if framework_score >= 2:
        classifications.append("framework")

    # ---- 3. Actual usage ----
    usage_score = 0
    dev_dep = _check_dev_dependency(repo_path, logger)
    if dev_dep:
        signals.append(f"dev_dep:{dev_dep}")
        usage_score += 2

    if total_hits > 0 and test_hits / max(total_hits, 1) >= 0.8:
        signals.append("80pct_hits_in_test_code")
        usage_score += 2

    if "framework" not in classifications and not dev_dep and not runtime_dep:
        if total_hits > 0 and test_hits > 0:
            signals.append("hits_in_test_code")
            usage_score += 1

    if usage_score >= 1:
        classifications.append("actual_usage")

    if not classifications:
        classifications.append("unclassified")

    return {
        "classifications": classifications,
        "signals":         signals,
        "scores": {
            "research": research_score,
            "framework": framework_score,
            "usage":     usage_score,
        },
    }


def _check_runtime_dependency(repo_path: Path, logger) -> str | None:
    """Return dependency name if a technique lib is in runtime deps."""
    return None  # placeholder — full manifest parsing is complex; extend here


def _check_dev_dependency(repo_path: Path, logger) -> str | None:
    """Return dependency name if a technique lib is in dev/test deps."""
    for req in repo_path.glob("requirements*.txt"):
        try:
            text = req.read_text(encoding="utf-8", errors="ignore").lower()
            for lib in ("hypothesis", "proptest", "quickcheck", "scalacheck",
                        "jqwik", "fast-check", "fscheck", "gopter", "proper"):
                if lib in text:
                    return lib
        except OSError:
            pass
    return None


# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------

def detect_domains(repo_meta: dict, readme_text: str) -> list[str]:
    """Match domain keywords against repo name, description, topics, and README."""
    text = " ".join([
        repo_meta.get("full_name", ""),
        repo_meta.get("description", "") or "",
        " ".join(repo_meta.get("topics", [])),
        readme_text[:5000],
    ]).lower()

    matched = []
    for domain, keywords in cfg.DOMAIN_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(domain)
    return matched


# ---------------------------------------------------------------------------
# Clone helpers
# ---------------------------------------------------------------------------

def _clone_repo(repo_full_name: str, clone_url: str, target: Path, logger) -> bool:
    if target.exists():
        logger.info(f"SKIP clone (exists): {repo_full_name}")
        return True
    try:
        depth_args = ["--depth", str(cfg.CLONE_DEPTH)] if cfg.CLONE_DEPTH else []
        subprocess.run(
            ["git", "clone", "--no-tags"] + depth_args + [clone_url, str(target)],
            capture_output=True, timeout=300,
        )
        logger.info(f"Cloned: {repo_full_name}")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"Clone timeout: {repo_full_name}")
        shutil.rmtree(target, ignore_errors=True)
        return False
    except Exception as exc:
        logger.error(f"Clone failed for {repo_full_name}: {exc}")
        shutil.rmtree(target, ignore_errors=True)
        return False


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(slug: str, restart: bool = False, workers: int = cfg.ANALYSIS_WORKERS) -> None:
    ensure_dirs(slug)
    dirs = technique_dirs(slug)
    logger = setup_logging(slug, "code_analysis")

    analysis_dir = dirs["analysis"]
    analysis_dir.mkdir(parents=True, exist_ok=True)

    history_path  = analysis_dir / "code_history.json"
    results_path  = analysis_dir / "code_repos.json"

    if restart:
        logger.info("--restart: clearing code analysis history and results")
        for p in (history_path, results_path):
            if p.exists():
                p.unlink()

    history: dict = load_json(history_path, {})
    results: list = load_json(results_path, [])

    # Load code-surface search results only
    code_file = dirs["search"] / "code.json"
    if not code_file.exists():
        print("No code.json found — run search phase first.")
        return

    code_results: list[dict] = load_json(code_file, [])

    # Deduplicate repos from code surface
    seen_repos: dict[str, dict] = {}
    for item in code_results:
        name = item.get("repo_full_name", "")
        if name and name not in seen_repos:
            seen_repos[name] = item

    candidates = list(seen_repos.values())
    logger.info(f"Found {len(candidates)} unique repos on code surface")

    # Load analysis keywords (raw, passed to workers)
    from utils import load_analysis_keywords
    keywords_raw = load_analysis_keywords(slug)
    tech_search_keywords = _load_search_phrases(slug)

    cloned_dir = dirs["cloned"]
    cloned_dir.mkdir(parents=True, exist_ok=True)

    # Shuffle and batch
    unprocessed = [c for c in candidates if history.get(c["repo_full_name"]) not in ("done", "failed")]
    random.shuffle(unprocessed)

    batch_bytes = 0
    batch: list[dict] = []
    batches: list[list[dict]] = []

    for candidate in unprocessed:
        size_bytes = (candidate.get("size_kb", 0) or 0) * 1024
        if (batch and batch_bytes + size_bytes > cfg.CLONE_BATCH_MAX_BYTES) or len(batch) >= cfg.CLONE_BATCH_MAX_REPOS:
            batches.append(batch)
            batch = []
            batch_bytes = 0
        batch.append(candidate)
        batch_bytes += size_bytes
    if batch:
        batches.append(batch)

    logger.info(f"Processing {len(unprocessed)} repos in {len(batches)} batches")

    for batch_idx, batch in enumerate(batches):
        print(f"\nBatch {batch_idx+1}/{len(batches)} — {len(batch)} repos")
        cloned_paths: list[tuple[dict, Path]] = []

        # --- Clone batch ---
        for candidate in tqdm(batch, desc="Cloning", unit="repo"):
            name = candidate["repo_full_name"]
            if history.get(name) in ("done", "failed"):
                continue
            clone_url  = candidate.get("repo_clone_url") or f"https://github.com/{name}.git"
            local_path = safe_clone_path(cloned_dir, name)
            success = _clone_repo(name, clone_url, local_path, logger)
            if success:
                history[name] = "cloned"
                save_json(history_path, history)
                cloned_paths.append((candidate, local_path))
            else:
                history[name] = "failed"
                save_json(history_path, history)

        # --- Analyse batch ---
        for candidate, repo_path in tqdm(cloned_paths, desc="Analysing", unit="repo"):
            name = candidate["repo_full_name"]
            try:
                scan = scan_repo(repo_path, keywords_raw, workers=workers)
                commits = analyse_commits(repo_path, tech_search_keywords, logger)

                # Read README for classification + domains
                readme_text = ""
                for fn in ("README.md", "README.rst", "README.txt", "README"):
                    rp = repo_path / fn
                    if rp.exists():
                        try:
                            readme_text = rp.read_text(encoding="utf-8", errors="ignore")[:50000]
                        except OSError:
                            pass
                        break

                repo_meta = {
                    "full_name":   name,
                    "html_url":    candidate.get("html_url", ""),
                    "stars":       candidate.get("stars"),        # None for code surface items; enriched from repo_metadata.json in analysis.py
                    "language":    candidate.get("language"),     # None for code surface items; enriched from repo_metadata.json in analysis.py
                    "description": candidate.get("description", "") or "",
                    "topics":      candidate.get("topics", []),
                    "created_at":  candidate.get("created_at"),
                    "size_kb":     candidate.get("size_kb", 0),
                }
                classification = classify_repo(repo_path, scan, repo_meta, logger)
                domains = detect_domains(repo_meta, readme_text)

                record = {
                    **repo_meta,
                    "scan":           scan,
                    "commits":        commits,
                    "classification": classification,
                    "domains":        domains,
                    "readme_snippet": readme_text[:2000],
                }
                results.append(record)
                save_json(results_path, results)
                history[name] = "done"
                save_json(history_path, history)
                logger.info(f"Analysed: {name} — {scan['total_specific_hits']} specific hits")

            except Exception as exc:
                logger.error(f"Analysis failed for {name}: {exc}", exc_info=True)
                history[name] = "failed"
                save_json(history_path, history)

        # --- Delete cloned repos ---
        for _, repo_path in cloned_paths:
            shutil.rmtree(repo_path, ignore_errors=True)
        logger.info(f"Batch {batch_idx+1} complete — clones deleted")

    print(f"\nCode analysis complete: {len(results)} repos analysed.")
    logger.info(f"Code analysis done: {len(results)} repos")


def _load_search_phrases(slug: str) -> list[str]:
    """Return bare keyword strings (no quotes) for commit message matching."""
    from utils import load_search_keywords
    raw = load_search_keywords(slug)
    phrases = []
    for kw in raw:
        clean = kw.strip('"').strip()
        if clean:
            phrases.append(clean)
    return phrases
