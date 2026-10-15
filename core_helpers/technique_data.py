"""
PBT / fuzz data preparation and collection (used by non_code_specialised_analysis.py)
======================================================================================
prepare(): streams the multi-GB search files, keeps only results found by explicit-phrase
  search keywords (inputs/comparison_keywords.json), checks every non-code title/body for a
  technique phrase, and draws the seeded random samples (±3% at 95% confidence):
  results/<slug>/filtered/, analysis/code_sample.json, analysis/noncode_sample.json.
fetch_sample_metadata() / fetch_sample_readmes() / fetch_lang_baseline(): GitHub API look-ups
  for the samples (A5–A7).
"""

from __future__ import annotations

import json
import math
import random
import re
import shutil
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from core_helpers import config as cfg
from core_helpers.keyword_matcher import TechniqueMatcher
from core_helpers.utils import resolve_technique, technique_dirs, load_json, save_json, setup_logging, load_search_keywords

SURFACES         = ["code", "repos", "commits", "prs", "issues", "discussions"]
NONCODE_SURFACES = SURFACES[1:]
SEED             = 20261011
MARGIN           = 0.03          # ± margin of error for a proportion, 95% confidence
Z95              = 1.96
OVERDRAW         = 1.08          # extra sampled repos to cover deleted/private repos and failed clones
SIGNAL_REPOS     = 15
TITLE_CHARS      = 300
COMMIT_BODY_CHARS = 1000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def base_keyword(kw: str) -> str:
    m = re.match(r'\s*("[^"]+")', kw or "")
    return m.group(1) if m else (kw or "").split(" ")[0]


def keyword_config(slug: str) -> dict:
    data = (load_json(cfg.INPUTS_DIR / "comparison_keywords.json", {}) or {}).get(slug) or {}
    return {"exclude": list(data.get("exclude_search_keywords", [])),
            "exclude_reason": data.get("exclude_reason", ""),
            "not_run": list(data.get("not_run_search_keywords", [])),
            "not_run_note": data.get("not_run_note", "")}


def cochran(population: int, margin: float = MARGIN) -> int:
    """Sample size for a proportion (p = 0.5, worst case), 95% confidence, finite-population corrected."""
    if population <= 0:
        return 0
    n0 = Z95 ** 2 * 0.25 / margin ** 2
    return min(population, math.ceil(n0 / (1 + (n0 - 1) / population)))


def margin_of_error(n: int, population: int) -> float:
    """± half-width (as a fraction) of the 95% confidence interval for a proportion, worst case."""
    if n <= 0:
        return 1.0
    fpc = math.sqrt((population - n) / (population - 1)) if population > 1 and n < population else 0.0
    return Z95 * math.sqrt(0.25 / n) * fpc


def iter_json_array(path: Path, chunk: int = 1 << 23):
    """Stream the objects of a (possibly multi-GB) top-level JSON array."""
    dec = json.JSONDecoder()
    with open(path, encoding="utf-8") as fh:
        buf, pos = "", 0
        while True:
            if pos > (1 << 22):
                buf, pos = buf[pos:], 0
            data = fh.read(chunk)
            buf += data
            while True:
                while pos < len(buf) and buf[pos] in " \t\r\n,[":
                    pos += 1
                if pos >= len(buf) or buf[pos] == "]":
                    break
                try:
                    obj, end = dec.raw_decode(buf, pos)
                except json.JSONDecodeError:
                    break                          # object continues in the next chunk
                yield obj
                pos = end
            if not data:
                return


