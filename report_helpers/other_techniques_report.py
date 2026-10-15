"""
Other Techniques Report (property-based testing, fuzz testing)
==============================================================
Renders analysis/overall.json["sections"] written by `specialised_report.py
report` into results/<slug>/sections_report/ (sections_report.md, sections_issues.md,
sections_samples.md). Same section numbering as the MT sections report; stand-alone (no
comparison with any other technique). Sections that need cloning or per-repository
metadata are computed on random samples and shown with 95% confidence intervals.

Reuses the generic renderers of sections_report.py; the sample-aware sections are
defined here. No calculations beyond formatting and confidence intervals.

Usage:
  python specialised_report.py -t pbt
"""

from __future__ import annotations

import argparse
import math
from datetime import datetime

from core_helpers import config as cfg
from report_helpers import sections_report as sr
from full_analysis.report import _PALETTE, _ALL_SURFACES, _fmt, _pct, _trunc, _table, _bar_chart, _grouped_bar_chart
from core_helpers.utils import resolve_technique

_NONCODE = sr._NONCODE_SURFACES


def _ci(k: int, n: int, population: int) -> float:
    """± half-width (percentage points) of the 95% CI for k/n, finite-population corrected."""
    if not n:
        return 0.0
    p = k / n
    fpc = math.sqrt((population - n) / (population - 1)) if population > 1 and n < population else 0.0
    return 1.96 * math.sqrt(p * (1 - p) / n) * fpc * 100


def _short(ctx: sr.Ctx) -> str:
    return cfg.TECHNIQUE_INPUT_PREFIXES[ctx.slug]


def _kw(ks: list[str]) -> str:
    return ", ".join(f"`{k}`" for k in ks) or "none"


# ---------------------------------------------------------------------------
# SEARCH
# ---------------------------------------------------------------------------

def _s1(ctx: sr.Ctx, out: list[str]) -> None:
    d, kw = ctx.sec["s1"]["surfaces"], ctx.sec["keywords"]
    out.append("## S1. Search Hits per Search Surface\n")
    out.append(f"_Explicit technique-phrase search keywords only ({len(kw['kept'])}: {_kw(kw['kept'])}). Raw = sum of "
               "GitHub `total_count` over these keywords (before deduplication); Unique = distinct items collected that "
               "are verified (non-CODE: title/body contains a technique phrase). CODE items are shown as found: they can "
               "only be verified by scanning, which is done on a sample (S2, A2)._\n")
    comp = (ctx.sec.get("completeness") or {}).get("surfaces", {})

    def ret(s):
        c = comp.get(s)
        if not c or not c.get("total_count"):
            return "—"
        return f"{_pct(min(c['retrieved'] / c['total_count'] * 100, 100))} ({c['capped']}/{c['slices']} capped)"
    out.append(_table(["Surface", "Raw Search Hits", "Unique Results", "Retrieved ÷ GitHub total (capped slices)"],
                      [[s.upper(), _fmt(d[s]["raw_comparable"]), _fmt(d[s]["unique_comparable"]), ret(s)]
                       for s in _ALL_SURFACES]) + "\n")
    out.append("_GitHub returns at most 1,000 results per query; a date/size slice is **capped** when GitHub "
               "reported more. Surfaces with capped slices are **lower bounds** (see sections_issues.md)._\n")
    _completeness_issue(ctx)
    out.append(f"![Search hits]({_grouped_bar_chart([s.upper() for s in _ALL_SURFACES], {'Raw search hits': [d[s]['raw_comparable'] for s in _ALL_SURFACES], 'Unique results': [d[s]['unique_comparable'] for s in _ALL_SURFACES]}, 'Search Hits per Surface', 'Surface', 'Count', ctx.plot('s1_hits_per_surface'), figsize=(9, 4.5))})\n")

    d2, st = ctx.sec["s2"], ctx.sec["prepare_stats"]["surfaces"]
    ctx.issues.append("## S1/S2 — Results found only by excluded search keywords\n")
    ctx.issues.append(f"_Excluded ({kw.get('exclude_reason') or 'team decision'}): {_kw(kw['excluded'])}. Results found "
                      "only by these keywords are left out of every section. Figures with them included, for reference:_\n")
    ctx.issues.append(_table(["Surface", "Raw hits (all keywords)", "Unique results (all keywords)", "Unique results (reported)",
                              "Distinct repos (all keywords)", "Distinct repos (reported)"],
                             [[s.upper(), _fmt(d[s]["raw_all"]), _fmt(d[s]["unique_all"]), _fmt(d[s]["unique_comparable"]),
                               _fmt(d2["repos_all"].get(s)), _fmt(d2["repos"][s])] for s in _ALL_SURFACES]) + "\n")
    ctx.note("S1", "decision", f"Only explicit technique phrases are counted (team decision); results found only by "
             f"{len(kw['excluded'])} tool/library/API keywords are excluded. All-keyword figures are in the S1/S2 section below.")
    if kw.get("not_run"):
        ctx.note("S1", "caveat", f"Search keywords never run: {_kw(kw['not_run'])}. {kw.get('not_run_note') or ''}")
    for b in ctx.sec["s1"].get("unique_gt_raw", []):
        ctx.note("S1", "caveat", f"{b['surface'].upper()} {b['keyword']}: {b['api_hit_count']:,} raw < "
                 f"{b['new_unique']:,} collected — GitHub's `total_count` is an estimate; raw hits are approximate.")
    ctx.note("S1", "caveat", "Search truncation: GitHub returns ≤1,000 results per query; queries were split by date/size "
             "until each piece had <900 results, but an unsplittable piece is truncated to 1,000.")


