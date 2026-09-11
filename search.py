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

All surfaces use adaptive slicing to bypass GitHub's 1 000-result hard cap:
  - repos / issues / prs / commits / discussions: bisect on `created:` date range
  - code: bisect on `size:` byte range (code search ignores `created:`)

Keywords are read from inputs/<prefix>_search_keywords.txt.
Results are saved to results/<slug>/search/{code,repos,issues,prs,commits,discussions}.json.
Progress is tracked in results/<slug>/search/search_history.json.

Resume: if stopped mid-keyword, that keyword is re-run on the next start.
--overwrite: resets history and all result files.
"""

from __future__ import annotations

import json
import time
from datetime import date, timedelta, datetime
from pathlib import Path

from rich.console import Console

import config as cfg
from utils import (
    resolve_technique, technique_dirs, ensure_dirs,
    setup_logging, load_json, save_json,
    load_search_keywords, gh_get, gh_graphql,
)

console = Console()
SURFACES = ["code", "repos", "issues", "prs", "commits", "discussions"]

# GitHub indexes code files up to ~384 KB; this is our size-slice ceiling.
_CODE_SIZE_MAX = 400_000


# ---------------------------------------------------------------------------
# Leaf fetchers — paginate one query, return all items up to GitHub's 1 000 cap
# ---------------------------------------------------------------------------

def _fetch_code(q: str, logger) -> list[dict]:
    url = f"{cfg.GITHUB_API_BASE}/search/code"
    results, page, total = [], 1, None
    while True:
        data = gh_get(url, params={"q": q, "per_page": cfg.GITHUB_API_PER_PAGE, "page": page},
                      is_code_search=True, logger=logger)
        t = data.get("total_count", 0)
        if total is None:
            total = t
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            repo = item.get("repository", {})
            results.append({
                "id":              item.get("html_url", ""),
                "sha":             item.get("sha", ""),
                "url":             item.get("url", ""),
                "html_url":        item.get("html_url", ""),
                "surface":         "code",
                "file_path":       item.get("path", ""),
                "file_name":       item.get("name", ""),
                "file_size_bytes": item.get("size"),
                "repo_id":         repo.get("id"),
                "repo_full_name":  repo.get("full_name", ""),
                "repo_html_url":   repo.get("html_url", ""),
                "repo_clone_url":  f"https://github.com/{repo.get('full_name', '')}.git",
                "language":        item.get("language") or repo.get("language"),
                "stars":           repo.get("stargazers_count"),
                "matched_keyword": q,
            })
        if page * cfg.GITHUB_API_PER_PAGE >= min(t, 1000):
            break
        page += 1
    logger.info(f"CODE fetch q={q!r}: total_count={total}, retrieved={len(results)}")
    return results, total or 0


def _fetch_repos(q: str, logger) -> tuple[list[dict], int]:
    url = f"{cfg.GITHUB_API_BASE}/search/repositories"
    results, page, total = [], 1, None
    while True:
        data = gh_get(url, params={"q": q, "per_page": cfg.GITHUB_API_PER_PAGE, "page": page},
                      logger=logger)
        t = data.get("total_count", 0)
        if total is None:
            total = t
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
                "archived":       item.get("archived", False),
                "pushed_at":      item.get("pushed_at"),
                "matched_keyword": q,
            })
        if page * cfg.GITHUB_API_PER_PAGE >= min(t, 1000):
            break
        page += 1
    logger.info(f"REPOS fetch q={q!r}: total_count={total}, retrieved={len(results)}")
    return results, total or 0


def _fetch_issues_prs(q: str, kind: str, logger) -> tuple[list[dict], int]:
    url = f"{cfg.GITHUB_API_BASE}/search/issues"
    results, page, total = [], 1, None
    full_q = f"{q} type:{kind}"
    while True:
        data = gh_get(url, params={"q": full_q, "per_page": cfg.GITHUB_API_PER_PAGE, "page": page},
                      logger=logger)
        t = data.get("total_count", 0)
        if total is None:
            total = t
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
                "surface":        "issues" if kind == "issue" else "prs",
                "title":          item.get("title", ""),
                "body":           item.get("body", "") or "",
                "state":          item.get("state"),
                "comment_count":  item.get("comments", 0),
                "created_at":     item.get("created_at"),
                "updated_at":     item.get("updated_at"),
                "closed_at":      item.get("closed_at"),
                "repo_full_name": repo_full_name,
                "author_login":   item.get("user", {}).get("login", ""),
                "labels":         [l.get("name", "") for l in item.get("labels", [])],
                "matched_keyword": q,
            })
        if page * cfg.GITHUB_API_PER_PAGE >= min(t, 1000):
            break
        page += 1
    logger.info(f"{kind.upper()} fetch q={full_q!r}: total_count={total}, retrieved={len(results)}")
    return results, total or 0


def _fetch_commits(q: str, logger) -> tuple[list[dict], int]:
    url = f"{cfg.GITHUB_API_BASE}/search/commits"
    results, page, total = [], 1, None
    while True:
        data = gh_get(url, params={"q": q, "per_page": cfg.GITHUB_API_PER_PAGE, "page": page},
                      delay=cfg.RATE_LIMIT_PAUSE, logger=logger)
        t = data.get("total_count", 0)
        if total is None:
            total = t
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            commit = item.get("commit", {})
            author = commit.get("author", {})
            repo   = item.get("repository", {})
            results.append({
                "id":             item.get("sha", ""),
                "url":            item.get("url", ""),
                "html_url":       item.get("html_url", ""),
                "surface":        "commits",
                "body":           commit.get("message", "") or "",
                "created_at":     commit.get("committer", {}).get("date") or author.get("date"),
                "author_date":    author.get("date"),
                "committer_date": commit.get("committer", {}).get("date"),
                "repo_full_name": repo.get("full_name", ""),
                "repo_id":        repo.get("id"),
                "matched_keyword": q,
            })
        if page * cfg.GITHUB_API_PER_PAGE >= min(t, 1000):
            break
        page += 1
    logger.info(f"COMMITS fetch q={q!r}: total_count={total}, retrieved={len(results)}")
    return results, total or 0


_DISCUSSION_QUERY = """
query($query: String!, $after: String) {
  search(query: $query, type: DISCUSSION, first: 100, after: $after) {
    discussionCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Discussion {
        id number title body createdAt updatedAt url
        comments { totalCount }
        repository { nameWithOwner }
      }
    }
  }
}
"""

_DISCUSSION_PROBE_QUERY = """
query($query: String!) {
  search(query: $query, type: DISCUSSION, first: 1) {
    discussionCount
  }
}
"""


def _probe_discussion_count(q: str, logger) -> int:
    resp = gh_graphql(_DISCUSSION_PROBE_QUERY, {"query": q}, logger=logger)
    if resp.get("errors"):
        if logger:
            logger.warning(f"GraphQL probe errors for {q!r}: {resp['errors']}")
        return 0
    return resp.get("data", {}).get("search", {}).get("discussionCount", 0)


def _fetch_discussions(q: str, logger) -> tuple[list[dict], int]:
    results, cursor, total = [], None, None
    while True:
        resp = gh_graphql(_DISCUSSION_QUERY, {"query": q, "after": cursor}, logger=logger)
        if resp.get("errors"):
            if logger:
                logger.warning(f"GraphQL errors for {q!r}: {resp['errors']}")
            break
        search = resp.get("data", {}).get("search", {})
        if total is None:
            total = search.get("discussionCount", 0)
        for node in search.get("nodes", []):
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
                "matched_keyword": q,
            })
        page_info = search.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    logger.info(f"DISCUSSIONS fetch q={q!r}: total_count={total}, retrieved={len(results)}")
    return results, total or 0


# ---------------------------------------------------------------------------
# Adaptive date-range slicing (repos / issues / prs / commits / discussions)
# ---------------------------------------------------------------------------

def _probe_count(url: str, q: str, logger, is_code: bool = False) -> int:
    data = gh_get(url, params={"q": q, "per_page": 1, "page": 1},
                  is_code_search=is_code, logger=logger)
    return data.get("total_count", 0)


def _sliced_date_search(
    keyword: str,
    fetch_fn,           # _fetch_repos | _fetch_issues_prs (partial) | _fetch_commits
    probe_url: str,
    date_qualifier: str,
    start: str,
    end: str,
    depth: int,
    logger,
    results: list,
    seen: set,
    surface_label: str,
) -> None:
    """
    Recursively bisect [start, end] until each slice fits under SLICE_THRESHOLD.
    fetch_fn(q, logger) -> (list[dict], total_count)
    """
    q = f"{keyword} {date_qualifier}:{start}..{end}"
    total = _probe_count(probe_url, q, logger)
    indent = "  " * depth
    console.print(f"{indent}[dim]{start}..{end}[/]  total={total}")

    if total == 0:
        return

    start_d = date.fromisoformat(start)
    end_d   = date.fromisoformat(end)
    span    = (end_d - start_d).days

    if total <= cfg.SLICE_THRESHOLD or depth >= cfg.SLICE_MAX_DEPTH or span < cfg.SLICE_MIN_DAYS:
        items, _ = fetch_fn(q, logger)
        if total > 1000:
            console.print(f"{indent}  [yellow]⚠ slice still >{1000} (total={total}), got {len(items)}[/]")
        for item in items:
            key = (item.get("id") or item.get("sha") or item.get("url", ""), surface_label)
            if key not in seen:
                seen.add(key)
                results.append(item)
        return

    mid   = start_d + timedelta(days=span // 2)
    next_ = mid + timedelta(days=1)
    console.print(f"{indent}[yellow]↳ slicing (total={total} > {cfg.SLICE_THRESHOLD})[/]")
    _sliced_date_search(keyword, fetch_fn, probe_url, date_qualifier,
                        start, mid.isoformat(), depth + 1, logger, results, seen, surface_label)
    _sliced_date_search(keyword, fetch_fn, probe_url, date_qualifier,
                        next_.isoformat(), end, depth + 1, logger, results, seen, surface_label)


def _sliced_discussion_search(
    keyword: str,
    start: str,
    end: str,
    depth: int,
    logger,
    results: list,
    seen: set,
) -> None:
    """
    Recursively bisect [start, end] for discussions until each slice fits under SLICE_THRESHOLD.
    Uses _probe_discussion_count (GraphQL discussionCount) for probing.
    """
    q = f"{keyword} created:{start}..{end}"
    total = _probe_discussion_count(q, logger)
    indent = "  " * depth
    console.print(f"{indent}[dim]{start}..{end}[/]  total={total}")

    if total == 0:
        return

    start_d = date.fromisoformat(start)
    end_d   = date.fromisoformat(end)
    span    = (end_d - start_d).days

    if total <= cfg.SLICE_THRESHOLD or depth >= cfg.SLICE_MAX_DEPTH or span < cfg.SLICE_MIN_DAYS:
        items, _ = _fetch_discussions(q, logger)
        if total > 1000:
            console.print(f"{indent}  [yellow]⚠ slice still >{1000} (total={total}), got {len(items)}[/]")
        for item in items:
            key = item.get("id", "")
            if key not in seen:
                seen.add(key)
                results.append(item)
        return

    mid   = start_d + timedelta(days=span // 2)
    next_ = mid + timedelta(days=1)
    console.print(f"{indent}[yellow]↳ slicing (total={total} > {cfg.SLICE_THRESHOLD})[/]")
    _sliced_discussion_search(keyword, start, mid.isoformat(), depth + 1, logger, results, seen)
    _sliced_discussion_search(keyword, next_.isoformat(), end, depth + 1, logger, results, seen)


# ---------------------------------------------------------------------------
# Adaptive size-range slicing (code search only — no date qualifier support)
# ---------------------------------------------------------------------------

def _sliced_code_search(
    keyword: str,
    size_min: int,
    size_max: int,
    logger,
    results: list,
    seen: set,
) -> None:
    """
    Recursively bisect [size_min, size_max] until each slice fits under SLICE_THRESHOLD.
    No depth cap — only stops when byte range < 2 (can't split further).
    """
    q = f"{keyword} size:{size_min}..{size_max}"
    total = _probe_count(f"{cfg.GITHUB_API_BASE}/search/code", q, logger, is_code=True)
    console.print(f"    [dim]size:{size_min}..{size_max}[/]  total={total}")

    if total == 0:
        return

    if total <= cfg.SLICE_THRESHOLD or (size_max - size_min) < 2:
        items, _ = _fetch_code(q, logger)
        if total > 1000:
            console.print(f"    [yellow]⚠ size range exhausted (total={total}), got {len(items)}[/]")
        for item in items:
            key = item.get("html_url") or f"{item.get('repo_full_name','')}:{item.get('file_path','')}"
            if key not in seen:
                seen.add(key)
                results.append(item)
        return

    mid = (size_min + size_max) // 2
    console.print(f"    [yellow]↳ slicing size (total={total} > {cfg.SLICE_THRESHOLD})[/]")
    _sliced_code_search(keyword, size_min, mid,       logger, results, seen)
    _sliced_code_search(keyword, mid + 1,  size_max,  logger, results, seen)


def search_code_sliced(keyword: str, logger) -> tuple[list[dict], int]:
    """Returns (results, total_count_from_probe)."""
    total = _probe_count(f"{cfg.GITHUB_API_BASE}/search/code", keyword, logger, is_code=True)
    console.print(f"  [blue]code[/] total_count={total}")
    if total == 0:
        return [], 0
    if total <= cfg.SLICE_THRESHOLD:
        items, _ = _fetch_code(keyword, logger)
        return items, total
    console.print(f"  [yellow]→ size-slicing (0..{_CODE_SIZE_MAX} bytes)[/]")
    results: list[dict] = []
    seen: set[str] = set()
    _sliced_code_search(keyword, 0, _CODE_SIZE_MAX, logger, results, seen)
    console.print(f"  [green]code done:[/] {len(results)} unique (total_count was {total})")
    return results, total


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedup(existing: list[dict], new_items: list[dict], key: str = "id") -> tuple[list[dict], int]:
    seen: dict[str, int] = {str(r[key]): i for i, r in enumerate(existing) if r.get(key)}
    added = 0
    for item in new_items:
        k = str(item.get(key, ""))
        if not k:
            existing.append(item)
            added += 1
        elif k not in seen:
            kw = item.get("matched_keyword", "")
            if kw:
                item.setdefault("matched_keywords", [kw])
            existing.append(item)
            seen[k] = len(existing) - 1
            added += 1
        else:
            kw = item.get("matched_keyword", "")
            if kw and kw not in existing[seen[k]].get("matched_keywords", []):
                existing[seen[k]].setdefault("matched_keywords", []).append(kw)
    return existing, added


# ---------------------------------------------------------------------------
# Summary tracking
# ---------------------------------------------------------------------------

def _init_summary() -> dict:
    return {s: {"api_hit_count": 0, "unique_results": 0, "keywords": {}} for s in SURFACES}


def _merge_counts(summary: dict, surface: str, keyword: str, api_hit: int, unique: int) -> None:
    summary[surface]["api_hit_count"] += api_hit
    summary[surface]["unique_results"] += unique
    e = summary[surface]["keywords"].setdefault(keyword, {"api_hit_count": 0, "unique_results": 0})
    e["api_hit_count"] += api_hit
    e["unique_results"] += unique


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
    surface_files = {s: search_dir / f"{s}.json" for s in SURFACES}

    if overwrite:
        logger.info("--overwrite: resetting all search files")
        console.print("[yellow]--overwrite: resetting search files[/]")
        for p in [history_path, summary_path] + list(surface_files.values()):
            if p.exists():
                p.unlink()

    history: dict = load_json(history_path, {})
    summary: dict = load_json(summary_path, _init_summary()) or _init_summary()
    surface_data: dict[str, list] = {s: load_json(surface_files[s], []) for s in SURFACES}

    keywords = load_search_keywords(slug)
    logger.info(f"Loaded {len(keywords)} search keywords for {slug}")
    console.print(f"[bold]Loaded {len(keywords)} keywords for [cyan]{slug}[/][/]")

    repos_url   = f"{cfg.GITHUB_API_BASE}/search/repositories"
    issues_url  = f"{cfg.GITHUB_API_BASE}/search/issues"
    commits_url = f"{cfg.GITHUB_API_BASE}/search/commits"

    for idx, keyword in enumerate(keywords, 1):
        if history.get(keyword) == "done":
            console.print(f"[dim][{idx}/{len(keywords)}] SKIP {keyword!r}[/]")
            continue

        console.rule(f"[bold cyan][{idx}/{len(keywords)}] {keyword}")
        logger.info(f'KEYWORD STARTED: "{keyword}"')

        try:
            # ── code (size-based slicing) ──────────────────────────────────
            console.print("[bold]code[/]")
            code_new, code_total = search_code_sliced(keyword, logger)
            logger.info(f'KEYWORD SURFACE: "{keyword}" | CODE | total_count={code_total}')
            surface_data["code"], code_added = _dedup(surface_data["code"], code_new)
            save_json(surface_files["code"], surface_data["code"])
            console.print(f"  → {keyword!r} CODE saved: {code_added} new (total on disk: {len(surface_data['code'])})")
            logger.info(f'KEYWORD SURFACE SAVED: "{keyword}" | CODE | new={code_added} | total_on_disk={len(surface_data["code"])}')
            _merge_counts(summary, "code", keyword, code_total, code_added)

            # ── repos (date-based slicing) ─────────────────────────────────
            console.print("[bold]repos[/]")
            total_repos = _probe_count(repos_url, keyword, logger)
            logger.info(f'KEYWORD SURFACE: "{keyword}" | REPOS | total_count={total_repos}')
            console.print(f"  total_count={total_repos}")
            repos_results: list[dict] = []
            repos_seen: set = set()
            if total_repos <= cfg.SLICE_THRESHOLD:
                items, _ = _fetch_repos(keyword, logger)
                repos_results = items
            else:
                console.print(f"  [yellow]→ date-slicing repos[/]")
                _sliced_date_search(keyword, _fetch_repos, repos_url, "created",
                                    cfg.SLICE_START_DATE, cfg.SLICE_END_DATE,
                                    0, logger, repos_results, repos_seen, "repos")
            surface_data["repos"], repos_added = _dedup(surface_data["repos"], repos_results)
            save_json(surface_files["repos"], surface_data["repos"])
            console.print(f"  → {keyword!r} REPOS saved: {repos_added} new (total on disk: {len(surface_data['repos'])})")
            logger.info(f'KEYWORD SURFACE SAVED: "{keyword}" | REPOS | new={repos_added} | total_on_disk={len(surface_data["repos"])}')
            _merge_counts(summary, "repos", keyword, total_repos, repos_added)

            # ── issues (date-based slicing) ────────────────────────────────
            console.print("[bold]issues[/]")
            issue_kw = f"{keyword} type:issue"
            total_issues = _probe_count(issues_url, issue_kw, logger)
            logger.info(f'KEYWORD SURFACE: "{keyword}" | ISSUES | total_count={total_issues}')
            console.print(f"  total_count={total_issues}")
            issues_results: list[dict] = []
            issues_seen: set = set()
            if total_issues <= cfg.SLICE_THRESHOLD:
                items, _ = _fetch_issues_prs(keyword, "issue", logger)
                issues_results = items
            else:
                console.print(f"  [yellow]→ date-slicing issues[/]")
                _sliced_date_search(
                    f"{keyword} type:issue",
                    lambda q, lg: _fetch_issues_prs(q.replace(" type:issue", ""), "issue", lg),
                    issues_url, "created",
                    cfg.SLICE_START_DATE, cfg.SLICE_END_DATE,
                    0, logger, issues_results, issues_seen, "issues")
            surface_data["issues"], issues_added = _dedup(surface_data["issues"], issues_results)
            save_json(surface_files["issues"], surface_data["issues"])
            console.print(f"  → {keyword!r} ISSUES saved: {issues_added} new (total on disk: {len(surface_data['issues'])})")
            logger.info(f'KEYWORD SURFACE SAVED: "{keyword}" | ISSUES | new={issues_added} | total_on_disk={len(surface_data["issues"])}')
            _merge_counts(summary, "issues", keyword, total_issues, issues_added)

            # ── prs (date-based slicing) ───────────────────────────────────
            console.print("[bold]prs[/]")
            pr_kw = f"{keyword} type:pr"
            total_prs = _probe_count(issues_url, pr_kw, logger)
            logger.info(f'KEYWORD SURFACE: "{keyword}" | PRS | total_count={total_prs}')
            console.print(f"  total_count={total_prs}")
            prs_results: list[dict] = []
            prs_seen: set = set()
            if total_prs <= cfg.SLICE_THRESHOLD:
                items, _ = _fetch_issues_prs(keyword, "pr", logger)
                prs_results = items
            else:
                console.print(f"  [yellow]→ date-slicing prs[/]")
                _sliced_date_search(
                    f"{keyword} type:pr",
                    lambda q, lg: _fetch_issues_prs(q.replace(" type:pr", ""), "pr", lg),
                    issues_url, "created",
                    cfg.SLICE_START_DATE, cfg.SLICE_END_DATE,
                    0, logger, prs_results, prs_seen, "prs")
            surface_data["prs"], prs_added = _dedup(surface_data["prs"], prs_results)
            save_json(surface_files["prs"], surface_data["prs"])
            console.print(f"  → {keyword!r} PRS saved: {prs_added} new (total on disk: {len(surface_data['prs'])})")
            logger.info(f'KEYWORD SURFACE SAVED: "{keyword}" | PRS | new={prs_added} | total_on_disk={len(surface_data["prs"])}')
            _merge_counts(summary, "prs", keyword, total_prs, prs_added)

            # ── commits (date-based slicing) ───────────────────────────────
            console.print("[bold]commits[/]")
            total_commits = _probe_count(commits_url, keyword, logger)
            logger.info(f'KEYWORD SURFACE: "{keyword}" | COMMITS | total_count={total_commits}')
            console.print(f"  total_count={total_commits}")
            commits_results: list[dict] = []
            commits_seen: set = set()
            if total_commits <= cfg.SLICE_THRESHOLD:
                items, _ = _fetch_commits(keyword, logger)
                commits_results = items
            else:
                console.print(f"  [yellow]→ date-slicing commits[/]")
                _sliced_date_search(keyword, _fetch_commits, commits_url, "committer-date",
                                    cfg.SLICE_START_DATE, cfg.SLICE_END_DATE,
                                    0, logger, commits_results, commits_seen, "commits")
            surface_data["commits"], commits_added = _dedup(surface_data["commits"], commits_results)
            save_json(surface_files["commits"], surface_data["commits"])
            console.print(f"  → {keyword!r} COMMITS saved: {commits_added} new (total on disk: {len(surface_data['commits'])})")
            logger.info(f'KEYWORD SURFACE SAVED: "{keyword}" | COMMITS | new={commits_added} | total_on_disk={len(surface_data["commits"])}')
            _merge_counts(summary, "commits", keyword, total_commits, commits_added)

            # ── discussions (date-based slicing via GraphQL) ──────────────
            console.print("[bold]discussions[/]")
            disc_total = _probe_discussion_count(keyword, logger)
            logger.info(f'KEYWORD SURFACE: "{keyword}" | DISCUSSIONS | total_count={disc_total}')
            console.print(f"  total_count={disc_total}")
            disc_results: list[dict] = []
            disc_seen: set = set()
            if disc_total <= cfg.SLICE_THRESHOLD:
                disc_results, _ = _fetch_discussions(keyword, logger)
            else:
                console.print(f"  [yellow]→ date-slicing discussions[/]")
                _sliced_discussion_search(keyword, cfg.SLICE_START_DATE, cfg.SLICE_END_DATE,
                                          0, logger, disc_results, disc_seen)
            surface_data["discussions"], disc_added = _dedup(surface_data["discussions"], disc_results)
            save_json(surface_files["discussions"], surface_data["discussions"])
            console.print(f"  → {keyword!r} DISCUSSIONS saved: {disc_added} new (total on disk: {len(surface_data['discussions'])})")
            logger.info(f'KEYWORD SURFACE SAVED: "{keyword}" | DISCUSSIONS | new={disc_added} | total_on_disk={len(surface_data["discussions"])}')
            _merge_counts(summary, "discussions", keyword, disc_total, disc_added)

        except Exception as exc:
            logger.error(f"Error on keyword {keyword!r}: {exc}", exc_info=True)
            console.print(f"[red]ERROR on {keyword!r}: {exc}[/]")
            continue

        # Persist summary and history after every keyword
        save_json(summary_path, summary)
        history[keyword] = "done"
        save_json(history_path, history)
        logger.info(f'KEYWORD DONE: "{keyword}"')

        console.print(
            f"[green]✓[/] code={code_added}  repos={repos_added}  "
            f"issues={issues_added}  prs={prs_added}  "
            f"commits={commits_added}  disc={disc_added}"
        )

    # Final summary
    console.rule("[bold]Search complete")
    for surface in SURFACES:
        c = summary[surface]
        console.print(
            f"  {surface:<12}  api_hits={c['api_hit_count']:>6}  "
            f"unique={c['unique_results']:>6}"
        )
        logger.info(f"FINAL {surface}: api_hit_count={c['api_hit_count']}, "
                    f"unique_results={c['unique_results']}")
