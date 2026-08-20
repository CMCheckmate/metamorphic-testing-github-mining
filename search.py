"""
Phase 1 — GitHub Search
========================
Searches GitHub across five surfaces for metamorphic testing adoption:

  Surface            Endpoint                    Rate limit (auth)
  ─────────────────  ──────────────────────────  ─────────────────
  Repositories       /search/repositories        30 req/min
  Code files         /search/code                 9 req/min (separate bucket)
  Issues & PRs       /search/issues              30 req/min
  Commit messages    /search/commits             30 req/min
  Discussions        GraphQL search()            5,000 pts/hr

All searches with total_count > SLICE_THRESHOLD (default 900) are automatically
split by date range and recursed until each slice fits under the 1,000-result
hard cap, giving full coverage instead of a truncated first-1,000 sample.

Usage:
    python search.py [--repo] [--code] [--issues] [--commits] [--discussions]
                     [--max-pages N] [--no-slice]

    Pass one or more surface flags to run only those; omit all to run everything.
    --max-pages N   Cap pages per individual query/slice (default: 10)
    --no-slice      Disable date-range slicing (faster, misses >1k results)

Output files (results/raw/):
    repos.json        — deduplicated repository records
    code.json         — deduplicated code-file match records
    issues.json       — deduplicated issue records
    prs.json          — deduplicated pull request records
    commits.json      — deduplicated commit records
    discussions.json  — deduplicated discussion records
    summary.json      — per-query hit counts + timestamp
"""

import argparse
import json
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import requests
from rich.console import Console
from rich.table import Table

from config import (
    GITHUB_TOKEN,
    GITHUB_API_BASE,
    GITHUB_GRAPHQL_URL,
    RESULTS_DIR,
    REPO_QUERIES,
    CODE_QUERIES,
    ISSUE_QUERIES,
    COMMIT_QUERIES,
    DISCUSSION_QUERIES,
    STANDARD_SEARCH_DELAY,
    CODE_SEARCH_DELAY,
    GRAPHQL_DELAY,
    SLICE_THRESHOLD,
    SLICE_MAX_DEPTH,
    SLICE_MIN_DAYS,
    SLICE_START_DATE,
    SLICE_END_DATE,
)

