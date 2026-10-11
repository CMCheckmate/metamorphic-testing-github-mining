"""
PBT / fuzz aggregate: builds analysis/overall.json["sections"] from the filtered search data,
the scanned CODE sample, the sample metadata and the commit-sampling estimates. Rendered by
other_techniques_report.py. Run through specialised_report.py.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter
from datetime import datetime, timezone

from core_helpers import config as cfg
from core_helpers.keyword_matcher import TechniqueMatcher
from core_helpers.utils import technique_dirs, load_json, save_json
from core_helpers.technique_data import (SURFACES, NONCODE_SURFACES, SEED, SIGNAL_REPOS, Z95, base_keyword,
                                        keyword_config, margin_of_error)


def _code_records(slug: str, dirs: dict, sample: dict, meta: dict) -> tuple[list[dict], dict]:
    from full_analysis.analysis import _is_gone
    spec = load_json(dirs["analysis"] / "specialised_repos.json", {}) or {}
    drawn = list(sample["sample"])
    in_sample = set(drawn)
    gone = {n for n in drawn if n in spec and spec[n].get("status") != "ok" and _is_gone(spec[n])}
    ok = {n: spec[n] for n in drawn if n in spec and spec[n].get("status") == "ok"}
    failed = {n for n in drawn if n in spec and spec[n].get("status") != "ok" and n not in gone}
    for n, r in ok.items():
        r.setdefault("html_url", f"https://github.com/{n}")
        m = meta.get(n) or {}
        for key in ("stars", "language", "created_at", "description", "topics"):
            if r.get(key) in (None, "", []):
                r[key] = m.get(key)
    scanned = len(ok) + len(gone)
    gone_share = len(gone) / scanned if scanned else 0.0
    status = {
        "sample_mode": True, "searched": sample["population"], "population": sample["population"],
        "population_current_est": round(sample["population"] * (1 - gone_share)),
        "gone_share_pct": gone_share * 100, "sample_drawn": len(drawn), "n_required": sample["n_required"],
        "margin_target_pct": sample["margin"] * 100, "gone": len(gone), "gone_repos": sorted(gone),
        "specialised_ok": len(ok), "specialised_failed": len(failed),
        "failed_repos": {n: (spec[n].get("error") or "")[:160] for n in failed},
        "not_scanned_repos": sorted(n for n in drawn if n not in spec),
        "not_analysed": len(drawn) - len(ok) - len(gone),
        "not_scanned": sum(1 for n in drawn if n not in spec),
        "foreign_records": sum(1 for n in spec if n not in in_sample),
        "excluded": 0, "excluded_keywords": [],
    }
    return list(ok.values()), status


_LOG_FETCH = re.compile(r"(\w+) fetch q='(.*?)': total_count=(\d+), retrieved=(\d+)")
_LOG_DATES = re.compile(r"(?:committer-date|created|pushed):(\d{4}-\d\d-\d\d)\.\.(\d{4}-\d\d-\d\d)")
_LOG_SURF  = {"CODE": "code", "REPOS": "repos", "COMMITS": "commits", "PR": "prs", "PRS": "prs",
              "ISSUE": "issues", "ISSUES": "issues", "DISCUSSIONS": "discussions"}
CAP = 990                       # a slice that returned ≥ this many of more results hit GitHub's 1,000 cap


def search_completeness(slug: str, dirs: dict, excl: set[str], query_items: dict) -> dict:
    """How much of what GitHub reported was actually retrieved, from search.log.
    Each logged slice: total_count (GitHub's estimate) vs retrieved (≤ 1,000 per query). A slice is
    'capped' when GitHub reported more results than the 1,000 it returns. total_count also counts
    fork copies of the same commit and, on the commit surface, loose (non-phrase) matches, so
    'retrieved %' is a lower bound of completeness; the relevant share of the items a capped slice
    returned shows whether the cap cut off relevant results (≈100% relevant → yes)."""
    log = dirs["base"] / "search.log"
    if not log.exists():
        return {}
    last: dict[tuple[str, str], tuple[int, int]] = {}
    with open(log, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _LOG_FETCH.search(line)
            if m and m.group(1).upper() in _LOG_SURF:
                q = re.sub(r"\s+type:(?:pr|issue)\s*$", "", m.group(2))      # stored keywords omit the type qualifier
                last[(_LOG_SURF[m.group(1).upper()], q)] = (int(m.group(3)), int(m.group(4)))
    out: dict = {"surfaces": {}, "commits_by_year": {}}
    years: dict[int, Counter] = {}
    for (s, q), (tot, got) in last.items():
        if base_keyword(q) in excl:
            continue
        capped = tot > got and got >= CAP
        a = out["surfaces"].setdefault(s, Counter())
        a["slices"] += 1
        a["capped"] += capped
        a["total_count"] += tot
        a["retrieved"] += min(got, tot) if tot else got
        n, rel = (query_items.get(s, {}).get(q) or [0, 0])
        if capped:
            a["capped_items"] += n
            a["capped_relevant"] += rel
        if s == "commits":
            d = _LOG_DATES.search(q)
            if d:
                a0, b0 = datetime.fromisoformat(d.group(1)), datetime.fromisoformat(d.group(2))
                y = (a0 + (b0 - a0) / 2).year              # slice attributed to its midpoint year
                c = years.setdefault(y, Counter())
                c["slices"] += 1
                c["capped"] += capped
                c["total_count"] += tot
                c["retrieved"] += min(got, tot) if tot else got
    out["surfaces"] = {s: dict(c) for s, c in out["surfaces"].items()}
    out["commits_by_year"] = {y: dict(c) for y, c in sorted(years.items())}
    return out


def _signal_repos(records: list[dict], summaries: list[dict]) -> list[dict]:
    """Random usage repositories with strong signals: technique phrase in ≥1 test code file."""
    by_name = {r["full_name"]: r for r in records}
    strong = sorted(s["full_name"] for s in summaries if s["is_usage"] and s["test_tech_files"] > 0)
    rnd = random.Random(SEED)
    pick = rnd.sample(strong, min(SIGNAL_REPOS, len(strong)))
    if len(pick) < SIGNAL_REPOS:                          # top up with the strongest other usage repos
        rest = sorted((s for s in summaries if s["is_usage"] and s["full_name"] not in pick),
                      key=lambda s: (-s["code_tech_files"], s["full_name"]))
        pick += [s["full_name"] for s in rest[:SIGNAL_REPOS - len(pick)]]
    sm = {s["full_name"]: s for s in summaries}
    rows = []
    for n in pick:
        s, rec = sm[n], by_name[n]
        hf = (rec.get("scan") or {}).get("hit_files") or []
        test_files = [h["path"] for h in hf if h.get("category") == "test_code"]
        code_files = [h["path"] for h in hf if h.get("category") == "source_code"]
        rows.append({"repo": n, "stars": s["stars"], "language": s["language"],
                     "technique_test_files": s["test_tech_files"], "technique_nontest_files": s["src_tech_files"],
                     "hits": s["total_specific"], "files": (test_files + code_files)[:4],
                     "strong": s["test_tech_files"] > 0,
                     "description": (s["description"] or "").replace("\n", " ")[:200]})
    return rows


def aggregate(slug: str) -> dict:
    from report_helpers import sections_aggregate as sa
    from report_helpers.data_repair import RepairContext, repair_record
    dirs = technique_dirs(slug)
    fdir, ad = dirs["base"] / "filtered", dirs["analysis"]
    stats = load_json(fdir / "prepare_stats.json", None)
    code_s, nc_s = load_json(ad / "code_sample.json", None), load_json(ad / "noncode_sample.json", None)
    if not stats or not code_s or not nc_s:
        raise SystemExit("Run `prepare` first.")
    items = {s: load_json(fdir / f"{s}.json", []) or [] for s in SURFACES}
    summary = load_json(fdir / "summary.json", {}) or {}
    meta = load_json(ad / "sample_metadata.json", {}) or {}
    readmes = load_json(ad / "repo_readmes.json", {}) or {}
    kc = keyword_config(slug)
    excl = set(kc["exclude"])
    matcher = TechniqueMatcher(slug)

    flags: dict[tuple[str, str], dict] = {}
    for s in SURFACES:
        for it in items[s]:
            # Verified results only (same rule as MT). CODE: one entry per repository; only the
            # scanned sample can be verified, so CODE counts are estimated from the sample (s2).
            f = {"found": True, "comparable": True}
            if s != "code":
                f.update(relevant=it["_rel"], hits=it["_hits"], agent=it["_agent"], comparable=bool(it["_rel"]),
                         text=f"{it.get('title') or ''}\n{it.get('body') or ''}")
            flags[(s, str(it.get("id")))] = f
    fl = lambda s, it: flags[(s, str(it.get("id")))]

    records, status = _code_records(slug, dirs, code_s, meta)
    rctx = RepairContext(slug, ad, code_paths=False)
    all_summaries = [repair_record(r, rctx) for r in records]
    summaries = [r for r in all_summaries if r["total_specific"] > 0]     # verified CODE repos only

    st = stats["surfaces"]
    out: dict = {"version": sa.SECTIONS_VERSION, "standalone": True, "exclude_keywords": sorted(excl)}
    out["s1"] = sa._s1(summary, items, fl, excl)
    out["s1"]["unique_gt_raw"] = [b for b in out["s1"]["unique_gt_raw"] if base_keyword(b["keyword"]) not in excl]
    for s in SURFACES:
        out["s1"]["surfaces"][s]["unique_all"] = st.get(s, {}).get("items_all", 0)
    # code.json holds one entry per repository: CODE items as found (not verifiable per item).
    out["s1"]["surfaces"]["code"]["unique_comparable"] = st.get("code", {}).get("items_kept", 0)
    out["s2"] = sa._s2(items, fl, summaries)
    out["s2"]["repos_all"] = {s: st.get(s, {}).get("repos_all", 0) for s in SURFACES}
    out["s2"]["union_all"] = stats.get("union_all")
    # CODE: verified share among sampled repos whose state is known now (hit / no hit / deleted).
    n_known = status["specialised_ok"] + status["gone"]
    k = len(summaries)
    p = k / n_known if n_known else 0.0
    N = code_s["population"]
    fpc = math.sqrt((N - n_known) / (N - 1)) if N > 1 and n_known < N else 0.0
    out["s2"]["code_verified_est"] = {"verified": k, "known": n_known, "share": p, "estimate": p * N,
                                      "ci": Z95 * math.sqrt(p * (1 - p) / n_known) * fpc * N if n_known else None}
    nc_sets = {s: {it.get("repo_full_name") for it in items[s] if it.get("repo_full_name") and fl(s, it)["comparable"]}
               for s in NONCODE_SURFACES}
    nc_union = set().union(*nc_sets.values())
    out["s2"]["union_noncode"] = len(nc_union)
    out["s2"]["overlap_noncode"] = {str(c): v for c, v in sorted(Counter(sum(rn in nc_sets[s] for s in NONCODE_SURFACES)
                                                                         for rn in nc_union).items())}
    out["s3"] = sa._s3(summaries)
    out["s4"] = _s4(stats, summary, items)
    out["a1"] = sa._a1(summaries, items, fl, matcher)
    out["a2"] = sa._a2(all_summaries, status, {})
    out["a3"] = sa._a3(summaries, rctx)
    out["a3"]["signal_repos"] = _signal_repos(records, summaries)
    out["a4"] = sa._a4(summaries)
    code_items = {"code": [{"repo_full_name": s["full_name"], "id": s["full_name"]} for s in summaries]}
    out["a5"] = sa._a5(summaries, code_items, lambda s, it: {"comparable": True}, meta,
                       load_json(ad / "github_language_baseline.json", {}) or {})
    nc_alive = {n for n in nc_s["sample"] if meta.get(n)}
    nc_items = {s: [it for it in items[s] if it.get("repo_full_name") in nc_alive] for s in NONCODE_SURFACES}
    out["a6"], out["a7"] = sa._a6_a7(slug, nc_items, fl, meta, readmes)
    out["t8"], out["t9"] = sa._timeline(items["commits"], fl)
    out["t8"]["creation"] = sa.repo_creation_years(items["commits"], fl, meta)
    if (dirs["base"] / "commit_sample" / "strata.json").exists():      # commit_sampling.py results
        from core_helpers import commit_sampling
        out["timeline_estimates"] = commit_sampling.compute_estimates(slug)
    out["sample"] = {
        "code": {k: code_s[k] for k in ("population", "n_required", "n_target", "margin", "seed")},
        "noncode": {k: nc_s[k] for k in ("population", "n_required", "n_target", "margin", "seed")},
        "noncode_alive": len(nc_alive),
        "noncode_fetched": sum(1 for n in nc_s["sample"] if n in meta),
        "noncode_moe_pct": margin_of_error(len(nc_alive), nc_s["population"]) * 100,
        "code_moe_pct": margin_of_error(len(summaries), code_s["population"]) * 100,
    }
    out["keywords"] = {"kept": stats["kept_keywords"], "excluded": stats["excluded_keywords"],
                       "exclude_reason": stats.get("exclude_reason"),
                       "not_run": [k for k in stats.get("not_run", []) if k in stats["kept_keywords"]],
                       "not_run_note": stats.get("not_run_note"),
                       "analysis": [{"id": k["id"], "label": k.get("label"), "regex": k["regex"],
                                     "subset_of": k.get("subset_of")} for k in matcher.keywords]}
    out["completeness"] = search_completeness(slug, dirs, excl, stats.get("query_items") or {})
    out["prepare_stats"] = {k: v for k, v in stats.items() if k != "query_items"}
    out["excluded"] = sa.excluded_results(items, fl, all_summaries, status, code_scope=set(code_s["sample"]))
    out["extras_present"] = {k: (ad / f).exists() for k, f in (
        ("sample_metadata", "sample_metadata.json"), ("repo_readmes", "repo_readmes.json"),
        ("language_baseline", "github_language_baseline.json"),
        ("specialised", "specialised_repos.json"))}
    save_json(ad / "overall.json", {"slug": slug, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "sections": out})
    return out


def _s4(stats: dict, summary: dict, items: dict) -> dict:
    kept, not_run = stats["kept_keywords"], set(stats.get("not_run", []))
    by_surface = {}
    for s in SURFACES:
        matched = Counter(k for it in items[s] for k in it.get("matched_keywords", []))
        kd = {base_keyword(k): d for k, d in summary.get(s, {}).get("keywords", {}).items()}
        by_surface[s] = {"no_collected_items": [k for k in kept if k not in not_run and not matched.get(k)],
                         "no_api_hits": [k for k in kept if k not in not_run and not kd.get(k, {}).get("api_hit_count")]}
    return {"keywords": kept, "not_run": [k for k in kept if k in not_run], "by_surface": by_surface}
