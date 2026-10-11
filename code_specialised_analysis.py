"""
Specialised (fast) code analysis
================================
Re-scans CODE-surface repositories collecting only what the sections report uses:
per repository, the file list, each file's class (test code / source code / doc /
config / other), whether each file has a technique hit (+ per-keyword counts for A1),
lines of code in code files (S3), and a README excerpt for manual classification.

Why it is fast compared with code_analysis.py:
  * `git clone --depth 1 --no-checkout`: latest snapshot only, no history, nothing
    written out as files (no Windows checkout / antivirus cost);
  * native `git grep` over the snapshot instead of a Python regex loop on every line:
    a literal prefilter ("metamorphic") finds the few candidate files, test-file
    import rules and line counts are also git grep;
  * no commit mining, doc word sets or automated classification;
  * several repositories in parallel.

Population: CODE-surface repositories from search/code.json, minus repositories found
only by keywords excluded from the comparison (inputs/comparison_keywords.json, e.g.
"@metamorphic", which GitHub searches as the bare word). Phase 1 = repositories already
analysed by code_analysis.py (re-scanned with the fixed regexes), Phase 2 = the rest.
Each phase is processed in a fixed random order (seed below), so a partial run is a
random sample. Repositories larger than --big-gb are processed last.

Splitting across PCs (no coordination needed — every PC computes the same split):
  python code_specialised_analysis.py -t mt                                    # one PC, everything
  python code_specialised_analysis.py -t mt --weights 50,40,10 --shard 1       # you
  python code_specialised_analysis.py -t mt --weights 50,40,10 --shard 2       # friend A
  python code_specialised_analysis.py -t mt --weights 50,40,10 --shard 3       # friend B
Weights split the estimated work (based on repository size), not the repo count.

Other modes:
  --benchmark N        process the first N repos of this shard, then print timings and
                       a projection for the rest (results are kept, not wasted)
  --status             show progress of this shard
  --skip-done F [F …]  also skip repos already present in other output files
                       (lets a PC that finished early help with the remaining work)
  --merge F [F …]      combine shard outputs into analysis/specialised_repos.json
  --make-package       build the zip to give to the other PCs

Output: results/<slug>/specialised/shard{K}of{N}.jsonl (one JSON record per line;
resumable — rerun the same command to continue).

Sample mode (PBT / fuzz): when analysis/code_sample.json exists (written by
`non_code_specialised_analysis.py --prepare`), the population is that seeded random sample of
the explicit-phrase CODE repositories (read from results/<slug>/filtered/code_sample_items.json)
instead of every CODE repository. Sharding, resuming and merging work the same way.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from tqdm import tqdm

from core_helpers import config as cfg
from full_analysis.code_analysis import _EXT_LANG, _TEST_DIR_RE
from core_helpers.keyword_matcher import TechniqueMatcher, PREFILTER
from core_helpers.utils import (
    resolve_technique, technique_dirs, load_json, save_json, setup_logging,
    load_analysis_keywords, compile_analysis_keywords,
)

SCANNER_VERSION = 3
SEED            = 20261010
OVERHEAD_KB     = 30_000          # fixed per-repo cost, in "KB-equivalents", for work estimates
README_CHARS    = 3000
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1",
           "GCM_INTERACTIVE": "never", "GIT_ASKPASS": "echo"}
_CODE_GLOBS = [f":(icase)*{e}" for e in sorted(cfg.CODE_EXTENSIONS)]
_LANG_EXTS: dict[str, list[str]] = {}
for _e, _l in _EXT_LANG.items():
    _LANG_EXTS.setdefault(_l, []).append(_e)


# ---------------------------------------------------------------------------
# Population and shard assignment (deterministic on every PC)
# ---------------------------------------------------------------------------

def _base_kw(kw: str) -> str:
    m = re.match(r'\s*("[^"]+")', kw or "")
    return m.group(1) if m else (kw or "").split(" ")[0]


def comparison_exclusions(slug: str) -> set[str]:
    data = load_json(cfg.INPUTS_DIR / "comparison_keywords.json", {}) or {}
    return set((data.get(slug) or {}).get("exclude_search_keywords", []))


def build_population(slug: str, dirs: dict) -> dict:
    sample = load_json(dirs["analysis"] / "code_sample.json", None)
    if sample:
        return _sample_population(slug, dirs, sample)
    code = load_json(dirs["search"] / "code.json", []) or []
    meta = load_json(dirs["analysis"] / "cloned_repo_metadata.json", {}) or {}
    hist = load_json(dirs["analysis"] / "code_history.json", {}) or {}
    excl = comparison_exclusions(slug)
    repos: dict[str, dict] = {}
    for it in code:
        rn = it.get("repo_full_name")
        if not rn:
            continue
        r = repos.setdefault(rn, {"name": rn, "kws": set(), "paths": set(),
                                  "url": it.get("repo_clone_url") or f"https://github.com/{rn}.git"})
        r["kws"].update(_base_kw(k) for k in (it.get("matched_keywords") or [it.get("matched_keyword")]))
        if it.get("file_path"):
            r["paths"].add(it["file_path"])
    sizes = [(m or {}).get("size_kb") or 0 for m in meta.values() if isinstance(m, dict)]
    median = sorted(sizes)[len(sizes) // 2] if sizes else 10_000
    excluded, phase1, phase2 = [], [], []
    for rn in sorted(repos):
        r = repos[rn]
        if excl and r["kws"] <= excl:
            excluded.append(rn)
            continue
        r["size_kb"] = ((meta.get(rn) or {}).get("size_kb") or median)
        (phase1 if hist.get(rn) == "done" else phase2).append(rn)
    rnd = random.Random(SEED)
    rnd.shuffle(phase1)
    rnd.shuffle(phase2)
    return {"repos": repos, "phase1": phase1, "phase2": phase2, "excluded": excluded,
            "exclude_keywords": sorted(excl)}


def _sample_population(slug: str, dirs: dict, sample: dict) -> dict:
    """Population = the seeded random sample drawn by --prepare (already in
    random order, so a partial run is still a random sample). Everything is phase 2."""
    names = list(sample["sample"])
    want  = set(names)
    meta  = {**(load_json(dirs["analysis"] / "cloned_repo_metadata.json", {}) or {}),
             **(load_json(dirs["analysis"] / "sample_metadata.json", {}) or {})}
    repos: dict[str, dict] = {}
    for rn, it in (load_json(dirs["base"] / "filtered" / "code_sample_items.json", {}) or {}).items():
        if rn in want:
            repos[rn] = {"name": rn, "kws": set(it.get("kws") or []), "paths": set(it.get("paths") or []),
                         "url": it.get("url") or f"https://github.com/{rn}.git"}
    sizes = [(m or {}).get("size_kb") or 0 for m in meta.values() if isinstance(m, dict)]
    median = sorted(sizes)[len(sizes) // 2] if sizes else 10_000
    for rn in names:
        r = repos.setdefault(rn, {"name": rn, "kws": set(), "paths": set(), "url": f"https://github.com/{rn}.git"})
        r["size_kb"] = (meta.get(rn) or {}).get("size_kb") or median
    return {"repos": repos, "phase1": [], "phase2": names, "excluded": [],
            "exclude_keywords": sorted(comparison_exclusions(slug)), "sample": sample}


def assign_shards(pop: dict, weights: list[float], big_kb: float) -> list[list[dict]]:
    """Weighted longest-processing-time assignment, per phase; then per-shard order:
    phase 1 (random order) -> phase 2 (random order), big repos last within each phase."""
    n = len(weights)
    shards: list[list[dict]] = [[] for _ in range(n)]
    loads = [0.0] * n
    for phase_no, names in ((1, pop["phase1"]), (2, pop["phase2"])):
        owner = {}
        work  = {rn: OVERHEAD_KB + pop["repos"][rn]["size_kb"] for rn in names}
        for rn in sorted(names, key=lambda x: (-work[x], x)):
            k = min(range(n), key=lambda i: ((loads[i] + work[rn]) / weights[i], i))
            loads[k] += work[rn]
            owner[rn] = k
        for k in range(n):
            mine  = [rn for rn in names if owner[rn] == k]                 # keeps the random order
            small = [rn for rn in mine if pop["repos"][rn]["size_kb"] <= big_kb]
            big   = [rn for rn in mine if pop["repos"][rn]["size_kb"] > big_kb]
            for rn in small + big:
                r = pop["repos"][rn]
                shards[k].append({"name": rn, "url": r["url"], "phase": phase_no, "size_kb": r["size_kb"],
                                  "matched_paths": sorted(r["paths"])[:20]})
    return shards


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd=None, timeout: int = 600, input_: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.longpaths=true", "-c", "core.quotepath=false", *args],
                          cwd=cwd, capture_output=True, timeout=timeout, env=GIT_ENV, input=input_)


def _rmtree(p: Path) -> None:
    def onerr(func, path, _):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            pass
    if p.exists():
        shutil.rmtree(p, onerror=onerr)


_PCRE: bool | None = None


def _pcre_ok() -> bool:
    """True if this git build supports `git grep -P` (Git for Windows does); else use -E."""
    global _PCRE
    if _PCRE is None:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "probe.txt"
            f.write_text("x\n", encoding="utf-8")
            r = subprocess.run(["git", "grep", "--no-index", "-P", "-e", "x", str(f)],
                               capture_output=True, env=GIT_ENV, cwd=d)
        _PCRE = r.returncode in (0, 1)
    return _PCRE


def _grep_paths(dest: Path, args: list[str], timeout: int = 600) -> list[str]:
    """Run `git grep -l -z … HEAD`, return repo-relative paths."""
    r = _git(["grep", "-I", "-l", "-z", *args], cwd=dest, timeout=timeout)
    out = []
    for item in r.stdout.split(b"\0"):
        if item.startswith(b"HEAD:"):
            out.append(item[5:].decode("utf-8", "replace"))
    return out


def _read_blobs(dest: Path, entries: list[tuple[str, str, int]]) -> dict[str, str]:
    """entries = (path, oid, size) -> {path: text}, read with `git cat-file --batch` in chunks."""
    texts: dict[str, str] = {}
    chunk: list[tuple[str, str, int]] = []
    budget = 0

    def flush():
        if not chunk:
            return
        r = _git(["cat-file", "--batch"], cwd=dest, timeout=600,
                 input_=("\n".join(oid for _, oid, _ in chunk) + "\n").encode())
        buf, pos = r.stdout, 0
        for path, _, _ in chunk:
            nl = buf.find(b"\n", pos)
            header = buf[pos:nl].split()
            if len(header) < 3 or header[1] != b"blob":
                pos = nl + 1
                continue
            size = int(header[2])
            texts[path] = buf[nl + 1: nl + 1 + size].decode("utf-8", errors="ignore")
            pos = nl + 1 + size + 1
        chunk.clear()

    for e in entries:
        chunk.append(e)
        budget += e[2]
        if budget > 200 * 1024 * 1024 or len(chunk) >= 500:
            flush()
            budget = 0
    flush()
    return texts


# ---------------------------------------------------------------------------
# Per-repository scan
# ---------------------------------------------------------------------------

class ScanContext:
    def __init__(self, slug: str, tmp: Path, clone_timeout: int) -> None:
        self.slug    = slug
        self.tmp     = tmp
        self.timeout = clone_timeout
        self.matcher = TechniqueMatcher(slug)
        self.prefilter = PREFILTER.get(slug, [])
        tfd = [k for k in compile_analysis_keywords(load_analysis_keywords(slug)) if k.get("apply_to")]
        self.tfd_file    = [k for k in tfd if k["apply_to"] == "filename"]
        self.tfd_content = [k for k in tfd if k["apply_to"] == "content"]


def _category(path: str, ext: str) -> str:
    if ext in cfg.CODE_EXTENSIONS:
        return "code"
    if ext in cfg.DOC_EXTENSIONS:
        return "docs"
    if ext in cfg.CONFIG_EXTENSIONS:
        return "config"
    return "other"


def _zero_cause(path: str, in_tree: bool, scannable: bool, text: str | None, ctx: "ScanContext") -> str:
    if not in_tree:
        return "missing_at_snapshot"
    if not scannable:
        return "file_not_scannable"           # skipped dir / ignored extension / empty / binary
    if text is None:                          # file has none of the prefilter literals
        words = [w.lower() for w in ctx.prefilter]
        return "match_in_path_only" if any(w in path.lower() for w in words) else "no_technique_word_in_file"
    if ctx.slug == "metamorphic_testing":
        from full_analysis.targeted_rescan import _zero_cause as zc
        return zc(path, text.splitlines(), {})
    return "technique_word_without_phrase"


def scan_repo(job: dict, ctx: ScanContext, slot: int) -> dict:
    name = job["name"]
    rec  = {"full_name": name, "phase": job["phase"], "scanner_version": SCANNER_VERSION,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    dest = ctx.tmp / f"w{slot}"
    _rmtree(dest)
    t0 = time.time()
    try:
        r = _git(["clone", "--depth", "1", "--no-checkout", "--single-branch", "--no-tags", "--quiet",
                  job["url"], str(dest)], timeout=ctx.timeout)
    except subprocess.TimeoutExpired:
        _rmtree(dest)
        return {**rec, "status": "failed", "error": f"clone timeout ({ctx.timeout}s)", "clone_s": round(time.time() - t0, 1)}
    if r.returncode != 0:
        _rmtree(dest)
        return {**rec, "status": "failed", "error": r.stderr.decode("utf-8", "replace")[-300:].strip(),
                "clone_s": round(time.time() - t0, 1)}
    t1 = time.time()
    try:
        rec.update(_scan_snapshot(dest, job, ctx))
        rec["status"] = "ok"
    except Exception as exc:                                # keep going; record the failure
        rec.update(status="failed", error=f"scan: {type(exc).__name__}: {exc}"[:300])
    finally:
        _rmtree(dest)
    rec["clone_s"] = round(t1 - t0, 1)
    rec["scan_s"]  = round(time.time() - t1, 1)
    return rec


def _scan_snapshot(dest: Path, job: dict, ctx: ScanContext) -> dict:
    head = _git(["log", "-1", "--format=%H%x09%cI"], cwd=dest).stdout.decode().strip().split("\t")
    ls = _git(["ls-tree", "-r", "-l", "-z", "HEAD"], cwd=dest, timeout=600).stdout

    files: dict[str, dict] = {}          # scannable files only
    all_paths: set[str] = set()
    for entry in ls.split(b"\0"):
        if not entry:
            continue
        meta, _, path_b = entry.partition(b"\t")
        parts = meta.split()
        path  = path_b.decode("utf-8", "replace")
        all_paths.add(path)
        if len(parts) < 4 or parts[1] != b"blob" or parts[0] in (b"120000", b"160000"):
            continue
        size = int(parts[3]) if parts[3].isdigit() else 0
        pp   = PurePosixPath(path)
        ext  = pp.suffix.lower()
        if size == 0 or ext in cfg.IGNORED_EXTENSIONS or any(d in cfg.SKIP_DIRS for d in pp.parts[:-1]):
            continue
        files[path] = {"oid": parts[2].decode(), "size": size, "ext": ext, "cat": _category(path, ext),
                       "lang": _EXT_LANG.get(ext), "parts": pp.parts}

    # Test-file detection for code files: filename rules, content rules (git grep), test dirs.
    content_test: set[str] = set()
    for kw in ctx.tfd_content:
        exts = _LANG_EXTS.get(kw.get("language"), []) if kw.get("language") else sorted(cfg.CODE_EXTENSIONS)
        if not exts:
            continue
        args = ["-P" if _pcre_ok() else "-E", "-e", kw["regex"], "HEAD", "--"] + [f":(icase)*{e}" for e in exts]
        content_test.update(_grep_paths(dest, args))
    for path, f in files.items():
        if f["cat"] != "code":
            continue
        is_test = path in content_test or any(_TEST_DIR_RE.search(d) for d in f["parts"][:-1])
        if not is_test:
            name = f["parts"][-1]
            is_test = any((not k.get("language") or k["language"] == f["lang"]) and k["compiled"].search(name)
                          for k in ctx.tfd_file)
        f["cat"] = "test_code" if is_test else "source_code"

    # Technique hits: literal prefilter with git grep, regexes only on candidate files.
    if ctx.prefilter:
        args = ["-i", "-F"] + [x for t in ctx.prefilter for x in ("-e", t)] + ["HEAD"]
        candidates = [p for p in _grep_paths(dest, args) if p in files]
    else:
        candidates = [p for p in files if files[p]["cat"] != "other"]
    texts = _read_blobs(dest, [(p, files[p]["oid"], files[p]["size"]) for p in candidates])
    kw_counts: Counter = Counter()
    hit_files = []
    for p, text in texts.items():
        hits, n_lines = ctx.matcher.scan_text(text)
        total = ctx.matcher.total(hits)
        files[p]["hit"] = total > 0
        if total:
            kw_counts.update(hits)
            hit_files.append({"path": p, "category": files[p]["cat"], "specific_hits": hits,
                              "total_specific": total, "n_spec_lines": n_lines})

    # Lines of code (code files only), natively.
    loc: dict[str, int] = {}
    r = _git(["grep", "-I", "-c", "-z", "-e", "", "HEAD", "--", *_CODE_GLOBS], cwd=dest, timeout=600)
    for line in r.stdout.split(b"\n"):
        if line.startswith(b"HEAD:") and b"\0" in line:
            p, _, n = line[5:].partition(b"\0")
            ps = p.decode("utf-8", "replace")
            if ps in files and n.strip().isdigit():
                loc[ps] = int(n)

    # Aggregates in the same shape code_analysis stores, so analysis.py works unchanged.
    by_cat = {c: {"file_count": 0, "hit_file_count": 0, "total_lines": 0, "hit_line_count": 0,
                  "total_general_hits": 0, "total_specific_hits": 0}
              for c in ("test_code", "source_code", "docs", "config", "other")}
    code_b, doc_b, langs = Counter(), Counter(), Counter()
    spec_by_path = {h["path"]: h for h in hit_files}
    for p, f in files.items():
        c, hit = f["cat"], f.get("hit", False)
        b = by_cat[c]
        b["file_count"] += 1
        b["hit_file_count"] += hit
        b["total_lines"] += loc.get(p, 0)
        if hit:
            b["total_specific_hits"] += spec_by_path[p]["total_specific"]
            b["hit_line_count"] += spec_by_path[p]["n_spec_lines"]
        if c in ("test_code", "source_code"):
            code_b[("tech_test" if hit else "gen_test") if c == "test_code" else ("tech_nontest" if hit else "nontest")] += 1
            if f["lang"]:
                langs[f["lang"]] += 1
        if c == "docs":
            doc_b["tech_doc" if hit else "gen_doc"] += 1
        else:
            doc_b["nondoc_tech" if hit else "nondoc_general"] += 1

    # GitHub's matched files (from code search) — explains repos with no hit.
    matched = {}
    for p in job.get("matched_paths", []):
        in_tree, scannable = p in all_paths, p in files
        if scannable and files[p].get("hit"):
            matched[p] = {"hit": True}
        else:
            matched[p] = {"hit": False, "cause": _zero_cause(p, in_tree, scannable, texts.get(p), ctx)}

    readme = ""
    for p in sorted(files, key=lambda x: (len(x), x)):
        if "/" not in p and PurePosixPath(p).stem.lower() == "readme":
            readme = _read_blobs(dest, [(p, files[p]["oid"], files[p]["size"])]).get(p, "")[:README_CHARS]
            break

    labels = ctx.matcher.labels
    return {
        "commit": head[0] if head else None,
        "commit_date": head[1] if len(head) > 1 else None,
        "readme_snippet": readme,
        "scan": {
            "scanner_version":     SCANNER_VERSION,
            "total_files":         len(files),
            "total_hit_files":     sum(1 for f in files.values() if f.get("hit")),
            "total_lines":         sum(loc.values()),          # lines of code (code files only)
            "total_hit_lines":     sum(h["n_spec_lines"] for h in hit_files),
            "total_general_hits":  0,                          # not collected by this scanner
            "total_specific_hits": sum(h["total_specific"] for h in hit_files),
            "by_category":         by_cat,
            "hits_by_keyword":     {k: {"count": v, "label": labels.get(k, k)} for k, v in kw_counts.items()},
            "language_distribution": dict(langs),
            "code_files":          by_cat["test_code"]["file_count"] + by_cat["source_code"]["file_count"],
            "code_loc":            sum(loc.values()),
            "code_buckets":        dict(code_b),
            "doc_buckets":         dict(doc_b),
            "hit_files":           hit_files,
            "matched_paths":       matched,
        },
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _keep_awake(on: bool) -> None:
    """Stop Windows from idle-sleeping while the scan runs (a sleeping PC freezes every
    worker; on wake-up all in-flight repos 'time out' together). No admin rights needed.
    Does not override closing a laptop lid or choosing Sleep manually."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    except Exception:
        pass