console = Console()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _headers(accept: str = "application/vnd.github+json") -> dict:
    if not GITHUB_TOKEN:
        console.print(
            "[bold red]Warning:[/] GITHUB_TOKEN not set. "
            "Unauthenticated: 10 req/min (standard), code search unavailable."
        )
    h = {
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _get(url: str, params: dict | None = None, delay: float = STANDARD_SEARCH_DELAY) -> dict:
    """GET with retry on 403/429 (rate limit).  Sleeps `delay` seconds before each call."""
    time.sleep(delay)
    for attempt in range(4):
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (403, 429):
            retry_after = int(resp.headers.get("Retry-After", 60))
            console.print(
                f"  [yellow]Rate limited (HTTP {resp.status_code}) — "
                f"sleeping {retry_after}s (attempt {attempt+1}/4)[/]"
            )
            time.sleep(retry_after)
        elif resp.status_code == 422:
            # Unprocessable — query too complex or date slice empty; treat as empty
            return {}
        else:
            console.print(f"  [red]HTTP {resp.status_code}[/] {url}: {resp.text[:200]}")
            return {}
    return {}


def _graphql(query: str, variables: dict | None = None) -> dict:
    """POST a GraphQL query and return the response data dict."""
    time.sleep(GRAPHQL_DELAY)
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(
        GITHUB_GRAPHQL_URL,
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code == 200:
        body = resp.json()
        if "errors" in body:
            console.print(f"  [yellow]GraphQL errors:[/] {body['errors']}")
        return body.get("data", {})
    if resp.status_code in (403, 429):
        retry_after = int(resp.headers.get("Retry-After", 60))
        console.print(f"  [yellow]GraphQL rate limited — sleeping {retry_after}s[/]")
        time.sleep(retry_after)
    else:
        console.print(f"  [red]GraphQL HTTP {resp.status_code}[/]: {resp.text[:200]}")
    return {}


# ---------------------------------------------------------------------------
# Adaptive date-range slicing
# ---------------------------------------------------------------------------

def _date_slices(start: str, end: str, depth: int = 0) -> list[tuple[str, str]]:
    """
    Return a list of (start, end) date pairs covering [start, end].
    At depth 0 this is just [(start, end)] — slicing is triggered lazily
    by _sliced_search once it sees total_count > SLICE_THRESHOLD.
    """
    return [(start, end)]


def _fetch_all_pages(
    url: str,
    base_params: dict,
    delay: float,
    max_pages: int,
    transform_fn,
) -> tuple[list[dict], int]:
    """
    Page through a search endpoint until exhausted or max_pages reached.
    Returns (records, total_count_from_first_page).
    transform_fn(item) converts a raw API item to our record dict.
    """
    records: list[dict] = []
    total_count = 0

    for page in range(1, max_pages + 1):
        params = {**base_params, "per_page": 100, "page": page}
        data = _get(url, params=params, delay=delay if page > 1 else 0)
        if not data:
            break
        items = data.get("items", [])
        if page == 1:
            total_count = data.get("total_count", 0)
        if not items:
            break
        for item in items:
            r = transform_fn(item)
            if r:
                records.append(r)
        if len(items) < 100 or page * 100 >= min(total_count, 1000):
            break

    return records, total_count


def _sliced_search(
    url: str,
    base_q: str,
    extra_params: dict,
    delay: float,
    max_pages: int,
    transform_fn,
    date_qualifier: str,       # "created" | "committer-date" | "author-date"
    start: str,
    end: str,
    depth: int = 0,
    enable_slicing: bool = True,
) -> list[dict]:
    """
    Run a search for [start, end].  If total_count > SLICE_THRESHOLD and
    depth < SLICE_MAX_DEPTH and the window is wide enough, bisect and recurse.
    Returns a flat list of records.
    """
    q = f"{base_q} {date_qualifier}:{start}..{end}"
    params = {"q": q, **extra_params}
    records, total_count = _fetch_all_pages(url, params, delay, max_pages, transform_fn)

    indent = "  " * depth
    console.print(
        f"{indent}[dim]{start}..{end}[/]  total={total_count}  retrieved={len(records)}"
    )

    if (
        enable_slicing
        and total_count > SLICE_THRESHOLD
        and depth < SLICE_MAX_DEPTH
    ):
        start_d = date.fromisoformat(start)
        end_d   = date.fromisoformat(end)
        span    = (end_d - start_d).days

        if span >= SLICE_MIN_DAYS:
            mid_d  = start_d + timedelta(days=span // 2)
            mid    = mid_d.isoformat()
            next_d = (mid_d + timedelta(days=1)).isoformat()
            console.print(f"{indent}[yellow]↳ slicing (total={total_count} > {SLICE_THRESHOLD})[/]")
            left  = _sliced_search(url, base_q, extra_params, delay, max_pages,
                                   transform_fn, date_qualifier, start, mid,
                                   depth + 1, enable_slicing)
            right = _sliced_search(url, base_q, extra_params, delay, max_pages,
                                   transform_fn, date_qualifier, next_d, end,
                                   depth + 1, enable_slicing)
            return left + right

    return records


# ---------------------------------------------------------------------------
# Transform functions — raw API item → our record dict
# ---------------------------------------------------------------------------

def _repo_transform(item: dict) -> dict:
    return {
        "id":             item["id"],
        "full_name":      item["full_name"],
        "html_url":       item["html_url"],
        "clone_url":      item["clone_url"],
        "description":    item.get("description") or "",
        "language":       item.get("language") or "",
        "topics":         item.get("topics", []),
        "stars":          item["stargazers_count"],
        "forks":          item["forks_count"],
        "size_kb":        item["size"],
        "pushed_at":      item["pushed_at"],
        "created_at":     item["created_at"],
        "default_branch": item["default_branch"],
        "is_fork":        item["fork"],
        "license":        (item.get("license") or {}).get("spdx_id", ""),
    }


def _code_transform(item: dict) -> dict:
    repo = item["repository"]
    return {
        "repo_id":        repo["id"],
        "repo_full_name": repo["full_name"],
        "repo_html_url":  repo["html_url"],
        "repo_clone_url": f"https://github.com/{repo['full_name']}.git",
        "file_path":      item["path"],
        "file_url":       item["html_url"],
        "file_name":      item["name"],
        "file_sha":       item["sha"],
    }


def _issue_transform(item: dict) -> dict:
    repo_url = item.get("repository_url", "")
    full_name = "/".join(repo_url.rstrip("/").split("/")[-2:]) if repo_url else ""
    return {
        "id":             item["id"],
        "number":         item["number"],
        "title":          item.get("title", ""),
        "html_url":       item["html_url"],
        "repo_full_name": full_name,
        "repo_clone_url": f"https://github.com/{full_name}.git" if full_name else "",
        "state":          item.get("state", ""),
        "created_at":     item.get("created_at", ""),
        "updated_at":     item.get("updated_at", ""),
        "comments":       item.get("comments", 0),
        "kind":           "pr" if "pull_request" in item else "issue",
        "user_login":     (item.get("user") or {}).get("login", ""),
        "body_excerpt":   (item.get("body") or "")[:500],
    }


def _commit_transform(item: dict) -> dict:
    repo = item.get("repository", {})
    commit = item.get("commit", {})
    author = commit.get("author", {})
    return {
        "sha":            item["sha"],
        "html_url":       item["html_url"],
        "repo_full_name": repo.get("full_name", ""),
        "repo_clone_url": f"https://github.com/{repo.get('full_name','')}.git",
        "repo_html_url":  repo.get("html_url", ""),
        "message":        commit.get("message", "")[:500],
        "author_name":    author.get("name", ""),
        "author_date":    author.get("date", ""),
    }


# ---------------------------------------------------------------------------
# Search functions — one per surface
# ---------------------------------------------------------------------------

def search_repositories(queries: list[dict], max_pages: int, enable_slicing: bool) -> list[dict]:
    url = f"{GITHUB_API_BASE}/search/repositories"
    all_records: list[dict] = []
    summary: list[dict] = []

    for q in queries:
        console.print(f"\n[bold cyan]repo:[/] {q['query']}  ({q['label']})")
        before = len(all_records)

        if enable_slicing:
            recs = _sliced_search(
                url, q["query"], {"sort": "stars", "order": "desc"},
                STANDARD_SEARCH_DELAY, max_pages, _repo_transform,
                "created", SLICE_START_DATE, SLICE_END_DATE,
            )
        else:
            recs, _ = _fetch_all_pages(
                url, {"q": q["query"], "sort": "stars", "order": "desc"},
                STANDARD_SEARCH_DELAY, max_pages, _repo_transform,
            )

        for rec in recs:
            rec["matched_query"] = q["query"]
            rec["matched_label"] = q["label"]
        all_records.extend(recs)
        summary.append({"type": "repo", **q, "hits": len(recs)})
        console.print(f"  → {len(recs)} records for this query")

    return all_records, summary


def search_code(queries: list[dict], max_pages: int, enable_slicing: bool) -> list[dict]:
    url = f"{GITHUB_API_BASE}/search/code"
    all_records: list[dict] = []
    summary: list[dict] = []

    for q in queries:
        base_q = q["query"]
        if q.get("lang"):
            base_q += f" language:{q['lang']}"
        console.print(f"\n[bold cyan]code:[/] {q['query']}"
                      + (f"  lang={q['lang']}" if q.get("lang") else "")
                      + f"  ({q['label']})")

        # Code search doesn't support date qualifiers on the file itself,
        # but does accept repo creation date via `created:` on the repo qualifier.
        # We slice on the repo's created date as a proxy.
        if enable_slicing:
            recs = _sliced_search(
                url, base_q, {},
                CODE_SEARCH_DELAY, max_pages, _code_transform,
                "created", SLICE_START_DATE, SLICE_END_DATE,
            )
        else:
            recs, _ = _fetch_all_pages(
                url, {"q": base_q},
                CODE_SEARCH_DELAY, max_pages, _code_transform,
            )

        for rec in recs:
            rec["matched_query"] = q["query"]
            rec["matched_label"] = q["label"]
        all_records.extend(recs)
        summary.append({"type": "code", **q, "hits": len(recs)})
        console.print(f"  → {len(recs)} records for this query")

    return all_records, summary


def search_issues(queries: list[dict], max_pages: int, enable_slicing: bool) -> tuple[list[dict], list[dict], list[dict]]:
    url = f"{GITHUB_API_BASE}/search/issues"
    all_issues: list[dict] = []
    all_prs: list[dict] = []
    summary: list[dict] = []

    for q in queries:
        kind = q.get("kind", "issue")
        base_q = f"{q['query']} is:{kind}"
        console.print(f"\n[bold cyan]{kind}:[/] {q['query']}  ({q['label']})")

        if enable_slicing:
            recs = _sliced_search(
                url, base_q, {"sort": "updated", "order": "desc"},
                STANDARD_SEARCH_DELAY, max_pages, _issue_transform,
                "created", SLICE_START_DATE, SLICE_END_DATE,
            )
        else:
            recs, _ = _fetch_all_pages(
                url, {"q": base_q, "sort": "updated", "order": "desc"},
                STANDARD_SEARCH_DELAY, max_pages, _issue_transform,
            )

        for rec in recs:
            rec["matched_query"] = q["query"]
            rec["matched_label"] = q["label"]
        if kind == "pr":
            all_prs.extend(recs)
        else:
            all_issues.extend(recs)
        summary.append({"type": kind, **q, "hits": len(recs)})
        console.print(f"  → {len(recs)} records for this query")

    return all_issues, all_prs, summary


def search_commits(queries: list[dict], max_pages: int, enable_slicing: bool) -> tuple[list[dict], list[dict]]:
    url = f"{GITHUB_API_BASE}/search/commits"
    all_records: list[dict] = []
    summary: list[dict] = []

    for q in queries:
        console.print(f"\n[bold cyan]commit:[/] {q['query']}  ({q['label']})")

        if enable_slicing:
            recs = _sliced_search(
                url, q["query"], {"sort": "committer-date", "order": "desc"},
                STANDARD_SEARCH_DELAY, max_pages, _commit_transform,
                "committer-date", SLICE_START_DATE, SLICE_END_DATE,
            )
        else:
            recs, _ = _fetch_all_pages(
                url, {"q": q["query"], "sort": "committer-date", "order": "desc"},
                STANDARD_SEARCH_DELAY, max_pages, _commit_transform,
            )

        for rec in recs:
            rec["matched_query"] = q["query"]
            rec["matched_label"] = q["label"]
        all_records.extend(recs)
        summary.append({"type": "commit", **q, "hits": len(recs)})
        console.print(f"  → {len(recs)} records for this query")

    return all_records, summary


# ---------------------------------------------------------------------------
# GraphQL — Discussions
# ---------------------------------------------------------------------------

_DISCUSSION_GQL = """
query($q: String!, $after: String) {
  search(query: $q, type: DISCUSSION, first: 100, after: $after) {
    discussionCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Discussion {
        id
        number
        title
        url
        createdAt
        updatedAt
        upvoteCount
        comments { totalCount }
        category { name }
        repository {
          nameWithOwner
          url
        }
        bodyText
      }
    }
  }
}
"""


def search_discussions(queries: list[str], max_pages: int) -> tuple[list[dict], list[dict]]:
    all_records: list[dict] = []
    summary: list[dict] = []

    if not GITHUB_TOKEN:
        console.print("[yellow]Discussions search skipped — GITHUB_TOKEN required for GraphQL.[/]")
        return all_records, summary

    for q_str in queries:
        console.print(f"\n[bold cyan]discussion:[/] {q_str}")
        records: list[dict] = []
        cursor = None
        pages = 0

        while pages < max_pages:
            data = _graphql(_DISCUSSION_GQL, {"q": q_str, "after": cursor})
            search_data = data.get("search", {})
            nodes = search_data.get("nodes", [])
            page_info = search_data.get("pageInfo", {})
            total = search_data.get("discussionCount", 0)

            for node in nodes:
                if not node:
                    continue
                repo = node.get("repository") or {}
                records.append({
                    "id":              node.get("id", ""),
                    "number":          node.get("number", 0),
                    "title":           node.get("title", ""),
                    "url":             node.get("url", ""),
                    "repo_full_name":  repo.get("nameWithOwner", ""),
                    "repo_clone_url":  f"https://github.com/{repo.get('nameWithOwner','')}.git",
                    "category":        (node.get("category") or {}).get("name", ""),
                    "created_at":      node.get("createdAt", ""),
                    "upvotes":         node.get("upvoteCount", 0),
                    "comment_count":   (node.get("comments") or {}).get("totalCount", 0),
                    "body_excerpt":    (node.get("bodyText") or "")[:500],
                    "matched_query":   q_str,
                    "matched_label":   q_str,
                    "matched_queries": [q_str],
                })

            pages += 1
            console.print(f"  page {pages} — {len(records)} so far (discussionCount={total})")

            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        all_records.extend(records)
        summary.append({"type": "discussion", "query": q_str, "label": "discussion", "hits": len(records)})
        console.print(f"  → {len(records)} records for this query")

    return all_records, summary


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedup_merge(records: list[dict], key_fn) -> list[dict]:
    """Deduplicate records by key, merging matched_queries and matched_labels across duplicates."""
    seen: dict = {}
    order: list = []
    for r in records:
        k  = key_fn(r)
        q  = r.get("matched_query", "")
        lbl = r.get("matched_label", q)
        qs  = r.get("matched_queries", [q] if q else [])
        ls  = r.get("matched_labels",  [lbl] if lbl else [])
        if k not in seen:
            rec = dict(r)
            rec["matched_queries"] = list(qs)
            rec["matched_labels"]  = list(ls)
            seen[k] = rec
            order.append(k)
        else:
            for q_item in qs:
                if q_item and q_item not in seen[k]["matched_queries"]:
                    seen[k]["matched_queries"].append(q_item)
            for l_item in ls:
                if l_item and l_item not in seen[k]["matched_labels"]:
                    seen[k]["matched_labels"].append(l_item)
    return [seen[k] for k in order]


def dedup_repos(recs):    return _dedup_merge(recs, lambda r: r["id"])
def dedup_code(recs):     return _dedup_merge(recs, lambda r: f"{r['repo_id']}:{r['file_sha']}")
def dedup_issues(recs):   return _dedup_merge(recs, lambda r: r["id"])
def dedup_commits(recs):  return _dedup_merge(recs, lambda r: r["sha"])
def dedup_discuss(recs):  return _dedup_merge(recs, lambda r: r["id"])


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def print_summary(all_summary: list[dict]) -> None:
    table = Table(title="Search Summary", show_lines=True)
    table.add_column("Surface", style="cyan",  no_wrap=True)
    table.add_column("Query",   style="white")
    table.add_column("Label",   style="dim")
    table.add_column("Hits",    justify="right", style="green")
    for row in all_summary:
        table.add_row(row.get("type",""), row.get("query",""), row.get("label",""), str(row.get("hits",0)))
    console.print(table)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _write(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def run(
    do_repos: bool,
    do_code: bool,
    do_issues: bool,
    do_commits: bool,
    do_discussions: bool,
    max_pages: int,
    enable_slicing: bool,
) -> None:
    raw = RESULTS_DIR / "raw"
    all_summary: list[dict] = []

    repos = issues = prs = commits = discussions = []
    code: list[dict] = []

    if do_repos:
        console.rule("[bold blue]Repositories[/]")
        repos, s = search_repositories(REPO_QUERIES, max_pages, enable_slicing)
        repos = dedup_repos(repos)
        all_summary.extend(s)

    if do_code:
        console.rule("[bold blue]Code files[/]")
        code_raw, s = search_code(CODE_QUERIES, max_pages, enable_slicing)
        code = dedup_code(code_raw)
        all_summary.extend(s)

    if do_issues:
        console.rule("[bold blue]Issues & Pull Requests[/]")
        raw_issues, raw_prs, s = search_issues(ISSUE_QUERIES, max_pages, enable_slicing)
        issues = dedup_issues(raw_issues)
        prs    = dedup_issues(raw_prs)
        all_summary.extend(s)

    if do_commits:
        console.rule("[bold blue]Commits[/]")
        raw_commits, s = search_commits(COMMIT_QUERIES, max_pages, enable_slicing)
        commits = dedup_commits(raw_commits)
        all_summary.extend(s)

    if do_discussions:
        console.rule("[bold blue]Discussions (GraphQL)[/]")
        raw_disc, s = search_discussions(DISCUSSION_QUERIES, max_pages)
        discussions = dedup_discuss(raw_disc)
        all_summary.extend(s)

    # Write outputs
    _write(raw / "repos.json",       repos)
    _write(raw / "code.json",        code)
    _write(raw / "issues.json",      issues)
    _write(raw / "prs.json",         prs)
    _write(raw / "commits.json",     commits)
    _write(raw / "discussions.json", discussions)
    _write(raw / "summary.json", {
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "slicing_enabled":   enable_slicing,
        "repos":             len(repos),
        "code_files":        len(code),
        "issues":            len(issues),
        "prs":               len(prs),
        "commits":           len(commits),
        "discussions":       len(discussions),
        "queries":           all_summary,
    })

    print_summary(all_summary)
    console.print(
        f"\n[bold green]Done.[/]  "
        f"repos=[cyan]{len(repos)}[/]  "
        f"code=[cyan]{len(code)}[/]  "
        f"issues=[cyan]{len(issues)}[/]  "
        f"prs=[cyan]{len(prs)}[/]  "
        f"commits=[cyan]{len(commits)}[/]  "
        f"discussions=[cyan]{len(discussions)}[/]\n"
        f"Output: [dim]{raw}[/]"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1: search GitHub for MT adoption")
    parser.add_argument("--repo",         action="store_true", help="Repository searches")
    parser.add_argument("--code",         action="store_true", help="Code-file searches")
    parser.add_argument("--issues",       action="store_true", help="Issue & PR searches")
    parser.add_argument("--commits",      action="store_true", help="Commit message searches")
    parser.add_argument("--discussions",  action="store_true", help="GitHub Discussions (GraphQL)")
    parser.add_argument("--max-pages",    type=int, default=10,
                        help="Max pages per query/slice (default 10; GitHub caps at 10)")
    parser.add_argument("--no-slice",     action="store_true",
                        help="Disable adaptive date-range slicing (faster, incomplete for large queries)")
    args = parser.parse_args()

    # If no surface specified, run all
    any_flag = args.repo or args.code or args.issues or args.commits or args.discussions
    run(
        do_repos        = args.repo        or not any_flag,
        do_code         = args.code        or not any_flag,
        do_issues       = args.issues      or not any_flag,
        do_commits      = args.commits     or not any_flag,
        do_discussions  = args.discussions or not any_flag,
        max_pages       = args.max_pages,
        enable_slicing  = not args.no_slice,
    )


if __name__ == "__main__":
    main()