def _completeness_issue(ctx: sr.Ctx) -> None:
    comp = ctx.sec.get("completeness") or {}
    if not comp:
        ctx.note("S1", "unavailable", "search.log not found — search completeness (1,000-result cap) cannot be checked.")
        return
    rows = []
    for s in _ALL_SURFACES:
        c = comp["surfaces"].get(s)
        if not c:
            continue
        rel = (f"{_pct(c['capped_relevant'] / c['capped_items'] * 100)} of {_fmt(c['capped_items'])}"
               if c.get("capped_items") else "—")
        rows.append([s.upper(), _fmt(c["slices"]), _fmt(c["capped"]), _fmt(c["total_count"]), _fmt(c["retrieved"]),
                     _pct(min(c["retrieved"] / c["total_count"] * 100, 100)) if c["total_count"] else "—",
                     rel if s != "code" else "n/a"])
    ctx.issues.append("## S1/T9 — Search completeness (GitHub's 1,000-result cap)\n")
    ctx.issues.append("_From search.log, kept keywords only. A slice is capped when GitHub reported more results than "
                      "the 1,000 it returns. GitHub's total also counts fork copies of the same commit/PR and, for commit "
                      "search, loose matches of the words, so 'retrieved %' understates completeness. The last column is "
                      "the share of the items returned by capped slices whose title/body contains a technique phrase: "
                      "close to 100% means the cap cut off relevant results._\n")
    ctx.issues.append(_table(["Surface", "Slices", "Capped", "GitHub total", "Retrieved", "Retrieved %",
                              "Capped slices: relevant items"], rows) + "\n")
    bad = [s.upper() for s in _ALL_SURFACES
           if (comp["surfaces"].get(s) or {}).get("capped")]
    if bad:
        ctx.note("S1", "caveat", f"GitHub's 1,000-result cap truncated search slices on {', '.join(bad)}: counts on these "
                 "surfaces are lower bounds (completeness per surface in S1 and the section below).")


