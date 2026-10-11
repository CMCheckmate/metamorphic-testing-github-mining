"""
GitHub API look-ups for the specialised pipeline (used by non_code_specialised_analysis.py)
==========================================================================================
Data the search does not collect; each writes a resumable cache in results/<slug>/analysis/.

  fetch_metadata         GET /repos/{r} for every repo found on any surface → cloned_repo_metadata.json
                         (language, creation date, size, description, topics; MT ~9.3k calls, ~3 h)
  fetch_readmes          GET /repos/{r}/readme for each verified non-CODE repo → repo_readmes.json (A6/A7)
  fetch_lang_baseline    repository-search total_count per language, pushed in the year before the
                         search → github_language_baseline.json (A5 normalisation; ~30 calls)
  fetch_commit_coverage  pushed_at / archived for 150 sampled COMMITS-surface repos
                         → commit_coverage_check.json (checks that commit search covers inactive repos)

Shared helpers (_get with rate-limit handling, _fetch_many) are also used by technique_data.py.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from core_helpers import config as cfg
from core_helpers.utils import resolve_technique, technique_dirs, load_json, save_json, setup_logging

_SURFACES = ["code", "repos", "commits", "prs", "issues", "discussions"]
_README_MAX_CHARS = 20_000


def _headers(raw: bool = False) -> dict:
    h = {"Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json"}
    if cfg.GITHUB_TOKEN:
        h["Authorization"] = f"token {cfg.GITHUB_TOKEN}"
    return h


def _get(url: str, logger, raw: bool = False, params: dict | None = None):
    """GET with rate-limit wait; returns the Response (or None after retries)."""
    for attempt in range(cfg.RETRY_ATTEMPTS):
        try:
            r = requests.get(url, headers=_headers(raw), params=params, timeout=30)
        except requests.RequestException as exc:
            logger.warning(f"{url}: {exc}")
            time.sleep(cfg.RETRY_BACKOFF_BASE ** attempt)
            continue
        if r.status_code in (403, 429):
            # Primary limit (remaining = 0) or secondary/abuse limit (Retry-After, or a 403
            # mentioning "secondary rate limit") — search endpoints hit the latter often.
            body = r.text[:300].lower()
            if (r.headers.get("X-RateLimit-Remaining") == "0" or r.headers.get("Retry-After")
                    or "rate limit" in body or "abuse" in body):
                if r.headers.get("Retry-After"):
                    wait = float(r.headers["Retry-After"])
                elif r.headers.get("X-RateLimit-Remaining") == "0":
                    wait = int(r.headers.get("X-RateLimit-Reset", time.time() + 60)) - time.time()
                else:
                    wait = 60 * (attempt + 1)
                wait = max(wait, 5)
                logger.warning(f"Rate limited ({r.status_code}) — sleeping {wait:.0f}s: {url}")
                time.sleep(wait)
                continue
        if r.status_code not in (200, 404):
            logger.warning(f"HTTP {r.status_code} for {url} {params or ''}: {r.text[:200]}")
        return r
    logger.warning(f"Giving up after {cfg.RETRY_ATTEMPTS} attempts: {url} {params or ''}")
    return None


def _fetch_many(names: list[str], cache_path, fetch_one, label: str, logger) -> None:
    cache: dict = load_json(cache_path, {}) or {}
    todo = [n for n in names if n not in cache]
    print(f"{label}: {len(names):,} repos, {len(cache):,} cached, {len(todo):,} to fetch")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(fetch_one, n): n for n in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            name, value, keep = fut.result()
            if keep:
                cache[name] = value
            if i % 200 == 0:
                save_json(cache_path, cache)
                print(f"  [{i:,}/{len(todo):,}]")
    save_json(cache_path, cache)
    print(f"{label}: {len(cache):,} cached -> {cache_path}")


def _repos_on(dirs: dict, surfaces: list[str]) -> list[str]:
    names: set[str] = set()
    for s in surfaces:
        for it in load_json(dirs["search"] / f"{s}.json", []) or []:
            if it.get("repo_full_name"):
                names.add(it["repo_full_name"])
    return sorted(names)


def fetch_readmes(dirs: dict, logger) -> None:
    def one(name: str):
        time.sleep(0.75)
        r = _get(f"{cfg.GITHUB_API_BASE}/repos/{name}/readme", logger, raw=True)
        if r is None:
            return name, None, False
        if r.status_code == 404:
            return name, None, True                # no README / deleted
        return name, (r.text[:_README_MAX_CHARS] if r.status_code == 200 else None), r.status_code == 200
    # Only the repositories A6/A7 use (verified non-CODE repos), if the aggregate step has run.
    overall = load_json(dirs["analysis"] / "overall.json", {}) or {}
    targets = (overall.get("sections", {}).get("a6") or {}).get("verified_repos") or _repos_on(dirs, _SURFACES[1:])
    _fetch_many(sorted(targets), dirs["analysis"] / "repo_readmes.json", one, "readmes", logger)


def fetch_lang_baseline(dirs: dict, logger) -> None:
    """GitHub-wide primary-language counts for repositories pushed in the year before the
    search (mirrors code search's 'active in the last year' index) → A5 normalisation."""
    from collections import Counter
    from datetime import date, timedelta
    meta = load_json(dirs["analysis"] / "cloned_repo_metadata.json", {}) or {}
    code = _repos_on(dirs, ["code"])
    langs = [l for l, _ in Counter((meta.get(r) or {}).get("language") for r in code if (meta.get(r) or {}).get("language")).most_common(30)]
    since = (date.fromisoformat(cfg.SLICE_END_DATE) - timedelta(days=365)).isoformat()
    out = {"pushed_since": since, "languages": {}}
    r = _get(f"{cfg.GITHUB_API_BASE}/search/repositories", logger, params={"q": f"pushed:>={since}", "per_page": 1})
    out["total"] = r.json().get("total_count") if r is not None and r.status_code == 200 else None
    print(f"  all languages: {out['total']}")
    for lang in langs:
        time.sleep(cfg.RATE_LIMIT_PAUSE)
        r = _get(f"{cfg.GITHUB_API_BASE}/search/repositories", logger,
                 params={"q": f'language:"{lang}" pushed:>={since}', "per_page": 1})
        out["languages"][lang] = r.json().get("total_count") if r is not None and r.status_code == 200 else None
        print(f"  {lang}: {out['languages'][lang]}")
    out["fetched_at"] = datetime.now(timezone.utc).isoformat()
    path = dirs["analysis"] / "github_language_baseline.json"
    save_json(path, out)
    print(f"language baseline -> {path}")


def fetch_commit_coverage(dirs: dict, logger, n: int = 150) -> None:
    """Sample COMMITS-surface repos and record pushed_at / archived, to test whether commit
    search (unlike code search) also returns repositories inactive for over a year."""
    import random
    from collections import defaultdict
    from datetime import date, timedelta
    newest = defaultdict(str)
    for c in load_json(dirs["search"] / "commits.json", []) or []:
        rn, d = c.get("repo_full_name"), (c.get("committer_date") or "")[:10]
        if rn and d > newest[rn]:
            newest[rn] = d
    old  = sorted(r for r, d in newest.items() if d < "2024-01-01")
    rest = sorted(set(newest) - set(old))
    rnd  = random.Random(20261010)
    sample = rnd.sample(old, min(n // 2, len(old))) + rnd.sample(rest, min(n - min(n // 2, len(old)), len(rest)))
    cutoff = (date.fromisoformat(cfg.SLICE_END_DATE) - timedelta(days=365)).isoformat()
    rows = []
    for rn in sample:
        r = _get(f"{cfg.GITHUB_API_BASE}/repos/{rn}", logger)
        if r is None or r.status_code != 200:
            rows.append({"repo": rn, "status": "unavailable"})
        else:
            j = r.json()
            pushed = (j.get("pushed_at") or "")[:10]
            rows.append({"repo": rn, "status": "ok", "pushed_at": pushed, "archived": bool(j.get("archived")),
                         "inactive_1y": bool(pushed) and pushed < cutoff, "newest_matched_commit": newest[rn]})
        time.sleep(0.75)
    path = dirs["analysis"] / "commit_coverage_check.json"
    save_json(path, {"cutoff": cutoff, "repos": rows, "fetched_at": datetime.now(timezone.utc).isoformat()})
    ok = [r for r in rows if r["status"] == "ok"]
    print(f"commit coverage: {sum(r['inactive_1y'] for r in ok)}/{len(ok)} inactive >1y, "
          f"{sum(r['archived'] for r in ok)} archived -> {path}")


def fetch_metadata(slug: str, logger) -> None:
    """Metadata of every repository found on any search surface (the function the original
    non-code analysis used) → analysis/cloned_repo_metadata.json."""
    from full_analysis.analysis import fetch_cloned_repo_metadata
    fetch_cloned_repo_metadata(slug, cfg.GITHUB_TOKEN, logger)
