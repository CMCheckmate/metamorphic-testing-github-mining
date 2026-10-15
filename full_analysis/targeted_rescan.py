"""
Targeted Re-scan
================
Computes the one value the aggregate-only repair cannot derive from stored data:
the exact number of lines with a technique hit in files where several technique
keywords matched (stored `n_hit_lines` also counts general-test lines, and per-
keyword counts overlap on shared lines).

Population: Usage repositories that still have such "ambiguous" technique files,
as listed by the aggregate step in overall.json → sections.a31.rescan_candidates
(184 repos / 1,667 files for metamorphic testing). Only those files are re-read.

Per repo, in batches (same clone → scan → delete cycle as code analysis):
  1. Partial clone without checkout (`--filter=blob:none --no-checkout`), history
     limited to a few days before the originally analysed commit. No working tree
     is written and no repository code is executed.
  2. Candidate commits = the newest commits at or before the stored
     `last_commit_date` (+1 day tolerance — that timestamp was stored in local time
     with a 'Z' suffix).
  3. Each candidate is verified by re-scanning the ambiguous files with `git show`
     and comparing per-keyword hit counts with the stored ones. A file's line count
     is only used when its keyword counts match exactly (same file content).
  4. The clone is deleted after the batch.

Output: results/<slug>/analysis/rescan_technique_lines.json (resumable). Then run
  python -m full_analysis -t <technique> --phase analysis --aggregate-only
so data_repair.py merges the verified counts.

Usage:
  python -m full_analysis.targeted_rescan -t mt --dry-run      # list population only
  python -m full_analysis.targeted_rescan -t mt --limit 2      # try a couple of repos
  python -m full_analysis.targeted_rescan -t mt                # all candidates (refuses > --max-repos)
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from tqdm import tqdm

from core_helpers import config as cfg
from full_analysis.code_analysis import _force_rmtree
from core_helpers.utils import (
    resolve_technique, technique_dirs, load_json, save_json, setup_logging,
    safe_clone_path, load_analysis_keywords, compile_analysis_keywords,
)


def _git(args: list[str], cwd=None, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.longpaths=true", *args], cwd=cwd,
                          capture_output=True, timeout=timeout)


def _scan_text(text: str, spec_kws: list[dict]) -> tuple[dict[str, int], int]:
    """Same per-line rule as code_analysis._scan_file, technique keywords only."""
    hits: dict[str, int] = defaultdict(int)
    lines = 0
    for line in text.splitlines():
        hit = False
        for kw in spec_kws:
            if kw["compiled"].search(line):
                hits[kw["id"]] += 1
                hit = True
        lines += hit
    return dict(hits), lines


def _clone(repo: str, since: datetime, target, logger) -> bool:
    url = f"https://github.com/{repo}.git"
    base = ["clone", "--filter=blob:none", "--no-checkout", "--no-tags"]
    for extra in (["--shallow-since", since.strftime("%Y-%m-%d")], ["--depth", "300"]):
        r = _git(base + extra + [url, str(target)], timeout=600)
        if r.returncode == 0:
            return True
        logger.warning(f"clone {repo} {extra}: {r.stderr.decode(errors='replace')[:200]}")
        if target.exists():
            _force_rmtree(target, logger)
    return False


def _rescan_repo(cand: dict, path, spec_kws: list[dict], logger) -> dict:
    last = datetime.fromisoformat(cand["last_commit_date"].replace("Z", "+00:00"))
    r = _git(["rev-list", "-n", "10", f"--before={(last + timedelta(days=1)).isoformat()}", "HEAD"], cwd=path)
    shas = r.stdout.decode().split()
    if not shas:
        return {"status": "no_snapshot", "files": {}}

    best_sha, best = None, {}
    for sha in shas:
        files = {}
        for f in cand["files"]:
            show = _git(["show", f"{sha}:{f['path']}"], cwd=path, timeout=120)
            if show.returncode != 0:
                files[f["path"]] = {"verified": False, "reason": "missing_at_commit"}
                continue
            hits, n_lines = _scan_text(show.stdout.decode("utf-8", errors="ignore"), spec_kws)
            stored = {k: v for k, v in f["specific_hits"].items() if v}
            files[f["path"]] = {"verified": hits == stored, "n_specific_hit_lines": n_lines,
                                "stored_hits": stored, "rescan_hits": hits}
        n_ok = sum(v["verified"] for v in files.values())
        if best_sha is None or n_ok > sum(v["verified"] for v in best.values()):
            best_sha, best = sha, files
        if n_ok == len(files):
            break
    n_ok = sum(v["verified"] for v in best.values())
    status = "ok" if n_ok == len(best) else ("partial" if n_ok else "mismatch")
    logger.info(f"{cand['repo']}: {status} {n_ok}/{len(best)} files @ {best_sha[:10]}")
    return {"status": status, "commit": best_sha, "files": best}


_SPLIT_END_RE   = re.compile(r"metamorphic\W*$", re.I)
_SPLIT_START_RE = re.compile(r"^\W*(?:test|relation|propert|oracle|group)", re.I)
_PREFIX_RE      = re.compile(r"[A-Za-z0-9_]metamorphic", re.I)
# Technique phrase present but the analysis regex misses it: plural not covered
# ('metamorphic oracles'), no space ('Metamorphictests'), or a Unicode letter (CJK/Korean)
# directly next to the phrase, which defeats Python's Unicode-aware \b.
_PHRASE_GAP_RE  = re.compile(r"metamorphic[\s_-]*(?:test|relation|propert|oracle|group)", re.I)


def _zero_cause(path: str, lines: list[str], hits: dict) -> str:
    """Why a file GitHub code search matched produced no technique hit in our scan."""
    if hits:
        return "has_hits_but_was_not_scanned"     # skipped dir / size / extension at analysis time
    m = [i for i, l in enumerate(lines) if "metamorphic" in l.lower()]
    if not m:
        return "match_in_path_only" if "metamorphic" in path.lower() else "no_technique_word_in_file"
    if any(_SPLIT_END_RE.search(lines[i]) and i + 1 < len(lines) and _SPLIT_START_RE.search(lines[i + 1]) for i in m):
        return "phrase_split_across_lines"
    if any(_PREFIX_RE.search(lines[i]) for i in m):
        return "identifier_with_prefix"
    if any(_PHRASE_GAP_RE.search(lines[i]) for i in m):
        return "phrase_regex_gap"
    return "bare_word_metamorphic"


def _investigate_repo(cand: dict, path, spec_kws: list[dict], logger) -> dict:
    """Read each file GitHub matched, at the analysed commit, and classify the miss."""
    last = datetime.fromisoformat(cand["last_commit_date"].replace("Z", "+00:00"))
    r = _git(["rev-list", "-n", "1", f"--before={(last + timedelta(days=1)).isoformat()}", "HEAD"], cwd=path)
    shas = r.stdout.decode().split()
    if not shas:
        return {"status": "no_snapshot", "files": {}}
    files = {}
    for p in cand["files"]:
        show = _git(["show", f"{shas[0]}:{p}"], cwd=path, timeout=120)
        if show.returncode != 0:
            files[p] = {"cause": "missing_at_analysed_commit"}
            continue
        text  = show.stdout.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        hits, _ = _scan_text(text, spec_kws)
        files[p] = {"cause": _zero_cause(p, lines, hits), "regex_hits": hits,
                    "snippets": [l.strip()[:200] for l in lines if "metamorphic" in l.lower()][:3]}
    logger.info(f"{cand['repo']}: {[v['cause'] for v in files.values()]}")
    return {"status": "ok", "commit": shas[0], "files": files}


def run(slug: str, dry_run: bool, limit: int | None, max_repos: int, restart: bool, zero_hit: bool = False) -> None:
    dirs   = technique_dirs(slug)
    logger = setup_logging(slug, "targeted_rescan")
    overall = load_json(dirs["analysis"] / "overall.json", {}) or {}
    if zero_hit:
        # Zero-hit investigation: the files GitHub code search matched in repos where the
        # analysis found no technique hit at all.
        cands = [{"repo": z["repo"], "last_commit_date": z.get("last_commit_date"), "files": z["matched_paths"]}
                 for z in overall.get("sections", {}).get("a2", {}).get("zero_hit_repos", [])]
        out_path, process = dirs["analysis"] / "zero_hit_investigation.json", _investigate_repo
    else:
        cands = overall.get("sections", {}).get("a31", {}).get("rescan_candidates")
        out_path, process = dirs["analysis"] / "rescan_technique_lines.json", _rescan_repo
    if cands is None:
        print(f"No rescan candidates in overall.json - run: python -m full_analysis -t {slug} --phase analysis --aggregate-only")
        return
    results: dict = {} if restart else (load_json(out_path, {}) or {})
    todo = [c for c in cands if c["repo"] not in results and c.get("last_commit_date")]
    n_files = sum(len(c["files"]) for c in todo)
    print(f"Candidates: {len(cands)} repos ({sum(len(c['files']) for c in cands)} files); "
          f"to do: {len(todo)} repos / {n_files} files")
    if dry_run:
        for c in todo[:20]:
            print(f"  {c['repo']}  ({len(c['files'])} files, analysed {c['last_commit_date']})")
        return
    if limit:
        todo = todo[:limit]
    elif len(todo) > max_repos:
        print(f"Refusing to re-scan {len(todo)} repos (> --max-repos {max_repos}). Use --limit or raise --max-repos.")
        return

    spec_kws = [k for k in compile_analysis_keywords(load_analysis_keywords(slug))
                if k["category"] == "specific_technique"]
    clone_dir = dirs["base"] / "rescan_cloned"
    clone_dir.mkdir(parents=True, exist_ok=True)

    batch_n = cfg.CLONE_BATCH_MAX_REPOS
    for b in range(0, len(todo), batch_n):
        batch = todo[b:b + batch_n]
        print(f"\nBatch {b // batch_n + 1}/{(len(todo) - 1) // batch_n + 1} - {len(batch)} repos")
        cloned = []
        for c in tqdm(batch, desc="Cloning (partial)", unit="repo"):
            path = safe_clone_path(clone_dir, c["repo"])
            since = datetime.fromisoformat(c["last_commit_date"].replace("Z", "+00:00")) - timedelta(days=3)
            if path.exists() or _clone(c["repo"], since, path, logger):
                cloned.append((c, path))
            else:
                results[c["repo"]] = {"status": "clone_failed", "files": {}}
                save_json(out_path, results)
        for c, path in tqdm(cloned, desc="Re-scanning", unit="repo"):
            try:
                results[c["repo"]] = process(c, path, spec_kws, logger)
            except Exception as exc:
                logger.error(f"{c['repo']}: {exc}", exc_info=True)
                results[c["repo"]] = {"status": "error", "error": str(exc)[:200], "files": {}}
            save_json(out_path, results)
        for _, path in cloned:
            try:
                _force_rmtree(path, logger)
            except Exception as exc:
                logger.warning(f"Failed to delete {path}: {exc}")

    st = Counter(v["status"] for v in results.values())
    print(f"\nDone. Status: {dict(st)} -> {out_path}")
    print(f"Next: python specialised_report.py -t {slug}")


def main() -> None:
    p = argparse.ArgumentParser(description="Re-scan ambiguous technique files of Usage repos for exact line counts.")
    p.add_argument("--technique", "-t", required=True)
    p.add_argument("--dry-run", action="store_true", help="List the population without cloning.")
    p.add_argument("--limit", type=int, help="Process at most N repos this run.")
    p.add_argument("--max-repos", type=int, default=200, help="Safety cap on population size (default 200).")
    p.add_argument("--restart", action="store_true", help="Ignore previous results.")
    p.add_argument("--zero-hit", action="store_true",
                   help="Investigate repos with no technique hit: read the files GitHub matched and classify why "
                        "(output: zero_hit_investigation.json).")
    a = p.parse_args()
    run(resolve_technique(a.technique), a.dry_run, a.limit, a.max_repos, a.restart, a.zero_hit)


if __name__ == "__main__":
    main()
