"""
Phase: Search
=============
Queries GitHub across six surfaces for adoption of the specified testing technique.

Surfaces:
  code        — /search/code              (9 req/min)
  repos       — /search/repositories      (30 req/min)
  issues      — /search/issues (type:issue)
  prs         — /search/issues (type:pr)
  commits     — /search/commits           (30 req/min)
  discussions — GraphQL search()

Keywords are read from inputs/<prefix>_search_keywords.txt.
Results are saved to results/<slug>/search/{code,repos,issues,prs,commits,discussions}.json.
Progress is tracked in results/<slug>/search/search_history.json.

Resume: if stopped mid-keyword, that keyword is re-run on the next start.
        Write to history only after a keyword completes all surfaces.
--overwrite: resets history and all result files.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

from tqdm import tqdm

import config as cfg
from utils import (
    resolve_technique, technique_dirs, ensure_dirs,
    setup_logging, load_json, save_json,
    load_search_keywords, gh_get, gh_graphql,
)

SURFACES = ["code", "repos", "issues", "prs", "commits", "discussions"]


# ---------------------------------------------------------------------------
# Surface handlers
# ---------------------------------------------------------------------------

def _search_code(keyword: str, logger, per_page: int = cfg.GITHUB_API_PER_PAGE) -> list[dict]:
    """Search code surface. One query string, returns all paged results."""
    url = f"{cfg.GITHUB_API_BASE}/search/code"
    results = []
    page = 1
    api_hit_count = None

    while True:
        params = {"q": keyword, "per_page": per_page, "page": page}
        data = gh_get(url, params=params, is_code_search=True, logger=logger)
        total = data.get("total_count", 0)
        if api_hit_count is None:
            api_hit_count = total
            if total > 0 and not data.get("items"):
                raise RuntimeError(
                    f"CODE SEARCH CRITICAL: api_hit_count={total} but items=[] for keyword {keyword!r}.\n"
                    f"Full response: {json.dumps(data, indent=2)}"
                )
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            repo = item.get("repository", {})
            results.append({
                "id":             item.get("sha", ""),
                "url":            item.get("url", ""),
                "html_url":       item.get("html_url", ""),
                "surface":        "code",
                "file_path":      item.get("path", ""),
                "repo_id":        repo.get("id"),
                "repo_full_name": repo.get("full_name", ""),
                "repo_html_url":  repo.get("html_url", ""),
                "repo_clone_url": f"https://github.com/{repo.get('full_name', '')}.git",
                "language":       item.get("language") or repo.get("language"),
                "stars":          repo.get("stargazers_count"),
                "matched_keyword": keyword,
            })
        if page * per_page >= min(total, 1000):
            break
        page += 1

    logger.info(f"CODE keyword={keyword!r}: api_hit_count={api_hit_count}, results={len(results)}")
    return results


def _search_repos(keyword: str, logger, per_page: int = cfg.GITHUB_API_PER_PAGE) -> list[dict]:
    url = f"{cfg.GITHUB_API_BASE}/search/repositories"
    results = []
    page = 1
    api_hit_count = None

    while True:
        params = {"q": keyword, "per_page": per_page, "page": page}
        data = gh_get(url, params=params, logger=logger)
        total = data.get("total_count", 0)
        if api_hit_count is None:
            api_hit_count = total
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            results.append({
                "id":             item.get("id"),
                "url":            item.get("url", ""),
                "html_url":       item.get("html_url", ""),
                "surface":        "repos",
                "repo_id":        item.get("id"),
                "repo_full_name": item.get("full_name", ""),
                "repo_clone_url": item.get("clone_url", ""),
                "title":          item.get("name", ""),
                "body":           item.get("description", "") or "",
                "stars":          item.get("stargazers_count"),
                "language":       item.get("language"),
                "topics":         item.get("topics", []),
                "created_at":     item.get("created_at"),
                "updated_at":     item.get("updated_at"),
                "size_kb":        item.get("size", 0),
                "is_fork":        item.get("fork", False),
                "matched_keyword": keyword,
            })
        if page * per_page >= min(total, 1000):
            break
        page += 1

    logger.info(f"REPOS keyword={keyword!r}: api_hit_count={api_hit_count}, results={len(results)}")
    return results


def _search_issues_prs(keyword: str, kind: str, logger, per_page: int = cfg.GITHUB_API_PER_PAGE) -> list[dict]:
    """kind is 'issue' or 'pr'."""
    url = f"{cfg.GITHUB_API_BASE}/search/issues"
    results = []
    page = 1
    api_hit_count = None
    q = f"{keyword} type:{kind}"

    while True:
        params = {"q": q, "per_page": per_page, "page": page}
        data = gh_get(url, params=params, logger=logger)
        total = data.get("total_count", 0)
        if api_hit_count is None:
            api_hit_count = total
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            repo_url = item.get("repository_url", "")
            repo_full_name = "/".join(repo_url.rstrip("/").split("/")[-2:]) if repo_url else ""
            results.append({
                "id":             item.get("id"),
                "number":         item.get("number"),
                "url":            item.get("url", ""),
                "html_url":       item.get("html_url", ""),
                "surface":        kind,
                "title":          item.get("title", ""),
                "body":           item.get("body", "") or "",
                "state":          item.get("state"),
                "comment_count":  item.get("comments", 0),
                "created_at":     item.get("created_at"),
                "updated_at":     item.get("updated_at"),
                "repo_full_name": repo_full_name,
                "matched_keyword": keyword,
            })
        if page * per_page >= min(total, 1000):
            break
        page += 1

    logger.info(f"{kind.upper()} keyword={keyword!r}: api_hit_count={api_hit_count}, results={len(results)}")
    return results


def _search_commits(keyword: str, logger, per_page: int = cfg.GITHUB_API_PER_PAGE) -> list[dict]:
    url = f"{cfg.GITHUB_API_BASE}/search/commits"
    results = []
    page = 1
    api_hit_count = None

    while True:
        params = {"q": keyword, "per_page": per_page, "page": page}
        data = gh_get(url, params=params, delay=cfg.RATE_LIMIT_PAUSE, logger=logger)
        total = data.get("total_count", 0)
        if api_hit_count is None:
            api_hit_count = total
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            commit = item.get("commit", {})
            author = commit.get("author", {})
            repo = item.get("repository", {})
            results.append({
                "id":             item.get("sha", ""),
                "url":            item.get("url", ""),
                "html_url":       item.get("html_url", ""),
                "surface":        "commits",
                "body":           commit.get("message", "") or "",
                "created_at":     author.get("date"),
                "repo_full_name": repo.get("full_name", ""),
                "repo_id":        repo.get("id"),
                "matched_keyword": keyword,
            })
        if page * per_page >= min(total, 1000):
            break
        page += 1

    logger.info(f"COMMITS keyword={keyword!r}: api_hit_count={api_hit_count}, results={len(results)}")
    return results


_DISCUSSION_QUERY = """
query($query: String!, $after: String) {
  search(query: $query, type: DISCUSSION, first: 25, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Discussion {
        id
        number
        title
        body
        createdAt
        updatedAt
        url
        comments { totalCount }
        repository { nameWithOwner }
      }
    }
  }
}
"""


def _search_discussions(keyword: str, logger) -> list[dict]:
    results = []
    cursor = None
    api_hit_count = None

    while True:
        resp = gh_graphql(_DISCUSSION_QUERY, {"query": keyword, "after": cursor}, logger=logger)
        search = resp.get("data", {}).get("search", {})
        if api_hit_count is None:
            api_hit_count = search.get("issueCount", 0)
        nodes = search.get("nodes", [])
        for node in nodes:
            if not node:
                continue
            results.append({
                "id":             node.get("id", ""),
                "number":         node.get("number"),
                "url":            node.get("url", ""),
                "html_url":       node.get("url", ""),
                "surface":        "discussions",
                "title":          node.get("title", ""),
                "body":           node.get("body", "") or "",
                "comment_count":  node.get("comments", {}).get("totalCount", 0),
                "created_at":     node.get("createdAt"),
                "updated_at":     node.get("updatedAt"),
                "repo_full_name": node.get("repository", {}).get("nameWithOwner", ""),
                "matched_keyword": keyword,
            })
        page_info = search.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    logger.info(f"DISCUSSIONS keyword={keyword!r}: api_hit_count={api_hit_count}, results={len(results)}")
    return results


# ---------------------------------------------------------------------------
# Adaptive date-range slicing for code search
# ---------------------------------------------------------------------------

def _slice_code_search(keyword: str, logger, depth: int = 0) -> list[dict]:
    """
    Recurse date-range slices for code search to work around GitHub's 1000-result cap.
    Uses created:<start>..<end> qualifier appended to the keyword.
    """
    if depth >= cfg.SLICE_MAX_DEPTH:
        return _search_code(keyword, logger)

    start = date.fromisoformat(cfg.SLICE_START_DATE)
    end   = date.fromisoformat(cfg.SLICE_END_DATE)
    return _slice_range(keyword, start, end, depth, logger)


def _slice_range(keyword: str, start: date, end: date, depth: int, logger) -> list[dict]:
    sliced_q = f"{keyword} created:{start.isoformat()}..{end.isoformat()}"
    url = f"{cfg.GITHUB_API_BASE}/search/code"
    params = {"q": sliced_q, "per_page": 1, "page": 1}
    data = gh_get(url, params=params, is_code_search=True, logger=logger)
    total = data.get("total_count", 0)

    if total <= cfg.SLICE_THRESHOLD or (end - start).days <= cfg.SLICE_MIN_DAYS:
        return _search_code(sliced_q, logger)

    mid = start + (end - start) / 2
    left  = _slice_range(keyword, start, mid, depth + 1, logger)
    right = _slice_range(keyword, mid + timedelta(days=1), end, depth + 1, logger)
    return left + right


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedup(existing: list[dict], new_items: list[dict], key: str = "id") -> tuple[list[dict], int]:
    """Merge new_items into existing, deduplicating by key. Returns (merged, added_count)."""
    seen: dict[str, int] = {str(r[key]): i for i, r in enumerate(existing) if r.get(key)}
    added = 0
    for item in new_items:
        k = str(item.get(key, ""))
        if not k:
            existing.append(item)
            added += 1
        elif k in seen:
            existing[seen[k]].setdefault("matched_keywords", [])
            kw = item.get("matched_keyword", "")
            if kw and kw not in existing[seen[k]].get("matched_keywords", []):
                existing[seen[k]].setdefault("matched_keywords", [kw])
        else:
            existing.append(item)
            seen[k] = len(existing) - 1
            added += 1
    return existing, added


# ---------------------------------------------------------------------------
# Summary tracking
# ---------------------------------------------------------------------------

def _init_summary() -> dict:
    return {s: {"api_hit_count": 0, "unique_results": 0, "keywords": {}} for s in SURFACES}


def _merge_keyword_counts(summary: dict, surface: str, keyword: str,
                          api_hit: int, unique: int) -> None:
    summary[surface]["api_hit_count"] += api_hit
    summary[surface]["unique_results"] += unique
    kw_entry = summary[surface]["keywords"].setdefault(keyword, {"api_hit_count": 0, "unique_results": 0})
    kw_entry["api_hit_count"] += api_hit
    kw_entry["unique_results"] += unique


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(slug: str, overwrite: bool = False) -> None:
    ensure_dirs(slug)
    dirs = technique_dirs(slug)
    logger = setup_logging(slug, "search")
    search_dir = dirs["search"]
    search_dir.mkdir(parents=True, exist_ok=True)

    history_path = search_dir / "search_history.json"
    summary_path = search_dir / "summary.json"

    # Result files per surface
    surface_files = {s: search_dir / f"{s}.json" for s in SURFACES}

    if overwrite:
        logger.info("--overwrite: resetting all search files")
        for p in [history_path, summary_path] + list(surface_files.values()):
            if p.exists():
                p.unlink()

    history: dict = load_json(history_path, {})
    summary: dict = load_json(summary_path, _init_summary())
    if not summary:
        summary = _init_summary()

    # Load existing surface data
    surface_data: dict[str, list] = {s: load_json(surface_files[s], []) for s in SURFACES}

    keywords = load_search_keywords(slug)
    logger.info(f"Loaded {len(keywords)} search keywords for {slug}")

    pbar = tqdm(keywords, desc="Keywords", unit="kw")
    for keyword in pbar:
        pbar.set_postfix_str(keyword[:40])

        if history.get(keyword) == "done":
            logger.info(f"SKIP (done): {keyword!r}")
            continue

        # Run all surfaces for this keyword
        try:
            # --- code ---
            code_new = _slice_code_search(keyword, logger)
            surface_data["code"], code_added = _dedup(surface_data["code"], code_new)
            _merge_keyword_counts(summary, "code", keyword,
                                  len(code_new), code_added)

            # --- repos ---
            repos_new = _search_repos(keyword, logger)
            surface_data["repos"], repos_added = _dedup(surface_data["repos"], repos_new)
            _merge_keyword_counts(summary, "repos", keyword,
                                  len(repos_new), repos_added)

            # --- issues ---
            issues_new = _search_issues_prs(keyword, "issue", logger)
            surface_data["issues"], issues_added = _dedup(surface_data["issues"], issues_new)
            _merge_keyword_counts(summary, "issues", keyword,
                                  len(issues_new), issues_added)

            # --- prs ---
            prs_new = _search_issues_prs(keyword, "pr", logger)
            surface_data["prs"], prs_added = _dedup(surface_data["prs"], prs_new)
            _merge_keyword_counts(summary, "prs", keyword,
                                  len(prs_new), prs_added)

            # --- commits ---
            commits_new = _search_commits(keyword, logger)
            surface_data["commits"], commits_added = _dedup(surface_data["commits"], commits_new)
            _merge_keyword_counts(summary, "commits", keyword,
                                  len(commits_new), commits_added)

            # --- discussions ---
            disc_new = _search_discussions(keyword, logger)
            surface_data["discussions"], disc_added = _dedup(surface_data["discussions"], disc_new)
            _merge_keyword_counts(summary, "discussions", keyword,
                                  len(disc_new), disc_added)

        except Exception as exc:
            logger.error(f"Error on keyword {keyword!r}: {exc}", exc_info=True)
            # Don't mark as done — will retry on next run
            continue

        # Persist results
        for surface in SURFACES:
            save_json(surface_files[surface], surface_data[surface])
        save_json(summary_path, summary)

        history[keyword] = "done"
        save_json(history_path, history)

    # Final totals log
    for surface in SURFACES:
        counts = summary[surface]
        logger.info(f"FINAL {surface}: api_hit_count={counts['api_hit_count']}, "
                    f"unique_results={counts['unique_results']}")

    print(f"\nSearch complete for {slug}.")
    print(f"  Code:        {summary['code']['unique_results']} results")
    print(f"  Repos:       {summary['repos']['unique_results']} results")
    print(f"  Issues:      {summary['issues']['unique_results']} results")
    print(f"  PRs:         {summary['prs']['unique_results']} results")
    print(f"  Commits:     {summary['commits']['unique_results']} results")
    print(f"  Discussions: {summary['discussions']['unique_results']} results")
