"""
Phase 2 — Clone Repos
======================
Reads results/<slug>/raw/repos.json and results/<slug>/raw/code.json, builds a merged
candidate list, then shallow-clones each repo into repos/<slug>/<owner>/<name>/.

Repos that already exist on disk are skipped unless --refresh is passed.
A clone manifest (results/<slug>/cloned/manifest.json) is maintained so Phase 3
always has a complete picture of what is available locally.

Usage:
    python clone.py --technique techniques/metamorphic_testing.yaml
    python clone.py --technique techniques/fuzzing.yaml --min-stars 5 --workers 8

    --technique PATH  Path to a technique YAML file (required)
    --source      Which search result file to pull candidates from (default: both)
    --limit       Max number of repos to clone in this run (default: unlimited)
    --offset      Skip the first N candidates after filtering/sorting
    --refresh     Re-clone repos that already exist locally
    --min-stars   Skip repos with fewer stars (default: 0)
    --skip-forks  Skip forked repositories
    --lang        Only clone repos whose primary language matches (e.g. Python)
"""

import argparse
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

import git  # GitPython

from config import (
    MAX_REPO_SIZE_KB,
    CLONE_DEPTH,
    CLONE_DELAY_SECONDS,
)

console = Console()


# ---------------------------------------------------------------------------
# Candidate building
# ---------------------------------------------------------------------------

def load_candidates(source: str, profile) -> list[dict]:
    """
    Merge repo and/or code search results into a unified candidate list.
    Each candidate has at minimum: full_name, clone_url, size_kb, is_fork, stars, language.
    """
    candidates: dict[str, dict] = {}

    if source in ("repos", "both"):
        repo_file = profile.results_dir / "raw" / "repos.json"
        if repo_file.exists():
            with open(repo_file) as f:
                for rec in json.load(f):
                    candidates[rec["full_name"]] = rec
        else:
            console.print(f"[yellow]repos.json not found — run search.py first[/]")

    if source in ("code", "both"):
        code_file = profile.results_dir / "raw" / "code.json"
        if code_file.exists():
            with open(code_file) as f:
                for rec in json.load(f):
                    name = rec["repo_full_name"]
                    if name not in candidates:
                        # code records lack stars/size; fill with defaults
                        candidates[name] = {
                            "full_name":  name,
                            "clone_url":  rec["repo_clone_url"],
                            "html_url":   rec["repo_html_url"],
                            "size_kb":    0,
                            "is_fork":    False,
                            "stars":      0,
                            "language":   "",
                            "source":     "code_search",
                        }
        else:
            console.print(f"[yellow]code.json not found — run search.py first[/]")

    # Enrich code-only candidates with repo metadata where possible
    return list(candidates.values())