_CONSOLE_MODE: int | None = None


def _quickedit(off: bool) -> None:
    """Windows console 'QuickEdit' pauses all output while text is selected in the window
    (e.g. after clicking it to copy something). The progress-bar write then blocks and the
    whole scan freezes until Enter/Esc is pressed. Turn QuickEdit off while scanning and
    restore the original console mode afterwards. (Windows Terminal is not affected.)"""
    global _CONSOLE_MODE
    if sys.platform != "win32":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-10)                     # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
            return                                         # not a classic console (e.g. redirected)
        if off:
            _CONSOLE_MODE = mode.value
            k32.SetConsoleMode(handle, (mode.value | 0x0080) & ~0x0040)   # EXTENDED_FLAGS on, QUICK_EDIT off
        elif _CONSOLE_MODE is not None:
            k32.SetConsoleMode(handle, _CONSOLE_MODE)
    except Exception:
        pass


def _retryable(rec: dict) -> bool:
    """Timeouts (usually caused by the PC sleeping, or a transient network stall) are retried;
    'repository not found / disabled' and similar permanent failures are not."""
    return rec.get("status") != "ok" and "imeout" in (rec.get("error") or "")


def _out_path(dirs: dict, shard: int, n: int) -> Path:
    return dirs["base"] / "specialised" / f"shard{shard}of{n}.jsonl"