def _s2(ctx: sr.Ctx, out: list[str]) -> None:
    d = ctx.sec["s2"]
    ce = d["code_verified_est"]
    out.append("## S2. Distinct Repositories per Search Surface\n")
    out.append("_Verified repositories only (non-CODE: ≥1 item whose title/body contains a technique phrase; CODE: "
               "current snapshot has ≥1 technique hit). CODE is estimated from the random sample (A2): share of "
               f"sampled repositories with a hit ({ce['verified']:,} of {ce['known']:,}) × the {_fmt(d['repos']['code'])} "
               "CODE repositories found by search; ± = 95% confidence interval._\n")
    rows = [["CODE", f"≈ {_fmt(round(ce['estimate']))}" + (f" ± {_fmt(round(ce['ci']))}" if ce.get("ci") else "")
             if ce["known"] else "— (not scanned yet)"]]
    rows += [[s.upper(), _fmt(d["verified_repos"].get(s))] for s in _NONCODE]
    rows.append(["**Non-CODE surfaces (union)**", f"**{_fmt(d['union_noncode'])}**"])
    out.append(_table(["Surface", "Distinct Repos"], rows) + "\n")
    vals = [round(ce["estimate"]) if ce["known"] else 0] + [d["verified_repos"].get(s, 0) for s in _NONCODE]
    out.append(f"![Repos per surface]({_bar_chart([s.upper() for s in _ALL_SURFACES], vals, 'Distinct Repositories per Search Surface', 'Surface', 'Repositories', ctx.plot('s2_repos_per_surface'), figsize=(9, 4.5))})\n")
    out.append("_Number of non-CODE surfaces each repository appears on:_\n")
    out.append(_table(["Surfaces", "Repos", "% of union"],
                      [[kk, _fmt(v), _pct(v / max(d["union_noncode"], 1) * 100)] for kk, v in d["overlap_noncode"].items()]) + "\n")
    ctx.note("S2", "decision", "CODE repositories cannot all be verified without scanning every one; the CODE row is "
             "estimated from the random sample, and the union / overlap use the non-CODE surfaces only.")

def _s3(ctx: sr.Ctx, out: list[str]) -> None:
    sr._s3(ctx, out)
    out.insert(len(out) - 2, f"_Random sample of the CODE population (see A2); ±{ctx.sec['sample']['code_moe_pct']:.1f}% "
               "margin for proportions; the statistics below describe the sampled repositories._\n")


def _s4(ctx: sr.Ctx, out: list[str]) -> None:
    d = ctx.sec["s4"]
    out.append("## S4. Keywords Without Results\n")
    parts = [f"**{s.upper()}**: {', '.join(m.strip(chr(34)) for m in d['by_surface'][s]['no_collected_items'])}"
             for s in _ALL_SURFACES if d["by_surface"][s]["no_collected_items"]]
    n = len(d["keywords"])
    text = (f"Of the {n} search keywords, the following returned no results: " + "; ".join(parts) + ".") if parts else \
        f"All {n - len(d['not_run'])} search keywords that ran returned results on every surface."
    if d["not_run"]:
        text += f" Not run (search error, not repeated): {', '.join(k.strip(chr(34)) for k in d['not_run'])}."
    out.append(text + "\n")


# ---------------------------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------------------------

def _a1(ctx: sr.Ctx, out: list[str]) -> None:
    start = len(out)
    sr._a1(ctx, out)
    out.insert(start + 2, f"_(a) uses the random CODE sample (A2); (b) uses every collected non-CODE item._\n")


_ZERO_CAUSES = {**sr._ZERO_CAUSES,
                "technique_word_without_phrase": "File contains the technique word but no technique phrase "
                                                 "(e.g. only 'fuzzy'/'fuzzer', or 'property-based' without 'test')",
                "match_in_path_only": "Technique word only in the file path, not the content",
                "no_technique_word_in_file": "File has no technique word at all — GitHub's index held an older version"}


