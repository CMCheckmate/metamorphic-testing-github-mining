"""
Data Repair
===========
Turns every analysed repository record into the compact per-repo summary that
sections_aggregate.py uses, applied in memory at aggregate time
(code_repos.json is never rewritten).

Two record sources:
  * code_specialised_analysis.py records (scanner_version 3, analysis/specialised_repos.json):
    already correct — summarised directly.
  * Legacy code_analysis.py records (code_repos.json), used only for repositories the
    specialised scan has not (yet) covered. Repairs applied:
      1. test_code / source_code re-derived from the repo-relative path, filename test
         rules, and content test rules recovered from the per-file `general_hits`
         (scans below scanner_version 2 matched test dirs on the absolute path and
         never applied the test rules);
      2. .ipynb files moved from 'other' to code;
      3. files whose extension is now in IGNORED_EXTENSIONS dropped;
      4. `total_specific` excludes keywords marked `subset_of`.
    Legacy records still use the old (pre-2026-10-10) technique regexes and the old 5 MB
    file-size limit; only a specialised re-scan fixes those.

Summary fields (per repo): file and code-file counts, lines of code, technique hits,
code-file buckets for A3 (technique test / general test / technique non-test /
non-test), whole-repo doc buckets for A4, and zero-hit diagnostics.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from core_helpers import config as cfg
from full_analysis.code_analysis import _TEST_DIR_RE, _aggregate_file_results, SCANNER_VERSION
from core_helpers.utils import load_analysis_keywords, compile_analysis_keywords, load_json

REPAIR_VERSION = 2
_CODE_CATS = ("test_code", "source_code")


class RepairContext:
    def __init__(self, slug: str, analysis_dir: Path, code_paths: bool = True) -> None:
        self.slug         = slug
        self.keywords_raw = load_analysis_keywords(slug)
        compiled          = compile_analysis_keywords(self.keywords_raw)
        tfd               = [k for k in compiled if k.get("apply_to")]
        self.tfd_file     = [k for k in tfd if k["apply_to"] == "filename"]
        self.tfd_content  = [k for k in tfd if k["apply_to"] == "content"]
        self.subset_of    = {k["id"]: k["subset_of"] for k in self.keywords_raw if k.get("subset_of")}
        self.totals = Counter()   # repair statistics across all repos
        # Files GitHub code search matched, per repo — used to diagnose zero-hit repos.
        # (Only needed for legacy records; code_paths=False skips loading code.json.)
        self.code_paths: dict[str, set[str]] = {}
        for it in (load_json(analysis_dir.parent / "search" / "code.json", []) or [] if code_paths else []):
            self.code_paths.setdefault(it.get("repo_full_name", ""), set()).add(it.get("file_path", ""))


def _is_test_file(f: dict, parts: list[str], ctx: RepairContext) -> bool:
    lang = f.get("language")
    for kw in ctx.tfd_file:
        if (not kw.get("language") or kw["language"] == lang) and kw["compiled"].search(parts[-1]):
            return True
    gh = f.get("general_hits") or {}
    for kw in ctx.tfd_content:
        if (not kw.get("language") or kw["language"] == lang) and gh.get(kw["id"]):
            return True
    return any(_TEST_DIR_RE.search(p) for p in parts[:-1])


def repair_record(rec: dict, ctx: RepairContext) -> dict:
    """Repair rec['scan'] in place (legacy records only); return the compact summary."""
    scan = rec.get("scan", {}) or {}
    if (scan.get("scanner_version") or 1) >= 3:
        ctx.totals["records_specialised"] += 1
        return _summarise_v3(rec)
    ctx.totals["records_legacy"] += 1
    legacy = (scan.get("scanner_version") or 1) < SCANNER_VERSION

    files: list[dict] = []
    dropped: Counter = Counter()
    stored_test = derived_test = code_files = 0
    for f in scan.get("file_details", []) or []:
        posix = (f.get("rel_path") or "").replace("\\", "/")
        parts = posix.split("/")
        ext   = Path(parts[-1]).suffix.lower()
        if ext in cfg.IGNORED_EXTENSIONS:
            dropped[ext] += 1
            continue
        cat = f.get("category", "other")
        stored_test += cat == "test_code"
        if ext in cfg.CODE_EXTENSIONS and cat not in _CODE_CATS:
            cat = "source_code"                       # e.g. .ipynb previously 'other'
            if not legacy and _is_test_file(f, parts, ctx):
                cat = "test_code"
        if legacy and cat in _CODE_CATS:
            cat = "test_code" if _is_test_file(f, parts, ctx) else "source_code"
        if cat in _CODE_CATS:
            code_files   += 1
            derived_test += cat == "test_code"
        sh = f.get("specific_hits") or {}
        # Updated in place (millions of file records — copying would double memory).
        f.update(category=cat, rel_path=posix,
                 total_specific=sum(v for k, v in sh.items() if k not in ctx.subset_of and v > 0))
        files.append(f)

    new_scan = _aggregate_file_results(files, ctx.keywords_raw)
    new_scan["scanner_version"] = scan.get("scanner_version", 1)
    new_scan["repair"] = {"version": REPAIR_VERSION, "legacy_reclassified": legacy,
                          "stored_test_files": stored_test, "derived_test_files": derived_test,
                          "code_files": code_files, "dropped_files": dict(dropped)}
    rec["scan"] = new_scan
    ctx.totals.update(stored_test=stored_test, derived_test=derived_test, code_files=code_files,
                      dropped=sum(dropped.values()))
    for e, n in dropped.items():
        ctx.totals[f"dropped{e}"] += n
    return _summarise_legacy(rec, ctx)


def _base(rec: dict, scan: dict, source: str) -> dict:
    return {
        "full_name":      rec.get("full_name", ""),
        "html_url":       rec.get("html_url", ""),
        "stars":          rec.get("stars"),
        "language":       rec.get("language"),
        "created_at":     rec.get("created_at"),
        "description":    (rec.get("description") or "")[:500],
        "topics":         rec.get("topics") or [],
        "readme_snippet": (rec.get("readme_snippet") or "")[:3000],
        "source":         source,
        "snapshot":       rec.get("commit_date") or (rec.get("commits") or {}).get("last_commit_date"),
        "total_files":    scan.get("total_files", 0),
        "total_specific": scan.get("total_specific_hits", 0),
        "kw_hits":        {k: v.get("count", 0) for k, v in (scan.get("hits_by_keyword") or {}).items()},
    }


def _finish(s: dict, code_b: Counter, doc_b: Counter, code_files: int, code_loc: int,
            kw_files: Counter, tech_paths: list[str]) -> dict:
    s.update(code_buckets=dict(code_b), doc_buckets=dict(doc_b), code_files=code_files, code_loc=code_loc,
             kw_files=dict(kw_files), tech_paths=tech_paths,
             test_tech_files=code_b.get("tech_test", 0), src_tech_files=code_b.get("tech_nontest", 0))
    s["code_tech_files"] = s["test_tech_files"] + s["src_tech_files"]
    s["is_usage"] = s["code_tech_files"] > 0
    return s


def _summarise_v3(rec: dict) -> dict:
    scan = rec["scan"]
    s = _base(rec, scan, "specialised")
    kw_files: Counter = Counter()
    tech_paths = []
    for h in scan.get("hit_files", []):
        kw_files.update(h.get("specific_hits", {}).keys())
        if len(tech_paths) < 5:
            tech_paths.append(h["path"])
    s = _finish(s, Counter(scan.get("code_buckets") or {}), Counter(scan.get("doc_buckets") or {}),
                scan.get("code_files", 0), scan.get("code_loc", 0), kw_files, tech_paths)
    if s["total_specific"] == 0:
        mp = scan.get("matched_paths") or {}
        s["matched_paths"] = list(mp)[:5]
        s["matched_causes"] = {p: v.get("cause") for p, v in mp.items() if not v.get("hit")}
        s["zero_hit_reason"] = "no_matched_path" if not mp else "investigated_by_scan"
    return s


def _summarise_legacy(rec: dict, ctx: RepairContext) -> dict:
    scan = rec["scan"]
    s = _base(rec, scan, "legacy")
    code_b, doc_b, kw_files = Counter(), Counter(), Counter()
    code_files = code_loc = 0
    tech_paths: list[str] = []
    for f in scan["file_details"]:
        cat  = f["category"]
        spec = f["total_specific"] > 0
        if cat in _CODE_CATS:
            code_files += 1
            code_loc   += f.get("n_lines") or 0
            if cat == "test_code":
                code_b["tech_test" if spec else "gen_test"] += 1
            else:
                code_b["tech_nontest" if spec else "nontest"] += 1
        if cat == "docs":
            doc_b["tech_doc" if spec else "gen_doc"] += 1
        else:
            doc_b["nondoc_tech" if spec else "nondoc_general"] += 1
        if spec:
            kw_files.update((f.get("specific_hits") or {}).keys())
            if len(tech_paths) < 5:
                tech_paths.append(f["rel_path"])
    s = _finish(s, code_b, doc_b, code_files, code_loc, kw_files, tech_paths)
    if s["total_specific"] == 0:
        matched = ctx.code_paths.get(s["full_name"], set())
        scanned = {f["rel_path"] for f in scan["file_details"]}
        s["matched_paths"] = sorted(matched)[:5]
        s["matched_causes"] = {}
        s["zero_hit_reason"] = ("no_matched_path" if not matched else
                                "matched_file_scanned_no_regex_hit" if matched & scanned else
                                "matched_file_not_in_scan")
    return s