def _read_jsonl(paths) -> dict[str, dict]:
    done: dict[str, dict] = {}
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue                                    # torn last line after a crash
                prev = done.get(r["full_name"])
                if prev is None or r.get("status") == "ok" or prev.get("status") != "ok":
                    done[r["full_name"]] = r
    return done


def run(args) -> None:
    slug = resolve_technique(args.technique)
    dirs = technique_dirs(slug)
    weights = [float(w) for w in args.weights.split(",")] if args.weights else [1.0] * args.num_shards
    n, k = len(weights), args.shard
    if not 1 <= k <= n:
        sys.exit(f"--shard must be between 1 and {n}")
    if slug not in PREFILTER:
        print("WARNING: no literal prefilter for this technique — every non-'other' file is read (slow).")

    pop    = build_population(slug, dirs)
    shards = assign_shards(pop, weights, args.big_gb * 1024 * 1024)
    jobs   = shards[k - 1]
    out    = _out_path(dirs, k, n)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_json(out.parent / "population.json", {
        "seed": SEED, "weights": weights, "excluded_only_by": pop["exclude_keywords"],
        "excluded": pop["excluded"], "phase1": len(pop["phase1"]), "phase2": len(pop["phase2"]),
        "shard_sizes": [len(s) for s in shards],
        "sample_of": (pop.get("sample") or {}).get("population")})
    if pop.get("sample"):
        smp = pop["sample"]
        print(f"Sample mode: {len(smp['sample']):,} randomly sampled repos of {smp['population']:,} CODE-surface "
              f"repositories (±{smp['margin'] * 100:.0f}% at 95% confidence needs {smp['n_required']:,}; "
              "the extra repos cover deleted/private ones).")

    done = _read_jsonl([out] + [Path(p) for p in args.skip_done])
    finished = {rn for rn, r in done.items()
                if r.get("status") == "ok" or (not args.retry_failed and not _retryable(r))}
    todo = [j for j in jobs if j["name"] not in finished]
    ph = Counter(j["phase"] for j in jobs)
    if not pop.get("sample"):
        print(f"Technique {slug}: population {len(pop['phase1']) + len(pop['phase2']):,} repos "
              f"(phase 1: {len(pop['phase1']):,}, phase 2: {len(pop['phase2']):,}; "
              f"{len(pop['excluded'])} excluded — found only by {', '.join(pop['exclude_keywords']) or '—'})")
    print(f"Shard {k}/{n} (weights {args.weights or 'equal'}): {len(jobs):,} repos "
          f"(phase 1: {ph[1]:,}, phase 2: {ph[2]:,}); already done: {len(jobs) - len(todo):,}; to do: {len(todo):,}")
    print(f"Output: {out}")
    if args.status:
        st = Counter(done[j["name"]].get("status") for j in jobs if j["name"] in done)
        print(f"Status: {dict(st)}")
        return
    if args.benchmark:
        todo = todo[:args.benchmark]
    if not todo:
        print("Nothing to do.")
        return

    ctx = ScanContext(slug, dirs["base"] / "specialised_tmp" / f"shard{k}", args.clone_timeout)
    _rmtree(ctx.tmp)
    ctx.tmp.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(slug, f"specialised_shard{k}of{n}")
    lock   = threading.Lock()
    slots  = list(range(args.workers))
    slot_lock = threading.Lock()

    def work(job):
        with slot_lock:
            slot = slots.pop()
        try:
            return scan_repo(job, ctx, slot)
        finally:
            with slot_lock:
                slots.append(slot)

    t_start = time.time()
    results = []
    _keep_awake(True)
    _quickedit(off=True)
    try:
        with open(out, "a", encoding="utf-8") as fh:
            # Second pass: repos that timed out in the first pass are retried once at the end.
            for attempt, batch in enumerate((todo, None)):
                if batch is None:
                    first_pass = {r["full_name"]: r for r in results}
                    batch = [j for j in todo if _retryable(first_pass.get(j["name"], {}))]
                    if not batch or args.benchmark:
                        break
                    print(f"\nRetrying {len(batch)} repo(s) that timed out (e.g. while the PC was asleep)...")
                pass_failed = 0
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futs = {pool.submit(work, j): j for j in batch}
                    bar  = tqdm(as_completed(futs), total=len(futs), unit="repo",
                                desc=f"shard {k}/{n}" + (" (retry)" if attempt else ""))
                    for fut in bar:
                        rec = fut.result()
                        job = futs[fut]
                        rec["shard"] = f"{k}/{n}"
                        rec["size_kb"] = job["size_kb"]
                        with lock:
                            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            fh.flush()
                        results.append(rec)
                        logger.info(f"{rec['full_name']}: {rec['status']} clone={rec.get('clone_s')}s scan={rec.get('scan_s')}s"
                                    + (f" error={rec.get('error')}" if rec["status"] != "ok" else ""))
                        pass_failed += rec["status"] != "ok"
                        bar.set_postfix(failed=pass_failed)
    finally:
        _keep_awake(False)
        _quickedit(off=False)
    _rmtree(ctx.tmp)
    # Keep only the latest record per repo for the summary below.
    latest: dict[str, dict] = {}
    for r in results:
        latest[r["full_name"]] = r
    results = list(latest.values())
    elapsed = time.time() - t_start
    print(f"\nProcessed {len(results)} repos in {elapsed / 60:.1f} min "
          f"({sum(r['status'] == 'ok' for r in results)} ok, {sum(r['status'] != 'ok' for r in results)} failed).")
    if args.benchmark:
        _projection(results, [j for j in jobs if j["name"] not in finished][len(results):], elapsed, args.workers)
    else:
        print(f"Send {out.name} to the person merging, or run: python code_specialised_analysis.py -t {args.technique} --merge "
              f"\"results/{slug}/specialised/*.jsonl\"")