def _a2(ctx: sr.Ctx, out: list[str]) -> None:
    d = ctx.sec["a2"]
    st = d["status"]
    N = st["population"]
    ex = (ctx.sec.get("excluded") or {}).get("code_reasons", {})
    inc = d["usage"] + d["non_usage"]
    known = st["specialised_ok"] + st["gone"]
    out.append("## A2. Cloned Repository Classification\n")
    out.append("_Usage = ≥1 code file (test or source, incl. `.ipynb`) with a technique phrase · Non-Usage = ≥1 "
               "technique hit, none in code files. Seeded random sample of the CODE-surface repositories; only sampled "
               "repositories whose current snapshot has a technique hit are included (the rest: sections_excluded.md). "
               "± = 95% confidence interval._\n")
    out.append(_table(["Population and sample", "Repos"], [
        ["CODE-surface repositories found by search", _fmt(N)],
        [f"Sample size needed for ±{st['margin_target_pct']:.0f}% at 95% confidence", _fmt(st["n_required"])],
        ["Random sample drawn (incl. extra for unavailable repos)", _fmt(st["sample_drawn"])],
        ["… excluded: no longer available (deleted / private / disabled)", _fmt(ex.get("no longer available", 0))],
        ["… excluded: scan failed or not scanned yet", _fmt(ex.get("scan failed", 0) + ex.get("not scanned yet", 0) + ex.get("not scanned", 0))],
        ["… excluded: no technique hit in the current snapshot", _fmt(ex.get("no technique hit now", 0))],
        ["**Included (sample)**", f"**{_fmt(inc)}**"],
        ["Margin of error achieved (95%, worst case)", f"±{d['sample']['moe_95_pct']:.1f}%"],
    ]) + "\n")
    rows = []
    for key, label in (("usage", "Usage"), ("non_usage", "Non-Usage")):
        k = d[key]
        rows.append([label, _fmt(k), f"{_pct(k / inc * 100 if inc else 0)} ± {_ci(k, inc, N):.1f}",
                     f"≈ {_fmt(round(k / known * N))}" if known else "—"])
    out.append(_table(["Group", "Repos (sample)", "% of included (95% CI)", "Estimated repos in population"], rows) + "\n")
    out.append(f"![Usage split]({_bar_chart(['Usage', 'Non-Usage'], [d['usage'], d['non_usage']], 'Sampled CODE-Surface Repositories by Group', 'Group', 'Repositories', ctx.plot('a2_usage_split'))})\n")
    if d["analysed"] < st["n_required"]:
        ctx.note("A2", "action", f"Only {d['analysed']:,} of the {st['n_required']:,} repos needed for ±{st['margin_target_pct']:.0f}% are "
                 f"analysed (±{d['sample']['moe_95_pct']:.1f}% now). Re-run the scan command — finished repos are skipped.")
    if st.get("foreign_records"):
        ctx.note("A2", "inconsistent", f"specialised_repos.json holds {st['foreign_records']:,} repos outside the current "
                 "sample (ignored). Did `prepare` draw a different sample after the scan?")
    ctx.note("A2", "caveat", "Estimated population counts = share of sampled repositories whose state is known (hit, no "
             "hit or deleted) × the CODE repositories found by search.")

def _a3(ctx: sr.Ctx, out: list[str]) -> None:
    d = ctx.sec["a3"]
    u = d["usage"]
    out.append('## A3. "Usage" Repository Code-File Classification\n')
    out.append(f"_{u['repos']:,} usage repositories in the sample; **code files only**. Technique test = test file with a "
               "technique phrase · General test = test file without · Technique non-test = non-test code file with a "
               "phrase · Non-test = non-test code file without. % of the repo's code files, averaged across "
               "repositories._\n")
    sr._bucket_table(ctx, out, u, [("tech_test", "Technique test"), ("gen_test", "General test"),
                                   ("tech_nontest", "Technique non-test"), ("nontest", "Non-test")],
                     "Usage Repos: Code-File Categories", "a3_usage_code_buckets", _PALETTE[0], "code files")
    ctx.note("A3", "caveat", "Test files = filename pattern (test_*.py, *_test.go, *Test.java, *.spec.ts…), pytest/JUnit "
             "import or `@Test`, or a test/tests/testing/spec/e2e directory in the repo-relative path.")
    ctx.note("A3", "decision", "No manual classification for this technique (team decision); "
             f"{len(d['signal_repos'])} random usage repositories with strong signals are listed in sections_samples.md.")
    rows = d["signal_repos"]
    ctx.samples.append(f"## A3 — {len(rows)} random usage repositories with strong signals\n")
    ctx.samples.append("_Seeded random pick from the sampled usage repositories with a technique phrase in ≥1 **test** "
                       "code file (topped up with the usage repositories with most technique code files if fewer). "
                       "Evidence only, not a classification._\n")
    ctx.samples.append(_table(["Repository", "Stars", "Language", "Tech Test Files", "Tech Non-test Files", "Hits",
                               "Example files", "Description"],
                              [[f"[{r['repo']}](https://github.com/{r['repo']})",
                                _fmt(r["stars"]) if r["stars"] is not None else "—", r["language"] or "—",
                                r["technique_test_files"], r["technique_nontest_files"], _fmt(r["hits"]),
                                "<br>".join(f"`{p}`" for p in r["files"]), _trunc(r["description"].replace("|", "/"), 140) or "—"]
                               for r in rows]) + "\n")