def _draw(names: list[str], margin: float = MARGIN) -> dict:
    pop = sorted(names)
    order = pop[:]
    random.Random(SEED).shuffle(order)
    need = cochran(len(pop), margin)
    target = min(len(pop), math.ceil(need * OVERDRAW))
    return {"population": len(pop), "margin": margin, "confidence": 0.95, "n_required": need,
            "overdraw": OVERDRAW, "n_target": target, "seed": SEED, "sample": order[:target],
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


# ---------------------------------------------------------------------------
# 1. prepare
# ---------------------------------------------------------------------------

def prepare(slug: str) -> None:
    from report_helpers.sections_aggregate import strip_agent_lines
    dirs = technique_dirs(slug)
    sd, fdir = dirs["search"], dirs["base"] / "filtered"
    fdir.mkdir(parents=True, exist_ok=True)
    dirs["analysis"].mkdir(parents=True, exist_ok=True)
    kc = keyword_config(slug)
    excl = set(kc["exclude"])
    all_kws = [base_keyword(k) for k in load_search_keywords(slug)]
    history = load_json(sd / "search_history.json", {}) or {}
    ran = {base_keyword(k) for k, v in history.items() if v == "done"}
    kept_kws = [k for k in all_kws if k not in excl]
    kept_set = set(kept_kws)
    matcher = TechniqueMatcher(slug)
    print(f"{slug}: {len(kept_kws)} kept search keywords, {len(excl)} excluded; "
          f"never run: {', '.join(k for k in kept_kws if k not in ran) or 'none'}")

    stats: dict = {"kept_keywords": kept_kws, "excluded_keywords": sorted(excl),
                   "exclude_reason": kc["exclude_reason"], "not_run": [k for k in all_kws if k not in ran],
                   "not_run_note": kc["not_run_note"], "surfaces": {}}
    all_repos_union: set[str] = set()
    query_items: dict[str, dict[str, list[int]]] = {}   # surface -> full query -> [items, relevant items]
    verified_noncode: set[str] = set()
    code_by_repo: dict[str, dict] = {}        # CODE items collapsed per repository (fuzz: 1.5M items)
    t_all = time.time()
    for s in SURFACES:
        path = sd / f"{s}.json"
        t0 = time.time()
        kept: list[dict] = []
        st = Counter()
        repos_all, repos_kept = set(), set()
        if not path.exists():
            print(f"  {s}: missing {path}")
            continue
        for it in iter_json_array(path):
            st["items_all"] += 1
            rn = it.get("repo_full_name")
            if rn:
                repos_all.add(rn)
            kws = {base_keyword(k) for k in (it.get("matched_keywords") or [it.get("matched_keyword")]) if k}
            if not kws & kept_set:
                continue
            st["items_kept"] += 1
            if rn:
                repos_kept.add(rn)
            if s == "code":
                if rn:
                    r = code_by_repo.setdefault(rn, {"kws": set(), "paths": [], "url": it.get("repo_clone_url")})
                    r["kws"] |= kws & kept_set
                    if it.get("file_path") and len(r["paths"]) < 20 and it["file_path"] not in r["paths"]:
                        r["paths"].append(it["file_path"])
                continue
            row = {"id": it.get("id"), "repo_full_name": rn, "repo_id": it.get("repo_id"),
                   "matched_keywords": sorted(kws)}
            body = it.get("body") or ""
            text, agent = strip_agent_lines(f"{it.get('title') or ''}\n{body}")
            hits, _ = matcher.scan_text(text)
            rel = matcher.total(hits) > 0
            st["relevant"] += rel
            if rel and rn:
                verified_noncode.add(rn)
            qi = query_items.setdefault(s, {})
            for q in it.get("matched_keywords") or [it.get("matched_keyword")]:
                if q and base_keyword(q) in kept_set:
                    c = qi.setdefault(q, [0, 0])
                    c[0] += 1
                    c[1] += rel
            row.update(title=(it.get("title") or "")[:TITLE_CHARS], html_url=it.get("html_url"),
                       created_at=it.get("created_at"), _hits=hits, _agent=agent, _rel=rel)
            if s == "commits":
                row.update(body=body[:COMMIT_BODY_CHARS], committer_date=it.get("committer_date"),
                           author_date=it.get("author_date"))
            kept.append(row)
        if s == "code":
            kept = [{"id": rn, "repo_full_name": rn, "matched_keywords": sorted(r["kws"])}
                    for rn, r in sorted(code_by_repo.items())]
        save_json(fdir / f"{s}.json", kept)
        all_repos_union |= repos_all
        stats["surfaces"][s] = {**st, "repos_all": len(repos_all), "repos_kept": len(repos_kept)}
        print(f"  {s:12} items {st['items_all']:>10,} -> {st['items_kept']:>9,} kept | repos {len(repos_all):>8,} -> "
              f"{len(repos_kept):>8,}" + (f" | relevant items {st['relevant']:,}" if s != "code" else "")
              + f"  ({time.time() - t0:.0f}s)", flush=True)
    stats["union_all"] = len(all_repos_union)
    stats["query_items"] = query_items
    stats["prepared_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_json(fdir / "prepare_stats.json", stats)
    for name in ("summary.json", "search_history.json"):
        if (sd / name).exists():
            shutil.copyfile(sd / name, fdir / name)

    code_sample = _draw(sorted(code_by_repo))
    save_json(dirs["analysis"] / "code_sample.json", code_sample)
    save_json(fdir / "code_sample_items.json",
              {rn: {"paths": code_by_repo[rn]["paths"], "url": code_by_repo[rn]["url"],
                    "kws": sorted(code_by_repo[rn]["kws"])} for rn in code_sample["sample"]})
    nc_sample = _draw(sorted(verified_noncode))
    save_json(dirs["analysis"] / "noncode_sample.json", nc_sample)
    print(f"\nCODE sample: {code_sample['n_target']:,} of {code_sample['population']:,} repos "
          f"(±{MARGIN * 100:.0f}% needs {code_sample['n_required']:,}; {OVERDRAW:.2f}× drawn)")
    print(f"A6/A7 sample: {nc_sample['n_target']:,} of {nc_sample['population']:,} verified non-CODE repos "
          f"(needs {nc_sample['n_required']:,})")
    print(f"Done in {(time.time() - t_all) / 60:.1f} min. Next: python code_specialised_analysis.py -t "
          f"{cfg.TECHNIQUE_INPUT_PREFIXES[slug]}")


# ---------------------------------------------------------------------------
# 2. fetch (GitHub API)
# ---------------------------------------------------------------------------

def _copy_baseline(dirs: dict, name: str) -> None:
    """GitHub-wide baselines do not depend on the technique: reuse the most complete copy."""
    dst = dirs["analysis"] / name
    best, best_size = None, dst.stat().st_size if dst.exists() else -1
    for p in cfg.RESULTS_DIR.glob(f"*/analysis/{name}"):
        if p.resolve() != dst.resolve() and p.stat().st_size > best_size:
            best, best_size = p, p.stat().st_size
    if best:
        shutil.copyfile(best, dst)
        print(f"{name}: copied the GitHub-wide baseline from {best.parent.parent.name}")


def _samples(dirs: dict) -> tuple[dict, dict]:
    code_s = load_json(dirs["analysis"] / "code_sample.json", None)
    nc_s = load_json(dirs["analysis"] / "noncode_sample.json", None)
    if not code_s or not nc_s:
        raise SystemExit("Run `python non_code_specialised_analysis.py -t <technique> --prepare` first.")
    return code_s, nc_s


def fetch_sample_metadata(slug: str, logger) -> None:
    """Current repository metadata for both samples → analysis/sample_metadata.json."""
    from core_helpers import github_fetch as fx
    dirs = technique_dirs(slug)
    code_s, nc_s = _samples(dirs)

    def meta_one(name: str):
        time.sleep(0.75)
        r = fx._get(f"{cfg.GITHUB_API_BASE}/repos/{name}", logger)
        if r is None:
            return name, None, False                     # transient — retried next run
        if r.status_code in (404, 451):
            return name, None, True                      # deleted / private / blocked
        if r.status_code != 200:
            return name, None, False
        d = r.json()
        return name, {"full_name": d.get("full_name", name), "stars": d.get("stargazers_count"),
                      "language": d.get("language"), "size_kb": d.get("size", 0),
                      "created_at": d.get("created_at"), "pushed_at": d.get("pushed_at"),
                      "archived": d.get("archived"), "fork": d.get("fork"),
                      "description": d.get("description") or "",
                      "topics": [t for t in d.get("topics", []) if isinstance(t, str)]}, True

    names = sorted(set(code_s["sample"]) | set(nc_s["sample"]))
    fx._fetch_many(names, dirs["analysis"] / "sample_metadata.json", meta_one, "metadata (both samples)", logger)


def fetch_sample_readmes(slug: str, logger) -> None:
    """READMEs of the A6/A7 sample repositories that still exist → analysis/repo_readmes.json."""
    from core_helpers import github_fetch as fx
    dirs = technique_dirs(slug)
    _, nc_s = _samples(dirs)
    meta = load_json(dirs["analysis"] / "sample_metadata.json", {}) or {}
    if not meta:
        raise SystemExit("Run --metadata first (READMEs are fetched only for sampled repositories that still exist).")

    def readme_one(name: str):
        time.sleep(0.75)
        r = fx._get(f"{cfg.GITHUB_API_BASE}/repos/{name}/readme", logger, raw=True)
        if r is None:
            return name, None, False
        if r.status_code == 404:
            return name, None, True
        return name, (r.text[:fx._README_MAX_CHARS] if r.status_code == 200 else None), r.status_code == 200

    nc_alive = [n for n in nc_s["sample"] if meta.get(n)]
    fx._fetch_many(nc_alive, dirs["analysis"] / "repo_readmes.json", readme_one, "READMEs (A6/A7 sample)", logger)


def fetch_lang_baseline(slug: str, logger) -> None:
    """GitHub-wide language counts for A5: reuse another technique's file (the counts are
    GitHub-wide) and add the sample's top languages that it lacks."""
    from core_helpers import github_fetch as fx
    dirs = technique_dirs(slug)
    code_s, _ = _samples(dirs)
    meta = load_json(dirs["analysis"] / "sample_metadata.json", {}) or {}
    _copy_baseline(dirs, "github_language_baseline.json")
    bl_path = dirs["analysis"] / "github_language_baseline.json"
    bl = load_json(bl_path, {}) or {}
    langs = [l for l, _ in Counter((meta.get(n) or {}).get("language") for n in code_s["sample"]
                                   if (meta.get(n) or {}).get("language")).most_common(30)]
    if not bl.get("pushed_since"):
        from datetime import date, timedelta
        bl["pushed_since"] = (date.fromisoformat(cfg.SLICE_END_DATE) - timedelta(days=365)).isoformat()
    bl.setdefault("languages", {})
    if not bl.get("total"):
        r = fx._get(f"{cfg.GITHUB_API_BASE}/search/repositories", logger,
                    params={"q": f"pushed:>={bl['pushed_since']}", "per_page": 1})
        bl["total"] = r.json().get("total_count") if r is not None and r.status_code == 200 else None
    for lang in [l for l in langs if bl["languages"].get(l) is None]:
        time.sleep(cfg.RATE_LIMIT_PAUSE)
        r = fx._get(f"{cfg.GITHUB_API_BASE}/search/repositories", logger,
                    params={"q": f'language:"{lang}" pushed:>={bl["pushed_since"]}', "per_page": 1})
        bl["languages"][lang] = r.json().get("total_count") if r is not None and r.status_code == 200 else None
        print(f"  language baseline {lang}: {bl['languages'][lang]}")
    bl["fetched_at"] = bl.get("fetched_at") or datetime.now(timezone.utc).isoformat()
    save_json(bl_path, bl)
    print(f"language baseline -> {bl_path}")