def _projection(results: list[dict], remaining: list[dict], elapsed: float, workers: int) -> None:
    ok = [r for r in results if r["status"] == "ok"]
    if len(ok) < 3:
        print("Too few successful repos for a projection.")
        return
    xs = [r["size_kb"] / 1024 for r in ok]
    ys = [r.get("clone_s", 0) + r.get("scan_s", 0) for r in ok]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    var = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var if var else 0.0
    b = max(b, 0.0)
    a = max(my - b * mx, 0.5)
    # Effective parallelism actually achieved in this run (wall-clock vs summed per-repo time).
    eff = max(1.0, min(workers, sum(ys) / max(elapsed, 1e-6)))
    print(f"\nPer repo: median {sorted(ys)[len(ys) // 2]:.1f}s; model time ~ {a:.1f}s + {b:.3f}s per MB of repo size; "
          f"effective parallelism ~ {eff:.1f}")
    for phase in (1, 2):
        rem = [j for j in remaining if j["phase"] == phase]
        secs = sum(a + b * j["size_kb"] / 1024 for j in rem) / eff
        print(f"  Phase {phase}: {len(rem):,} repos left -> about {secs / 3600:.1f} h on this PC")
    print("Projection assumes the remaining repos behave like the benchmark; very large repos and network "
          "conditions can change it. Re-run without --benchmark to continue from where this stopped.")