def _a5(ctx: sr.Ctx, out: list[str]) -> None:
    d = ctx.sec["a5"]
    rows = d["rows"][:25]
    has_bl = any("lift" in r for r in rows)
    out.append("## A5. Primary Language\n")
    out.append(f"_Primary language (current GitHub metadata) of the {d['code_repos']:,} analysed sample repositories "
               f"({d['missing']:,} have none). Shares carry a ±{ctx.sec['sample']['code_moe_pct']:.1f}% (worst-case) margin."
               + (f" Lift compares like with like over the {d['baseline'].get('languages')} languages with a GitHub-wide "
                  "count: share among our sample repositories in those languages ÷ share among the public repositories in "
                  f"those languages pushed since {d['baseline'].get('pushed_since')}; >1 = over-represented." if has_bl else "")
               + "_\n")
    head = ["Language", "Repos", "Share"] + (["Share (compared languages)", "GitHub Share", "Lift"] if has_bl else [])
    out.append(_table(head, [[r["language"], _fmt(r["repos"]), _pct(r["share_pct"])]
                             + ([_pct(r.get("share_base_pct")) if r.get("share_base_pct") is not None else "—",
                                 _pct(r.get("github_share_pct"), 2) if r.get("github_share_pct") is not None else "—",
                                 _fmt(r.get("lift"), 2) if r.get("lift") is not None else "—"] if has_bl else [])
                             for r in rows]) + "\n")
    out.append(f"![Primary languages]({_bar_chart([r['language'] for r in rows], [r['repos'] for r in rows], 'Primary Language — Sampled CODE-Surface Repositories', 'Repositories', 'Language', ctx.plot('a5_primary_language'), horizontal=True, figsize=(8, max(4, len(rows) * 0.3 + 2)))})\n")
    if has_bl:
        lr = [r for r in rows if r.get("lift") is not None]
        out.append(f"![Language lift]({_bar_chart([r['language'] for r in lr], [r['lift'] for r in lr], 'Language Lift vs GitHub (share ÷ GitHub share)', 'Lift', 'Language', ctx.plot('a5_language_lift'), horizontal=True, color=_PALETTE[2], figsize=(8, max(4, len(lr) * 0.3 + 2)), bar_fmt='{:.2f}')})\n")
        ctx.note("A5", "caveat", "GitHub-wide counts come from repository search `total_count` (approximate) and only "
                 "count each repository's primary language.")
    else:
        ctx.note("A5", "action", f"Run `python non_code_specialised_analysis.py -t {_short(ctx)} --lang-baseline` for the GitHub-wide "
                 "language baseline.")
    if not d["code_repos"]:
        ctx.note("A5", "unavailable", "No analysed sample repositories yet (run the scan and fetch steps).")


def _a6(ctx: sr.Ctx, out: list[str]) -> None:
    smp = ctx.sec["sample"]
    start = len(out)
    sr._a6(ctx, out)
    out.insert(start + 1, f"_Seeded random sample of {smp['noncode']['n_target']:,} of the {smp['noncode']['population']:,} "
               f"verified non-CODE repositories; {smp['noncode_alive']:,} still exist and are counted "
               f"(±{smp['noncode_moe_pct']:.1f}% margin at 95% confidence)._\n")
    if smp["noncode_fetched"] < smp["noncode"]["n_target"]:
        ctx.note("A6", "action", f"Metadata fetched for {smp['noncode_fetched']:,} of {smp['noncode']['n_target']:,} sampled "
                 f"repos. Run `python non_code_specialised_analysis.py -t {_short(ctx)} --metadata --readmes`.")