def filter_candidates(
    candidates: list[dict],
    min_stars: int,
    skip_forks: bool,
    lang: str | None,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Return (kept, size_excluded, skip_counts). Size-excluded repos are recorded in the manifest."""
    out: list[dict] = []
    excluded: list[dict] = []
    skip_counts: dict[str, int] = {"size": 0, "fork": 0, "stars": 0, "language": 0}
    for c in candidates:
        if skip_forks and c.get("is_fork"):
            skip_counts["fork"] += 1
            continue
        if c.get("stars", 0) < min_stars:
            skip_counts["stars"] += 1
            continue
        if lang and c.get("language", "").lower() != lang.lower():
            skip_counts["language"] += 1
            continue
        if c.get("size_kb", 0) > MAX_REPO_SIZE_KB:
            size_kb = c["size_kb"]
            console.print(f"  [dim]skip (too large {size_kb:,} KB > {MAX_REPO_SIZE_KB:,} KB limit):[/] {c['full_name']}")
            excluded.append({**c, "skip_reason": f"size {size_kb:,} KB exceeds {MAX_REPO_SIZE_KB:,} KB limit"})
            skip_counts["size"] += 1
            continue
        out.append(c)
    return out, excluded, skip_counts


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def load_manifest(manifest_path: Path) -> dict:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        with open(manifest_path) as f:
            return json.load(f)
    return {"repos": {}}


def save_manifest(manifest: dict, manifest_path: Path) -> None:
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------

def clone_repo(candidate: dict, refresh: bool, manifest: dict, repos_dir: Path) -> str:
    """
    Clone a single repo.  Returns one of: 'cloned', 'skipped', 'refreshed', 'error'.
    Updates manifest in-place.
    """
    full_name = candidate["full_name"]
    clone_url = candidate["clone_url"]
    dest = repos_dir / full_name

    already_exists = dest.exists() and (dest / ".git").exists()

    if already_exists and not refresh:
        manifest["repos"].setdefault(full_name, {})["local_path"] = str(dest)
        manifest["repos"][full_name]["status"] = "skipped_exists"
        return "skipped"

    if already_exists and refresh:
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        git.Repo.clone_from(
            clone_url,
            str(dest),
            depth=CLONE_DEPTH,
            no_single_branch=True,
        )
        status = "refreshed" if (already_exists and refresh) else "cloned"
    except git.exc.GitCommandError as exc:
        console.print(f"  [red]Clone error[/] {full_name}: {exc}")
        manifest["repos"][full_name] = {
            "full_name":  full_name,
            "local_path": str(dest),
            "status":     "error",
            "error":      str(exc),
            "cloned_at":  datetime.now(timezone.utc).isoformat(),
        }
        return "error"

    manifest["repos"][full_name] = {
        "full_name":       full_name,
        "clone_url":       clone_url,
        "html_url":        candidate.get("html_url", ""),
        "local_path":      str(dest),
        "stars":           candidate.get("stars", 0),
        "language":        candidate.get("language", ""),
        "created_at":      candidate.get("created_at", ""),
        "size_kb":         candidate.get("size_kb", 0),
        "is_fork":         candidate.get("is_fork", False),
        "matched_queries": _collect_queries(candidate),
        "status":          status,
        "cloned_at":       datetime.now(timezone.utc).isoformat(),
    }
    return status


def _collect_queries(candidate: dict) -> list[str]:
    # Prefer labels (e.g. "repo_metamorphic_testing") over raw query strings.
    # matched_labels is written by search.py's _dedup_merge; fall back to
    # matched_queries (raw strings) for data produced before that fix.
    ls = candidate.get("matched_labels", [])
    if ls:
        return ls
    qs = candidate.get("matched_queries", [])
    if qs:
        return qs
    q = candidate.get("matched_query", "")
    return [q] if q else []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(source: str, limit: int | None, offset: int, refresh: bool, min_stars: int,
        skip_forks: bool, lang: str | None, workers: int = 4, profile=None) -> None:

    manifest_path = profile.results_dir / "cloned" / "manifest.json"
    repos_dir     = profile.repos_dir

    candidates = load_candidates(source, profile)
    candidates, excluded, filter_skips = filter_candidates(candidates, min_stars, skip_forks, lang)
    candidates.sort(key=lambda c: c.get("stars", 0), reverse=True)

    if offset:
        candidates = candidates[offset:]
    if limit:
        candidates = candidates[:limit]

    console.print(
        f"\n[bold]{len(candidates)}[/] candidates to process  "
        f"(source={source}, min_stars={min_stars}, skip_forks={skip_forks}, "
        f"offset={offset}, workers={workers})"
    )

    manifest = load_manifest(manifest_path)
    for exc in excluded:
        name = exc["full_name"]
        manifest["repos"][name] = {
            "full_name":   name,
            "clone_url":   exc.get("clone_url", ""),
            "html_url":    exc.get("html_url", ""),
            "stars":       exc.get("stars", 0),
            "language":    exc.get("language", ""),
            "size_kb":     exc.get("size_kb", 0),
            "status":      "skipped_size",
            "skip_reason": exc["skip_reason"],
        }
    if excluded:
        save_manifest(manifest, manifest_path)
    manifest_lock = Lock()
    counts = {"cloned": 0, "skipped": 0, "refreshed": 0, "error": 0}
    counts_lock = Lock()

    def _clone_worker(candidate: dict) -> str:
        result = clone_repo(candidate, refresh, manifest, repos_dir)
        time.sleep(CLONE_DELAY_SECONDS)
        with manifest_lock:
            save_manifest(manifest, manifest_path)
        with counts_lock:
            counts[result] += 1
        return result

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Cloning…", total=len(candidates))

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_candidate = {
                executor.submit(_clone_worker, c): c for c in candidates
            }
            for future in as_completed(future_to_candidate):
                c = future_to_candidate[future]
                progress.update(
                    task,
                    description=f"[cyan]{c['full_name'][:50]}[/]",
                    advance=1,
                )

    skip_lines = [f"already exist=[dim]{counts['skipped']}[/]"]
    if filter_skips["size"]:
        skip_lines.append(f"too large=[yellow]{filter_skips['size']}[/]")
    if filter_skips["fork"]:
        skip_lines.append(f"fork=[dim]{filter_skips['fork']}[/]")
    if filter_skips["stars"]:
        skip_lines.append(f"below min stars=[dim]{filter_skips['stars']}[/]")
    if filter_skips["language"]:
        skip_lines.append(f"language filter=[dim]{filter_skips['language']}[/]")

    console.print(
        f"\n[bold green]Done.[/]  "
        f"cloned=[green]{counts['cloned']}[/]  "
        f"refreshed=[blue]{counts['refreshed']}[/]  "
        f"errors=[red]{counts['error']}[/]\n"
        f"Skipped:  " + "  |  ".join(skip_lines)
    )
    console.print(f"Manifest updated: [dim]{manifest_path}[/]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2: clone candidate repositories")
    parser.add_argument("--technique",   required=True,
                        help="Path to technique YAML file (e.g. techniques/metamorphic_testing.yaml)")
    parser.add_argument("--source",     choices=["repos", "code", "both"], default="both")
    parser.add_argument("--limit",      type=int,  default=None, help="Max repos to clone")
    parser.add_argument("--offset",     type=int,  default=0, help="Skip the first N filtered repos")
    parser.add_argument("--refresh",    action="store_true", help="Re-clone existing repos")
    parser.add_argument("--min-stars",  type=int,  default=0)
    parser.add_argument("--skip-forks", action="store_true")
    parser.add_argument("--lang",        type=str,  default=None, help="Filter by primary language")
    parser.add_argument("--workers",     type=int,  default=4,   help="Parallel clone workers (default: 4)")
    args = parser.parse_args()

    from config import load_technique
    profile = load_technique(args.technique)

    run(args.source, args.limit, args.offset, args.refresh, args.min_stars,
        args.skip_forks, args.lang, args.workers, profile=profile)


if __name__ == "__main__":
    main()