def merge(args) -> None:
    slug = resolve_technique(args.technique)
    dirs = technique_dirs(slug)
    files = [p for pat in args.merge for p in (glob.glob(pat) or [pat])]
    recs = _read_jsonl(files)
    out = dirs["analysis"] / "specialised_repos.json"
    save_json(out, recs)
    st = Counter(r.get("status") for r in recs.values())
    print(f"Merged {len(files)} file(s): {len(recs):,} repos ({dict(st)}) -> {out}")
    if (dirs["analysis"] / "code_sample.json").exists():
        print(f"Next: python specialised_report.py -t {args.technique}")
    else:
        print(f"Next: python specialised_report.py -t {args.technique}")


def make_package(args) -> None:
    slug = resolve_technique(args.technique)
    dirs = technique_dirs(slug)
    base = cfg.BASE_DIR
    out = base / f"specialised_package_{cfg.TECHNIQUE_INPUT_PREFIXES[slug]}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(base.glob("*.py")):
            z.write(p, p.name)
        for pkg in ("core_helpers", "report_helpers", "full_analysis"):       # imported by the scanner
            for p in sorted((base / pkg).glob("*.py")):
                z.write(p, f"{pkg}/{p.name}")
        for p in sorted((base / "inputs").glob("*")):
            if p.is_file():
                z.write(p, f"inputs/{p.name}")
        for name in ("requirements.txt", "README.md", ".env.example"):
            if (base / name).exists():
                z.write(base / name, name)
        if (dirs["analysis"] / "code_sample.json").exists():          # sample mode (PBT / fuzz)
            rels = (f"results/{slug}/filtered/code_sample_items.json", f"results/{slug}/analysis/code_sample.json",
                    f"results/{slug}/analysis/cloned_repo_metadata.json", f"results/{slug}/analysis/sample_metadata.json")
        else:
            rels = (f"results/{slug}/search/code.json", f"results/{slug}/analysis/cloned_repo_metadata.json",
                    f"results/{slug}/analysis/code_history.json")
        for rel in rels:
            if (base / rel).exists():
                z.write(base / rel, rel)
    print(f"Package written: {out} ({out.stat().st_size / 1024 / 1024:.0f} MB)")