def _a7(ctx: sr.Ctx, out: list[str]) -> None:
    d = ctx.sec["a7"]
    out.append("## A7. Word Cloud Analysis\n")
    out.append(f"_README + project description of the {d['repos']:,} sampled verified non-CODE repositories "
               f"({d['with_readme']:,} with a README). Each word counts once per repository; stopwords removed; "
               "size ∝ √frequency._\n")
    if not d["freq"]:
        ctx.note("A7", "unavailable", f"No metadata/READMEs yet. Run `python non_code_specialised_analysis.py -t {_short(ctx)} --metadata --readmes`.")
        return
    if d["whitelist_freq"]:
        out.append("### Domain vocabulary\n")
        out.append(f"![Word cloud domain]({sr._wordcloud(d['whitelist_freq'], 'Word Cloud — Domain Vocabulary', ctx.plot('a7_wordcloud_domain'))})\n")
    out.append("### All words\n")
    out.append(f"![Word cloud]({sr._wordcloud(d['freq'], 'Word Cloud — README + Description', ctx.plot('a7_wordcloud_all'))})\n")
    top, wl = list(d["freq"].items())[:40], list(d["whitelist_freq"].items())[:40]
    out.append(_table(["#", "Domain word", "Repos", "Word (all)", "Repos"],
                      [[i + 1, wl[i][0] if i < len(wl) else "", _fmt(wl[i][1]) if i < len(wl) else "",
                        top[i][0] if i < len(top) else "", _fmt(top[i][1]) if i < len(top) else ""]
                       for i in range(max(len(top), len(wl)))]) + "\n")


def _est(ctx: sr.Ctx, key: str) -> dict:
    return ((ctx.sec.get("timeline_estimates") or {}).get(key)) or {}


def _t8_estimates(ctx: sr.Ctx, out: list[str]) -> None:
    est = _est(ctx, "adoption")
    if not est:
        return
    d = ctx.sec["t8"]
    years = sorted(est, key=int)
    out.append("### Repositories by year of first commit mentioning the technique — corrected for the search cap\n")
    out.append("_Collected = first relevant commit in the downloaded data (a lower bound where the commit search was "
               "capped). Estimated = capped date ranges re-sampled (`--commit-sampling`): random time windows "
               "downloaded completely, each repository checked for an earlier relevant commit; ± = 95% confidence "
               "interval (0 = counted exactly)._\n")
    out.append(_table(["Year", "Collected (lower bound)", "Estimated", "95% CI"],
                      [[y, _fmt(sr._g(d["adopting_repos"], y)), _fmt(round(est[y]["estimate"])),
                        "exact" if est[y].get("exact") else f"± {_fmt(round(est[y]['ci']))}"] for y in years]) + "\n")
    fig, ax = sr.plt.subplots(figsize=(10, 4.5))
    xs = list(range(len(years)))
    ax.bar([x - 0.2 for x in xs], [sr._g(d["adopting_repos"], y) for y in years], 0.4, label="Collected (lower bound)",
           color=_PALETTE[0])
    ax.bar([x + 0.2 for x in xs], [est[y]["estimate"] for y in years], 0.4, yerr=[est[y]["ci"] for y in years],
           capsize=3, label="Estimated (95% CI)", color=_PALETTE[1])
    ax.set_xticks(xs); ax.set_xticklabels([str(y) for y in years])
    ax.set_xlabel("Year"); ax.set_ylabel("Repositories"); ax.legend()
    ax.set_title("Repositories by Year of First Commit Mentioning the Technique (corrected for the search cap)")
    out.append(f"![First commit repos estimated]({sr._save(fig, ctx.plot('t8_first_commit_repos_estimated'))})\n")