def main() -> None:
    p = argparse.ArgumentParser(description="Fast, shardable code analysis for the sections report.")
    p.add_argument("--technique", "-t", required=True)
    p.add_argument("--weights", help="Comma-separated work shares, one per PC, e.g. 50,40,10 (same on every PC).")
    p.add_argument("--num-shards", type=int, default=1, help="Equal split into N parts (ignored if --weights is given).")
    p.add_argument("--shard", type=int, default=1, help="Which part this PC runs (1-based).")
    p.add_argument("--workers", type=int, default=6, help="Repositories processed at the same time (default 6).")
    p.add_argument("--benchmark", type=int, metavar="N", help="Process N repos and print a time projection.")
    p.add_argument("--status", action="store_true", help="Show progress of this shard and exit.")
    p.add_argument("--skip-done", nargs="*", default=[], metavar="FILE", help="Other output files whose repos to skip.")
    p.add_argument("--retry-failed", action="store_true", help="Retry repos that failed earlier.")
    p.add_argument("--big-gb", type=float, default=3.0, help="Repos larger than this (GitHub size, GB) go last.")
    p.add_argument("--clone-timeout", type=int, default=1800, help="Seconds before a clone is abandoned.")
    p.add_argument("--merge", nargs="+", metavar="FILE", help="Merge shard outputs into analysis/specialised_repos.json.")
    p.add_argument("--make-package", action="store_true", help="Build the zip for the other PCs.")
    args = p.parse_args()
    if args.merge:
        merge(args)
    elif args.make_package:
        make_package(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