def _t9_agent_estimates(ctx: sr.Ctx, out: list[str]) -> None:
    est = _est(ctx, "agent")
    if not est:
        return
    d = ctx.sec["t9"]
    years = sorted(est, key=int)
    out.append("### Agent-marked share — corrected for the search cap\n")
    out.append("_Collected = share in the downloaded data. Estimated = capped date ranges re-sampled with random time "
               "windows (`--commit-sampling`); ± = 95% confidence interval in percentage points._\n")
    out.append(_table(["Year", "Collected share", "Estimated share", "95% CI"],
                      [[y, _pct(sr._g(d["agent_marked"], y) / sr._g(d["relevant"], y) * 100) if sr._g(d["relevant"], y) else "—",
                        _pct(est[y]["share"] * 100), "exact" if est[y].get("exact") else f"± {est[y]['ci'] * 100:.1f} pp"]
                       for y in years]) + "\n")


def _t9_completeness(ctx: sr.Ctx, out: list[str]) -> None:
    by_year = (ctx.sec.get("completeness") or {}).get("commits_by_year") or {}
    if not by_year:
        return
    years = sorted(by_year, key=int)
    out.append("### Commit-search completeness per year\n")
    out.append("_Retrieved ÷ GitHub's total_count for the commit-search slices of each year (slice midpoint). Years "
               "with capped slices are lower bounds; GitHub's total includes fork copies and loose word matches._\n")
    out.append(_table(["Year", "Slices", "Capped", "GitHub total", "Retrieved", "Retrieved %"],
                      [[y, _fmt(by_year[y]["slices"]), _fmt(by_year[y]["capped"]), _fmt(by_year[y]["total_count"]),
                        _fmt(by_year[y]["retrieved"]),
                        _pct(min(by_year[y]["retrieved"] / by_year[y]["total_count"] * 100, 100)) if by_year[y]["total_count"] else "—"]
                       for y in years]) + "\n")
    capped = [y for y in years if by_year[y]["capped"]]
    if capped:
        ctx.note("T8/T9", "caveat", f"Commit search hit the 1,000-result cap in {len(capped)} of {len(years)} years "
                 f"({', '.join(str(y) for y in capped)}). Commit counts, first-commit repo counts and agent shares for these years "
                 "are lower bounds, and year-to-year changes between capped and uncapped years are not comparable.")
        parts = [f"{y} ({_pct(min(by_year[y]['retrieved'] / max(by_year[y]['total_count'], 1) * 100, 100))} retrieved)"
                 for y in capped]
        c = (ctx.sec.get("completeness") or {}).get("surfaces", {}).get("commits") or {}
        rel = c["capped_relevant"] / c["capped_items"] * 100 if c.get("capped_items") else None
        ctx.issues.append(f"**Timeline completeness.** Commit-search slices were capped in: {', '.join(parts)}. "
                          + (f"{rel:.0f}% of the commits returned by capped slices contain a technique phrase, so relevant "
                             "commits beyond the first 1,000 per slice were lost. " if rel is not None else "")
                          + "A surge or decline in a capped year cannot be read from these counts.\n")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _sources_table(ctx: sr.Ctx) -> str:
    sec = ctx.sec
    st, ps, smp = sec["a2"]["status"], sec["prepare_stats"], sec["sample"]
    rows = [["Search keywords kept (explicit phrases)", _fmt(len(sec["keywords"]["kept"]))],
            ["Search keywords excluded (tool / library / API)", _fmt(len(sec["keywords"]["excluded"]))],
            ["Search keywords never run", _fmt(len(sec["keywords"]["not_run"]))],
            ["CODE population (repos)", _fmt(st["population"])],
            ["CODE sample drawn / analysed / unavailable / failed",
             f"{_fmt(st['sample_drawn'])} / {_fmt(st['specialised_ok'])} / {_fmt(st['gone'])} / {_fmt(st['specialised_failed'])}"],
            ["Verified non-CODE repos (population) / A6–A7 sample drawn / counted",
             f"{_fmt(smp['noncode']['population'])} / {_fmt(smp['noncode']['n_target'])} / {_fmt(smp['noncode_alive'])}"],
            ["Sample seed", str(smp["code"]["seed"])],
            ["Search data prepared", ps.get("prepared_at", "—")]]
    kws = sec["keywords"]["analysis"]
    return (_table(["Data source", "Value"], rows) + "\n\n_Analysis keywords (`inputs/"
            f"{_short(ctx)}_analysis_keywords.json`):_\n\n"
            + _table(["Keyword", "Regex", "Subset of"],
                     [[k["label"], f"`{k['regex'].replace('|', chr(92) + '|')}`", k["subset_of"] or ""] for k in kws]))


def _fix_commands(ctx: sr.Ctx) -> None:
    """Drop notes that only apply to MT (commit-search coverage is checked once, on MT)."""
    keep = []
    for sec, kind, text in ctx.notes:
        if "--commit-coverage" in text:
            continue                                   # verification of GitHub's commit search, not per technique
        keep.append((sec, kind, text))
    ctx.notes = keep


def run(slug: str) -> None:
    ctx = sr.Ctx(slug)
    if not ctx.sec or not ctx.sec.get("standalone"):
        print(f"No stand-alone sections yet - run: python specialised_report.py -t {slug}")
        return
    title = cfg.TECHNIQUE_DISPLAY_NAMES.get(slug, slug)
    stamp = f"{datetime.now():%Y-%m-%d %H:%M}"
    smp = ctx.sec["sample"]
    n = ctx.sec["a2"]["analysed"]
    sample_txt = (f"a random sample of {n:,} CODE-surface repositories (±{smp['code_moe_pct']:.1f}% at 95% confidence)"
                  if n else "a random CODE-surface sample that has not been scanned yet")
    body = [f"# {title} — Sections Report\n",
            f"_Generated {stamp}. Explicit technique-phrase search results only. Sections that need cloning (S3, A1a, "
            f"A2–A5) use {sample_txt}; A6/A7 use a random sample of verified non-CODE repositories. "
            "Caveats: [sections_issues.md](sections_issues.md) · repository lists: [sections_samples.md](sections_samples.md) · "
            "results treated as not found: [sections_excluded.md](sections_excluded.md)._\n",
            "# Search\n"]
    for fn in (_s1, _s2, _s3, _s4):
        fn(ctx, body)
    body.append("# Analysis\n")
    for fn in (_a1, _a2, _a3, sr._a4, _a5, _a6, _a7):
        fn(ctx, body)
    body.append("# Timeline (COMMITS surface)\n")
    for fn in (sr._t8, _t8_estimates, sr._t9, _t9_agent_estimates, _t9_completeness):
        fn(ctx, body)
    _fix_commands(ctx)
    (ctx.out_dir / "sections_report.md").write_text("\n".join(body), encoding="utf-8")

    order = {k: i for i, k in enumerate(["Action needed", "Decision / assumption", "Data inconsistency",
                                         "Data not available", "Caveat", "Verified / resolved"])}
    iss = [f"# {title} — Issues, Caveats & Verification\n",
           f"_Generated {stamp}. Companion to [sections_report.md](sections_report.md)._\n",
           "## Actions, decisions and caveats\n",
           _table(["#", "Section", "Type", "Note"],
                  [[i + 1, s, k, t] for i, (s, k, t) in enumerate(sorted(ctx.notes, key=lambda n: order.get(n[1], 9)))]) + "\n",
           "## Data sources\n", _sources_table(ctx) + "\n",
           "_Method: see README.md (Reproducing the results)._\n"] + ctx.issues
    (ctx.out_dir / "sections_issues.md").write_text("\n".join(iss), encoding="utf-8")

    smp_md = [f"# {title} — Samples for Manual Checking\n",
              f"_Generated {stamp}. Companion to [sections_report.md](sections_report.md)._\n"] + ctx.samples
    (ctx.out_dir / "sections_samples.md").write_text("\n".join(smp_md), encoding="utf-8")
    sr.write_excluded(ctx, title, stamp)
    print(f"Written: {ctx.out_dir / 'sections_report.md'} (+ sections_issues.md, sections_samples.md)")


def main() -> None:
    p = argparse.ArgumentParser(description="Render the stand-alone PBT / fuzz sections report.")
    p.add_argument("--technique", "-t", required=True, help="pbt / fuzz")
    run(resolve_technique(p.parse_args().technique))


if __name__ == "__main__":
    main()
