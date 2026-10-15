"""
Sections Report
===============
Renders overall.json["sections"] (built by sections_aggregate.py during
`python specialised_report.py -t mt`)
into three files in results/<slug>/sections_report/:

  sections_report.md   tables and plots only (what goes into the write-up)
  sections_issues.md   caveats, decisions, actions, data sources, verification write-ups
  sections_samples.md  every repository / commit list for manual checking
                       (+ usage_repos_for_review.csv)

Agreed scope (2026-10-10): S1, S2, S3 (analysed CODE repos: files / code files / LOC),
S4 (keywords with no results — one sentence), A1, A2, A3 (code files only), A4, A5
(primary language + GitHub-wide normalisation), A6 (+10 samples per domain), A7 (README +
description), T8 + T9 from the COMMITS surface only.

No calculations here beyond formatting.

Usage:
  python specialised_report.py -t mt
"""

from __future__ import annotations

import argparse
import csv
import math
import shutil
from datetime import datetime

from core_helpers import config as cfg
from core_helpers.utils import resolve_technique, technique_dirs, load_json
from full_analysis.report import (
    plt, _PALETTE, _ALL_SURFACES,
    _fmt, _pct, _trunc, _table, _save,
    _bar_chart, _grouped_bar_chart, _line_chart,
)

_NONCODE_SURFACES = ["repos", "commits", "prs", "issues", "discussions"]
_STATS_HEAD = ["Metric", "Min", "P25", "Median", "Avg", "P75", "Max", "Std Dev", "N", "Total"]
_STATS_NOTE = "_P25 / P75 = 25th / 75th percentile: the middle half of repositories lies between them._\n"


def _g(d: dict | None, key):
    """JSON turns int keys into strings — look up either form."""
    d = d or {}
    return d.get(str(key), d.get(key, 0))


def _stats_row(label: str, st: dict, decimals: int = 1) -> list:
    if not st or not st.get("n"):
        return [label] + ["—"] * 7 + ["0", "—"]
    return ([label] + [_fmt(st[k], decimals) for k in ("min", "p25", "median", "mean", "p75", "max", "stdev")]
            + [_fmt(st["n"]), _fmt(st.get("sum"))])


class Ctx:
    KINDS = {"action": "Action needed", "decision": "Decision / assumption", "inconsistent": "Data inconsistency",
             "unavailable": "Data not available", "caveat": "Caveat", "info": "Verified / resolved"}

    def __init__(self, slug: str) -> None:
        self.slug      = slug
        self.dirs      = technique_dirs(slug)
        self.out_dir   = self.dirs["base"] / "sections_report"
        self.plots_dir = self.out_dir / "plots"
        shutil.rmtree(self.plots_dir, ignore_errors=True)        # no stale plots from earlier layouts
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        self.overall   = load_json(self.dirs["analysis"] / "overall.json", {}) or {}
        self.sec       = self.overall.get("sections", {})
        self.notes: list[tuple[str, str, str]] = []
        self.issues: list[str] = []          # long-form issue write-ups
        self.samples: list[str] = []         # repository / commit lists

    def note(self, section: str, kind: str, text: str) -> None:
        self.notes.append((section, self.KINDS[kind], text))

    def plot(self, name: str):
        return self.plots_dir / f"{name}.{cfg.PLOT_FORMAT}"


def _short(ctx: Ctx) -> str:
    return cfg.TECHNIQUE_INPUT_PREFIXES.get(ctx.slug, ctx.slug)


def _excl(ctx: Ctx) -> str:
    return ", ".join(f"`{k}`" for k in ctx.sec.get("exclude_keywords", [])) or "none"


# ---------------------------------------------------------------------------
# SEARCH
# ---------------------------------------------------------------------------

def _s1(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["s1"]["surfaces"]
    out.append("## S1. Search Hits per Search Surface\n")
    out.append("_Raw = sum of GitHub `total_count` over the search keywords (before deduplication; GitHub's own "
               "count, cannot be filtered). Unique = distinct collected items that are verified: non-CODE — the "
               "title/body contains a technique keyword; CODE — the repository's current snapshot has a technique "
               "hit. Unverified results are treated as not found (sections_excluded.md)._\n")
    out.append(_table(["Surface", "Raw Search Hits", "Unique Results"],
                      [[s.upper(), _fmt(d[s]["raw_comparable"]), _fmt(d[s]["unique_comparable"])]
                       for s in _ALL_SURFACES]) + "\n")
    if ctx.sec.get("exclude_keywords"):
        ctx.issues.append("## S1/S2 — Results found only by excluded search keywords\n")
        ctx.issues.append(f"_Search results found only by {_excl(ctx)} are left out of every section. Figures with "
                          "them included, for reference:_\n")
        d2 = ctx.sec["s2"]
        ctx.issues.append(_table(["Surface", "Raw hits (all keywords)", "Unique results (all keywords)",
                                  "Distinct repos (all keywords)", "Distinct repos (reported)"],
                                 [[s.upper(), _fmt(d[s]["raw_all"]), _fmt(d[s]["unique_all"]), _fmt(d2["repos_all"][s]),
                                   _fmt(d2["repos"][s])] for s in _ALL_SURFACES]) + "\n")
        ctx.note("S1", "info", f"Results found only by {_excl(ctx)} are excluded (GitHub ignores the '@' and searches the "
                 "bare word); all-keyword figures are in the S1/S2 section below.")
    out.append(f"![Search hits]({_grouped_bar_chart([s.upper() for s in _ALL_SURFACES], {'Raw search hits': [d[s]['raw_comparable'] for s in _ALL_SURFACES], 'Unique results': [d[s]['unique_comparable'] for s in _ALL_SURFACES]}, 'Search Hits per Surface', 'Surface', 'Count', ctx.plot('s1_hits_per_surface'), figsize=(9, 4.5))})\n")
    for b in ctx.sec["s1"].get("unique_gt_raw", []):
        ctx.note("S1", "caveat", f"{b['surface'].upper()} {b['keyword']}: {b['api_hit_count']:,} raw < "
                 f"{b['new_unique']:,} collected — GitHub's `total_count` is an estimate; raw hits are approximate.")
    _truncation_note(ctx)


def _truncation_note(ctx: Ctx) -> None:
    """Capped search queries (search.log) and whether --fill-capped re-collected them."""
    from core_helpers.fill_capped import capped_queries
    capped = capped_queries(ctx.slug)
    fill = load_json(ctx.dirs["search"] / "capped_fill.json", {}) or {}
    if not capped:
        ctx.note("S1", "info", "Search truncation: no query of a kept search keyword hit GitHub's 1,000-result cap.")
        return
    missing = sum(c["total_before"] - c["retrieved_before"] for c in capped)
    desc = "; ".join(f"{c['surface'].upper()} {c['keyword']} {c['start']}..{c['end']} "
                     f"({c['retrieved_before']:,} of {c['total_before']:,})" for c in capped)
    done = [v for v in fill.values() if v.get("done")]
    if len(done) >= len(capped):
        left = sum(v.get("still_truncated", 0) for v in done)
        ctx.note("S1", "info", f"Search truncation: {len(capped)} queries hit GitHub's 1,000-result cap ({desc}). "
                 f"They were re-collected in finer time slices (`--fill-capped`): {sum(v['new_items'] for v in done):,} "
                 f"items added" + (f"; about {left:,} results still beyond the cap." if left else "; nothing is missing now."))
    else:
        ctx.note("S1", "caveat", f"Search truncation: {len(capped)} queries hit GitHub's 1,000-result cap ({desc}); at most "
                 f"{missing:,} results (GitHub's estimate, overlapping between keywords) were not collected; every other "
                 f"query was collected completely. `non_code_specialised_analysis.py -t {_short(ctx)} --fill-capped` "
                 f"re-collects them if needed.")


def _s2(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["s2"]
    out.append("## S2. Distinct Repositories per Search Surface\n")
    out.append("_Each verified result counted once per owning repository (non-CODE: ≥1 item whose title/body contains "
               "a technique keyword; CODE: current snapshot has ≥1 technique hit). Repositories without a verified "
               "result are listed in sections_excluded.md._\n")
    rows = [[s.upper(), _fmt(d["repos"][s])] for s in _ALL_SURFACES]
    rows.append(["**All surfaces (union)**", f"**{_fmt(d['union'])}**"])
    out.append(_table(["Surface", "Distinct Repos"], rows) + "\n")
    out.append(f"![Repos per surface]({_bar_chart([s.upper() for s in _ALL_SURFACES], [d['repos'][s] for s in _ALL_SURFACES], 'Distinct Repositories per Search Surface', 'Surface', 'Repositories', ctx.plot('s2_repos_per_surface'), figsize=(9, 4.5))})\n")
    out.append("_Number of surfaces each repository appears on:_\n")
    out.append(_table(["Surfaces", "Repos", "% of union"],
                      [[k, _fmt(v), _pct(v / d["union"] * 100)] for k, v in d["overlap"].items()]) + "\n")

def _s3(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["s3"]
    out.append("## S3. Size of Analysed CODE-Surface Repositories\n")
    out.append(f"_{d['repos']:,} CODE-surface repositories (verified, see A2). Files = scannable files; lines of code = "
               "lines in code files only._\n")
    out.append(_table(_STATS_HEAD, [_stats_row("Files per repo", d["files"], 0),
                                    _stats_row("Code files per repo", d["code_files"], 0),
                                    _stats_row("Lines of code per repo", d["code_loc"], 0)]) + "\n")
    out.append(_STATS_NOTE)
    if d["by_source"].get("legacy"):
        ctx.note("S3", "caveat", f"{d['by_source']['legacy']:,} repos still use the legacy scan (5 MB file limit, "
                 "files written before the fix); their counts are slightly lower. Re-scan with code_specialised_analysis.py.")


def _s4(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["s4"]
    out.append("## S4. Keywords Without Results\n")
    parts = []
    for s in _ALL_SURFACES:
        miss = d["by_surface"][s]["no_collected_items"]
        if miss:
            parts.append(f"**{s.upper()}**: {', '.join(m.strip(chr(34)) for m in miss)}")
    n = len(d["keywords"])
    out.append(("Of the " + str(n) + " search keywords, the following returned no results: "
                + "; ".join(parts) + ".") if parts else f"All {n} search keywords returned results on every surface.")
    out.append("\n")


# ---------------------------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------------------------

def _a1(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["a1"]
    out.append("## A1. Top Analysis Keyword Hits\n")
    out.append("_One hit = one line matching one technique regex (a phrase wrapped over two lines counts once). "
               "**⊂ parent** = comment/string variant also counted by its parent; excluded from totals._\n")
    out.append(f"### (a) CODE surface — {d['code_repos']:,} analysed repositories\n")
    out.append(_table(["#", "Keyword", "Hits", "Files", "Repos"],
                      [[i + 1, r["label"] + (f" ⊂ {r['subset_of']}" if r["subset_of"] else ""),
                        _fmt(r["hits"]), _fmt(r["files"]), _fmt(r["repos"])] for i, r in enumerate(d["code"])]) + "\n")
    main = [r for r in d["code"] if not r["subset_of"]][:20]
    if main:
        out.append(f"![Code keyword hits]({_bar_chart([_trunc(r['label'], 40) for r in main], [r['hits'] for r in main], 'Analysis Keyword Hits — CODE Surface', 'Hits', 'Keyword', ctx.plot('a1_code_keywords'), horizontal=True, figsize=(9, max(4, len(main) * 0.35 + 2)))})\n")
    out.append(f"### (b) Non-CODE surfaces — {d['noncode_items']:,} search-result titles and bodies\n")
    out.append(_table(["#", "Keyword"] + [s.upper() for s in _NONCODE_SURFACES] + ["Total Hits", "Items"],
                      [[i + 1, r["label"] + (f" ⊂ {r['subset_of']}" if r["subset_of"] else "")]
                       + [_fmt(r["by_surface"][s]) for s in _NONCODE_SURFACES] + [_fmt(r["hits"]), _fmt(r["items"])]
                       for i, r in enumerate(d["noncode"])]) + "\n")
    main = [r for r in d["noncode"] if not r["subset_of"]][:20]
    if main:
        out.append(f"![Non-code keyword hits]({_bar_chart([_trunc(r['label'], 40) for r in main], [r['hits'] for r in main], 'Analysis Keyword Hits — Non-CODE Surfaces', 'Hits', 'Keyword', ctx.plot('a1_noncode_keywords'), horizontal=True, color=_PALETTE[1], figsize=(9, max(4, len(main) * 0.35 + 2)))})\n")


_ZERO_CAUSES = {
    "missing_at_snapshot":           "Matched file no longer exists in the analysed snapshot (deleted/renamed after the search)",
    "missing_at_analysed_commit":    "Matched file no longer existed at the analysed commit (deleted/renamed after the search)",
    "file_not_scannable":            "Matched file is skipped by the scanner (ignored extension, skipped directory, empty or binary)",
    "has_hits_but_was_not_scanned":  "Matched file has hits but was skipped by the legacy scan",
    "phrase_split_across_lines":     "Phrase wrapped over two lines (legacy scan only; the current scan counts these)",
    "identifier_with_prefix":        "'metamorphic' only inside a longer identifier that is not a technique keyword (e.g. assertMetamorphicResult, antimetamorphic)",
    "phrase_regex_gap":              "Phrase form not covered by the regexes (e.g. `Metamorphictests`)",
    "bare_word_metamorphic":         "Only the bare word 'metamorphic' — no technique phrase (search false positive)",
    "match_in_path_only":            "'metamorphic' only in the file path, not the content",
    "no_technique_word_in_file":     "File has no 'metamorphic' at all — GitHub's index held an older version",
    "matched_file_scanned_no_regex_hit": "Legacy: matched file scanned, no regex hit (not investigated)",
    "matched_file_not_in_scan":      "Legacy: matched file not in the scan (not investigated)",
    "no_matched_path":               "No matched file path recorded",
}


def _a2(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["a2"]
    st = d["status"]
    ex = (ctx.sec.get("excluded") or {}).get("code_reasons", {})
    inc = d["usage"] + d["non_usage"]
    out.append("## A2. Cloned Repository Classification\n")
    out.append("_Usage = ≥1 code file (test or source, incl. `.ipynb`) with a technique hit · Non-Usage = ≥1 technique "
               "hit, none in code files. Only repositories whose current snapshot has a technique hit are included; "
               "the rest are listed with reasons in sections_excluded.md._\n")
    out.append(_table(["CODE-surface repositories", "Repos"], [
        ["Found by search", _fmt(st.get("searched"))],
        ["Excluded: no longer available (deleted / private / disabled)", _fmt(ex.get("no longer available", 0))],
        ["Excluded: scan failed or not scanned", _fmt(ex.get("scan failed", 0) + ex.get("not scanned yet", 0) + ex.get("not scanned", 0))],
        ["Excluded: no technique hit in the current snapshot", _fmt(ex.get("no technique hit now", 0))],
        ["**Included**", f"**{_fmt(inc)}**"],
    ]) + "\n")
    out.append(_table(["Group", "Repos", "% of included"], [
        ["Usage", _fmt(d["usage"]), _pct(d["usage"] / max(inc, 1) * 100)],
        ["Non-Usage", _fmt(d["non_usage"]), _pct(d["non_usage"] / max(inc, 1) * 100)],
    ]) + "\n")
    out.append(f"![Usage split]({_bar_chart(['Usage', 'Non-Usage'], [d['usage'], d['non_usage']], 'CODE-Surface Repositories by Group', 'Group', 'Repositories', ctx.plot('a2_usage_split'))})\n")
    if st.get("excluded"):
        ctx.note("A2", "info", f"{st['excluded']} CODE repos found only by {', '.join(st.get('excluded_keywords', []))} "
                 "are not part of the search results (bare-word search).")
    if st.get("specialised_failed"):
        ctx.note("A2", "action", f"{st['specialised_failed']:,} repos failed to clone (connection stalled or timed out) and are excluded. Re-run "
                 "the shard's command to retry them, then --merge and specialised_report.py.")

def _bucket_table(ctx: Ctx, out: list[str], d: dict, labels: list[tuple[str, str]], title: str, plot: str,
                  color: str, of_what: str) -> None:
    b = d["buckets"]
    pooled = sum(v["files"] for v in b.values()) or 1
    out.append(_table(["Category", f"Avg % of {of_what} per Repo", "Median %", "Files (pooled)", "% of Pooled Files"],
                      [[lbl, _pct(b[k]["avg_pct"]), _pct(b[k]["median_pct"]), _fmt(b[k]["files"]),
                        _pct(b[k]["files"] / pooled * 100)] for k, lbl in labels]) + "\n")
    out.append(f"![{title}]({_bar_chart([l for _, l in labels], [b[k]['avg_pct'] for k, _ in labels], title, 'Category', f'Avg % of {of_what} per repo', ctx.plot(plot), color=color, bar_fmt='{:.1f}%')})\n")


def _a3(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["a3"]
    u = d["usage"]
    out.append('## A3. "Usage" Repository Code-File Classification\n')
    out.append(f"_{u['repos']:,} usage repositories; **code files only** (non-code files ignored). Technique test = "
               "test file with a technique hit · General test = test file without · Technique non-test = non-test "
               "code file with a hit · Non-test = non-test code file without. % of the repo's code files, averaged "
               "across repositories._\n")
    _bucket_table(ctx, out, u, [("tech_test", "Technique test"), ("gen_test", "General test"),
                                ("tech_nontest", "Technique non-test"), ("nontest", "Non-test")],
                  "Usage Repos: Code-File Categories", "a3_usage_code_buckets", _PALETTE[0], "code files")
    out.append(f"_{u['repos']:,} usage repositories need manual classification (Actual Usage / Framework / Research "
               "Artifact-Tool / Unknown): list with evidence in `sections_samples.md` and `usage_repos_for_review.csv`._\n")
    ctx.note("A3", "action", "Manually classify the usage repositories (fill `manual_label` in usage_repos_for_review.csv).")
    ctx.note("A3", "caveat", "Test files = filename pattern (test_*.py, *_test.go, *Test.java, *.spec.ts…), pytest/JUnit "
             "import or `@Test`, or a test/tests/testing/spec/e2e directory in the repo-relative path. Languages "
             "without such rules (C/C++, Haskell, plain JS) rely on directories; Rust inline `#[cfg(test)]` modules "
             "do not make a source file a test file.")

    rows = d["manual_rows"]
    ctx.samples.append("## A3 — Usage repositories for manual classification\n")
    ctx.samples.append("_Also in `usage_repos_for_review.csv` (empty `manual_label`, `manual_notes`). Evidence only._\n")
    ctx.samples.append(_table(["Repository", "Stars", "Language", "Tech Test Files", "Tech Non-test Files",
                               "Sample Technique Files", "Description / README excerpt"],
                              [[f"[{r['repo']}](https://github.com/{r['repo']})",
                                _fmt(r["stars"]) if r["stars"] is not None else "—", r["language"] or "—",
                                r["technique_test_files"], r["technique_source_files"],
                                "<br>".join(f"`{p}`" for p in r["sample_technique_files"][:3]),
                                _trunc((r["description"] or r["readme_excerpt"]).replace("|", "/"), 160)]
                               for r in rows]) + "\n")
    with open(ctx.out_dir / "usage_repos_for_review.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["repo", "url", "stars", "language", "scan", "technique_test_files", "technique_nontest_files",
                    "code_files", "sample_technique_files", "description", "readme_excerpt", "manual_label", "manual_notes"])
        for r in rows:
            w.writerow([r["repo"], f"https://github.com/{r['repo']}", r["stars"], r["language"], r["source"],
                        r["technique_test_files"], r["technique_source_files"], r["code_files"],
                        "|".join(r["sample_technique_files"]), r["description"], r["readme_excerpt"], "", ""])


def _a4(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["a4"]
    out.append('## A4. "Non-Usage" Repository File Classification\n')
    out.append(f"_{d['repos']:,} non-usage repositories (≥1 technique hit, none in code files). Technique doc = doc file "
               "with a hit · General doc = doc file without · General technique = non-doc file with a hit · "
               "General = non-doc file without. % of all the repo's files, averaged across repositories._\n")
    _bucket_table(ctx, out, d, [("tech_doc", "Technique doc"), ("gen_doc", "General doc"),
                                ("nondoc_tech", "General technique"), ("nondoc_general", "General")],
                  "Non-Usage Repos: File Categories", "a4_nonusage_buckets", _PALETTE[1], "files")


def _a5(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["a5"]
    rows = d["rows"][:25]
    has_bl = any("lift" in r for r in rows)
    out.append("## A5. Primary Language\n")
    out.append(f"_Primary language (GitHub metadata) of the {d['code_repos']:,} verified CODE-surface repositories "
               f"({d['missing']:,} have none)."
               + (f" GitHub share = share of all public repositories pushed since {d['baseline'].get('pushed_since')} "
                  "(the same 'active in the last year' window as code search). Lift = our share ÷ GitHub share "
                  "(>1 = over-represented)." if has_bl else "") + "_\n")
    head = ["Language", "Repos", "Share"] + (["GitHub Share", "Lift"] if has_bl else [])
    out.append(_table(head, [[r["language"], _fmt(r["repos"]), _pct(r["share_pct"])]
                             + ([_pct(r.get("github_share_pct"), 2) if r.get("github_share_pct") is not None else "—",
                                 _fmt(r.get("lift"), 2) if r.get("lift") is not None else "—"] if has_bl else [])
                             for r in rows]) + "\n")
    out.append(f"![Primary languages]({_bar_chart([r['language'] for r in rows], [r['repos'] for r in rows], 'Primary Language — CODE-Surface Repositories', 'Repositories', 'Language', ctx.plot('a5_primary_language'), horizontal=True, figsize=(8, max(4, len(rows) * 0.3 + 2)))})\n")
    if has_bl:
        lr = [r for r in rows if r.get("lift") is not None]
        out.append(f"![Language lift]({_bar_chart([r['language'] for r in lr], [r['lift'] for r in lr], 'Language Lift vs GitHub (share ÷ GitHub share)', 'Lift', 'Language', ctx.plot('a5_language_lift'), horizontal=True, color=_PALETTE[2], figsize=(8, max(4, len(lr) * 0.3 + 2)), bar_fmt='{:.2f}')})\n")
        ctx.note("A5", "caveat", "GitHub-wide counts come from repository search `total_count` (approximate) and only "
                 "count each repository's primary language.")
    else:
        ctx.note("A5", "action", f"Run `python non_code_specialised_analysis.py -t {_short(ctx)} --lang-baseline` (~30 API search calls) "
                 "to add GitHub-wide language shares and the lift column.")


def _a6(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["a6"]
    n = d["repos_verified"] or 1
    out.append("## A6. Application Domain\n")
    k = d.get("readme_min_distinct", 2)
    out.append(f"_{d['repos_verified']:,} non-CODE repositories with ≥1 relevant item ({d['readme_coverage']:,} with a "
               "README); one count per repository, several domains possible; word-boundary keyword matching "
               "(`inputs/domain_keywords.json`). Description + topics: any domain keyword. + README: the README adds a "
               f"domain only if it contains ≥{k} different keywords of that domain._\n")
    doms = sorted(cfg.DOMAIN_KEYWORDS, key=lambda x: -_g(d["with_readme"], x))
    rows = [[x.replace("_", " ").title(), _fmt(_g(d["desc_topics"], x)), _pct(_g(d["desc_topics"], x) / n * 100),
             _fmt(_g(d["with_readme"], x)), _pct(_g(d["with_readme"], x) / n * 100)] for x in doms]
    rows.append(["_No domain matched_", _fmt(d["no_match_desc_topics"]), _pct(d["no_match_desc_topics"] / n * 100),
                 _fmt(d["no_match_with_readme"]), _pct(d["no_match_with_readme"] / n * 100)])
    out.append(_table(["Domain", "Repos (description + topics)", "%", "Repos (+ README)", "%"], rows) + "\n")
    out.append(f"![Domains]({_grouped_bar_chart([x.replace('_', ' ') for x in doms], {'Description + topics': [_g(d['desc_topics'], x) for x in doms], '+ README': [_g(d['with_readme'], x) for x in doms]}, 'Application Domain — Non-CODE Repositories', 'Domain', 'Repositories', ctx.plot('a6_domains'), figsize=(11, 4.5))})\n")
    ctx.note("A6", "caveat", "Heuristic keyword matching; verify with the 10 random repos per domain in sections_samples.md. "
             "Generic keywords (api, rest, react, query, security…) still match broadly; a README needs "
             f"≥{k} different keywords of a domain to count.")
    if not d["readme_coverage"]:
        ctx.note("A6", "action", f"Run `python non_code_specialised_analysis.py -t {_short(ctx)} --readmes` to add README text.")

    ctx.samples.append("## A6 — 10 random repositories per domain (manual verification)\n")
    ctx.samples.append("_Seeded random sample from repositories matched on metadata. 'Matched' = the text that "
                       "triggered the domain. Mark each as correct / incorrect to estimate precision._\n")
    for dom in doms:
        rows = d["samples"].get(dom, [])
        if not rows:
            continue
        ctx.samples.append(f"### {dom.replace('_', ' ').title()}\n")
        ctx.samples.append(_table(["Repository", "Description", "Matched", "From", "Also matched", "Correct?"],
                                  [[f"[{r['repo']}](https://github.com/{r['repo']})",
                                    _trunc(r["description"].replace("|", "/"), 120) or "—",
                                    ", ".join(f"`{m}`" for m in r["matched"]), r.get("source", ""),
                                    ", ".join(r["other_domains"]) or "—", ""] for r in rows]) + "\n")


def _wordcloud(freq: dict, title: str, path) -> str:
    try:
        from wordcloud import WordCloud
    except ImportError:
        top = list(freq.items())[:30]
        return _bar_chart([w for w, _ in top], [c for _, c in top], title, 'Repos', 'Word', path, horizontal=True, figsize=(8, 9))
    wc = WordCloud(width=1000, height=500, background_color="white", max_words=150, colormap="tab10",
                   relative_scaling=0.5).generate_from_frequencies({w: math.sqrt(c) for w, c in freq.items()})
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(title)
    return _save(fig, path)


def _a7(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["a7"]
    out.append("## A7. Word Cloud Analysis\n")
    out.append(f"_README + project description of the {d['repos']:,} verified non-CODE repositories "
               f"({d['with_readme']:,} with a README). Each word counts once per repository; stopwords removed; "
               "size ∝ √frequency._\n")
    if not d["freq"]:
        return
    if d["whitelist_freq"]:
        out.append("### Domain vocabulary\n")
        out.append(f"![Word cloud domain]({_wordcloud(d['whitelist_freq'], 'Word Cloud — Domain Vocabulary', ctx.plot('a7_wordcloud_domain'))})\n")
    out.append("### All words\n")
    out.append(f"![Word cloud]({_wordcloud(d['freq'], 'Word Cloud — README + Description', ctx.plot('a7_wordcloud_all'))})\n")
    top, wl = list(d["freq"].items())[:40], list(d["whitelist_freq"].items())[:40]
    out.append(_table(["#", "Domain word", "Repos", "Word (all)", "Repos"],
                      [[i + 1, wl[i][0] if i < len(wl) else "", _fmt(wl[i][1]) if i < len(wl) else "",
                        top[i][0] if i < len(top) else "", _fmt(top[i][1]) if i < len(top) else ""]
                       for i in range(max(len(top), len(wl)))]) + "\n")
    nn, no = d["noise_new"], d["noise_old"]
    ctx.issues.append("## A7 — Does README + description reduce noise?\n")
    ctx.issues.append(_table(["Text used", "Top-50 words that are agent/process words", "Top-50 words in domain vocabulary", "Top 10 words"], [
        ["Previous: relevant issue/PR/commit text + description + topics", _pct(no["top50_process_pct"]),
         _pct(no["top50_domain_vocab_pct"]), ", ".join(no["top10"])],
        ["Now: README + description", _pct(nn["top50_process_pct"]), _pct(nn["top50_domain_vocab_pct"]), ", ".join(nn["top10"])],
    ]) + "\n")
    verdict = "less" if nn["top50_process_pct"] < no["top50_process_pct"] else "not less"
    ctx.note("A7", "info" if verdict == "less" else "caveat",
             f"README + description is {verdict} noisy: {nn['top50_process_pct']:.0f}% vs {no['top50_process_pct']:.0f}% "
             "agent/process words among the top 50 (details below).")
    if not d["with_readme"]:
        ctx.note("A7", "action", f"No READMEs fetched yet — the cloud uses descriptions only. Run "
                 f"`python non_code_specialised_analysis.py -t {_short(ctx)} --readmes`.")


# ---------------------------------------------------------------------------
# TIMELINE
# ---------------------------------------------------------------------------

def _t8(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["t8"]
    years = d["years"]
    out.append("## T8. Repositories by Year of Their First Commit Mentioning the Technique (COMMITS Surface)\n")
    out.append(f"_Each of the {d['repos_total']:,} repositories counted once, in the year of its earliest commit whose "
               "message contains a technique keyword. A commit message mentioning the technique does not mean the "
               "technique is in the code._\n")
    out.append(_table(["Year", "Repos (first commit mentioning the technique)", "…that commit agent-marked"],
                      [[y, _fmt(_g(d["adopting_repos"], y)), _fmt(_g(d["adopting_with_agent_first_commit"], y))]
                       for y in years]) + "\n")
    out.append(f"![Repos by first technique commit]({_grouped_bar_chart([str(y) for y in years], {'Repos (first commit mentioning the technique)': [_g(d['adopting_repos'], y) for y in years], 'That commit agent-marked': [_g(d['adopting_with_agent_first_commit'], y) for y in years]}, 'Repositories by Year of First Commit Mentioning the Technique', 'Year', 'Repositories', ctx.plot('t8_first_commit_repos'), figsize=(10, 4.5))})\n")
    cr = d.get("creation") or {}
    if cr.get("by_year"):
        cy = sorted(cr["by_year"], key=int)
        out.append("### Repository creation year\n")
        out.append(f"_Year each of the {cr['repos']:,} repositories with ≥1 relevant commit was created on GitHub._\n")
        out.append(_table(["Year", "Repos created"], [[y, _fmt(_g(cr["by_year"], y))] for y in cy]) + "\n")
        out.append(f"![Repo creation years]({_bar_chart([str(y) for y in cy], [_g(cr['by_year'], y) for y in cy], 'Creation Year of Repositories with Relevant Commits', 'Year', 'Repositories', ctx.plot('t8_repo_creation_years'), figsize=(10, 4.5))})\n")
        if cr.get("estimated"):
            v = cr.get("validation") or {}
            ctx.note("T8", "caveat", f"Creation year of {cr['estimated']:,} of {cr['repos']:,} repositories estimated from "
                     "the GitHub repository ID (IDs are assigned in creation order), interpolated between "
                     f"{cr['reference_repos']:,} repositories with known creation dates; correct year for "
                     f"{v.get('exact_year_pct') or 0:.1f}% of {v.get('checked', 0):,} known repositories checked this way."
                     + (f" {cr['unknown']:,} could not be dated." if cr.get("unknown") else ""))


def _t9(ctx: Ctx, out: list[str]) -> None:
    d = ctx.sec["t9"]
    years = d["years"]
    out.append("## T9. Commit Activity (COMMITS Surface)\n")
    out.append("_Relevant = message contains ≥1 technique keyword; Capped = ≤5 relevant commits per repository per "
               "month; Without top 10 = excluding the 10 repositories with most relevant commits; Agent-marked = "
               "message carries an AI-agent authorship line (lower bound)._\n")
    out.append(_table(["Year", "Relevant", "Capped", "Without top 10", "Agent-marked", "Agent %", "Repos", "Repos with agent commit"],
                      [[y, _fmt(_g(d["relevant"], y)), _fmt(_g(d["relevant_capped"], y)),
                        _fmt(_g(d["relevant_without_top10_repos"], y)), _fmt(_g(d["agent_marked"], y)),
                        _pct(_g(d["agent_marked"], y) / _g(d["relevant"], y) * 100) if _g(d["relevant"], y) else "—",
                        _fmt(_g(d["repos"], y)), _fmt(_g(d["repos_with_agent_commit"], y))] for y in years]) + "\n")
    out.append(f"![Commits by year]({_grouped_bar_chart([str(y) for y in years], {'Relevant': [_g(d['relevant'], y) for y in years], 'Not agent-marked': [_g(d['relevant'], y) - _g(d['agent_marked'], y) for y in years], 'Capped': [_g(d['relevant_capped'], y) for y in years], 'Without top 10 repos': [_g(d['relevant_without_top10_repos'], y) for y in years]}, 'Technique Commits per Year (COMMITS Surface)', 'Year', 'Commits', ctx.plot('t9_commits_by_year'), figsize=(11, 4.5))})\n")
    rbm, abm = d["relevant_by_month"], d["agent_by_month"]
    if rbm:
        months = sorted(rbm)
        xs = list(range(len(months)))
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(xs, [rbm[m] for m in months], color=_PALETTE[0], label="Relevant commits")
        ax.plot(xs, [abm.get(m, 0) for m in months], color=_PALETTE[3], linestyle="--", label="Agent-marked")
        step = max(1, len(months) // 20)
        ax.set_xticks(xs[::step]); ax.set_xticklabels(months[::step], rotation=35, ha="right", fontsize=6)
        ax.set_ylabel("Commits"); ax.set_title("Technique Commits per Month (COMMITS Surface)"); ax.legend(fontsize=8)
        out.append(f"![Commits by month]({_save(fig, ctx.plot('t9_commits_by_month'))})\n")
    _ai_issue(ctx)
    ctx.samples.append(f"## T9 — 50 random relevant commits from {d['peak_year']} (manual check: agent-written?)\n")
    ctx.samples.append(_table(["Repository", "Date", "Agent-marked", "Message (first 300 chars)", "Agent? (manual)"],
                              [[f"[{r['repo']}]({r['url']})", r["date"], "yes" if r["agent_marked"] else "",
                                r["message"].replace("|", "/").replace("`", "'"), ""] for r in d["manual_sample"]]) + "\n")
    ctx.samples.append("## T9 — Repositories with the most relevant commits\n")
    ctx.samples.append(_table(["Repository", "Relevant commits"], [[rn, _fmt(v)] for rn, v in d["top10_repos"]]) + "\n")
    ctx.note("T9", "caveat", f"Commit search covers default branches only, was date-sliced {d['window'][0]} → "
             f"{d['window'][1]}, and keeps fork duplicates (same SHA) once.")


def _ai_issue(ctx: Ctx) -> None:
    t9, t8 = ctx.sec["t9"], ctx.sec["t8"]
    peak = t9["peak_year"]
    if not peak:
        return
    prev = peak - 1
    rel, ag = _g(t9["relevant"], peak), _g(t9["agent_marked"], peak)
    lines = [f"## T8/T9 — Is the {peak} surge real, and is it AI-driven?\n",
             f"**Concentration.** {rel:,} relevant commits in {peak} vs {_g(t9['relevant'], prev):,} in {prev}. "
             f"Capped at 5 per repo per month: {_g(t9['relevant_capped'], peak):,} vs {_g(t9['relevant_capped'], prev):,}. "
             f"Without the top 10 repositories: {_g(t9['relevant_without_top10_repos'], peak):,} vs "
             f"{_g(t9['relevant_without_top10_repos'], prev):,}. Distinct repositories: {_g(t9['repos'], peak):,} vs "
             f"{_g(t9['repos'], prev):,}. Repositories with their first technique-mentioning commit (T8): {_g(t8['adopting_repos'], peak):,} vs "
             f"{_g(t8['adopting_repos'], prev):,}. If the surge survives capping and top-10 removal, it is not driven "
             "by a few very active repositories.\n",
             f"**AI authorship (lower bound).** {ag:,} of {rel:,} relevant {peak} commits ({ag / max(rel, 1) * 100:.0f}%) "
             f"carry an AI-agent authorship line, from {_g(t9['repos_with_agent_commit'], peak):,} repositories; in "
             f"{prev}: {_g(t9['agent_marked'], prev):,} of {_g(t9['relevant'], prev):,}. Agents that leave no trailer "
             "(or users who remove it) are not counted, so the true share is higher. 50 random commits are listed in "
             "sections_samples.md for manual confirmation.\n"]
    cov = ctx.sec.get("coverage") or {}
    if cov:
        lines.append(f"**Does commit search cover inactive repositories?** Of {cov['ok']} sampled COMMITS-surface "
                     f"repositories, {cov['inactive_1y']} had no push since {cov['cutoff']} (inactive >1 year) and "
                     f"{cov['archived']} are archived. "
                     + ("So commit search is **not** limited to recently active repositories (unlike code search)."
                        if cov["inactive_1y"] else "None were inactive — the sample cannot rule out an activity filter.")
                     + "\n")
        ctx.note("T9", "info" if cov["inactive_1y"] else "caveat",
                 f"Commit-search coverage check: {cov['inactive_1y']}/{cov['ok']} sampled repos inactive >1 year, "
                 f"{cov['archived']} archived.")
    else:
        ctx.note("T9", "action", f"Run `python non_code_specialised_analysis.py -t {_short(ctx)} --commit-coverage` (~150 API calls) to "
                 "verify commit search also returns inactive/archived repositories. GitHub's documentation only "
                 "states that commit search covers default branches.")
    bias = ctx.sec.get("bias") or {}
    if bias:
        def share(s, y):
            b = bias.get(s, {})
            return _g(b.get("by_year"), y) / max(b.get("repos", 0), 1) * 100
        lines.append(f"**Creation year by surface.** GitHub code search only indexes repositories active (or returned "
                     f"in search results) in the last year, which is why CODE-surface data is not used for the timeline. "
                     f"Share of repositories created in {peak}: CODE {share('code', peak):.0f}%, REPOS search "
                     f"{share('repos', peak):.0f}%, COMMITS surface {share('commits', peak):.0f}%. Commit search has no "
                     "documented activity restriction, yet its repositories are even more concentrated in "
                     f"{peak} — so the concentration is mainly a genuine surge of new (largely agent-assisted) "
                     "repositories rather than an artefact of the code-search index.\n")
    ctx.issues.extend(lines)
    ctx.note("T8/T9", "info", f"Surge and AI-share verification for {peak}: see the T8/T9 section below.")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _sources_table(ctx: Ctx) -> str:
    st = ctx.sec["a2"]["status"]
    rt = ctx.sec["a3"]["repair_totals"]
    rows = [[f"Excluded from the search population (found only by {', '.join(st.get('excluded_keywords', [])) or '—'})", _fmt(st.get("excluded"))],
            ["CODE-surface repositories found by search", _fmt(st.get("searched"))],
            ["No longer available now (deleted / private / disabled)", _fmt(st.get("gone"))],
            ["Current population", _fmt(st.get("population"))],
            ["Analysed on the current snapshot (code_specialised_analysis.py)", _fmt(st.get("specialised_ok"))],
            ["Included (current snapshot has a technique hit)", _fmt(ctx.sec["a2"]["usage"] + ctx.sec["a2"]["non_usage"])],
            ["Clone failed: stalled or timed out (retry by re-running the shard)", _fmt(st.get("specialised_failed"))],
            ["Not analysed", _fmt(st.get("not_analysed"))]]
    if st.get("legacy_fallback"):
        rows.append(["Legacy search-time records used (use_legacy=True)", _fmt(st.get("legacy_fallback"))])
    if rt.get("records_legacy"):
        rows.append(["Legacy repair: test files stored → re-derived",
                     f"{_fmt(rt.get('stored_test', 0))} → {_fmt(rt.get('derived_test', 0))} of {_fmt(rt.get('code_files', 0))} code files"])
        rows.append(["Legacy repair: binary/generated files dropped", _fmt(rt.get("dropped", 0))])
    return _table(["Data source", "Repos"], rows)


_EXCL_CAUSES = {
    "missing_at_snapshot": "file GitHub matched no longer exists",
    "no_technique_word_in_file": "file no longer contains the technique word",
    "file_not_scannable": "file skipped by the scanner (skipped folder, ignored type, binary)",
    "match_in_path_only": "technique word only in the file path",
    "identifier_with_prefix": "word only inside a longer identifier",
    "phrase_regex_gap": "phrase form not covered by the regexes",
    "bare_word_metamorphic": "only the bare word, no technique phrase",
    "technique_word_without_phrase": "technique word present, but no technique phrase",
}


def write_excluded(ctx, title: str, stamp: str) -> None:
    """sections_excluded.md: every repository treated as not found, with the reason."""
    ex = ctx.sec.get("excluded") or {}
    if not ex:
        return

    def cause_text(detail: str) -> str:
        for k, v in _EXCL_CAUSES.items():
            detail = detail.replace(k, v)
        return detail.replace("|", "/")
    nc_by_surface: dict[str, list] = {}
    for r in ex["noncode"]:
        nc_by_surface.setdefault(r["surface"], []).append(r)
    everywhere = set(ex.get("repos_excluded_everywhere", []))
    md = [f"# {title} — Excluded Results\n",
          f"_Generated {stamp}. Companion to [sections_report.md](sections_report.md). Search results that could not "
          "be verified are treated as if the search had not found them: they appear in no table or plot. "
          f"{len(everywhere):,} repositories are excluded from the whole report; the others below are excluded only on "
          "the surface shown (they appear in the report through another surface)._\n",
          "## Summary\n",
          _table(["Where", "Excluded", "Reason"],
                 [["CODE surface — " + k, _fmt(v), ""] for k, v in sorted(ex.get("code_reasons", {}).items(), key=lambda x: -x[1])]
                 + [[f"{s.upper()} — repositories", _fmt(len(nc_by_surface.get(s, []))), "no collected item's title/body contains a technique keyword"]
                    for s in _NONCODE_SURFACES]
                 + [[f"{s.upper()} — items", _fmt(n), "title/body contains no technique keyword"]
                    for s, n in ex.get("items_dropped", {}).items()]) + "\n",
          "_Non-CODE: GitHub's issue/PR search also matches comments, which were not collected, so many of these probably "
          "mention the technique in a comment. CODE: the search matched GitHub's index at search time; the scan reads "
          "the current snapshot._\n",
          f"## CODE surface ({len(ex['code']):,} repositories)\n",
          _table(["Repository", "Reason", "Detail", "Excluded everywhere"],
                 [[f"[{r['repo']}](https://github.com/{r['repo']})", r["reason"], cause_text(r["detail"] or "—"),
                   "yes" if r["repo"] in everywhere else ""] for r in ex["code"]]) + "\n"]
    for s in _NONCODE_SURFACES:
        rows = nc_by_surface.get(s, [])
        if not rows:
            continue
        md.append(f"## {s.upper()} surface ({len(rows):,} repositories)\n")
        md.append(_table(["Repository", "Items found", "Example item", "Excluded everywhere"],
                         [[f"[{r['repo']}](https://github.com/{r['repo']})", _fmt(r["items"]),
                           (f"[{_trunc((r['example'] or {}).get('title', '').replace('|', '/'), 90) or 'link'}]({(r['example'] or {}).get('url', '')})"
                            if r.get("example") else "—"), "yes" if r["repo"] in everywhere else ""] for r in rows]) + "\n")
    (ctx.out_dir / "sections_excluded.md").write_text("\n".join(md), encoding="utf-8")


def run(slug: str) -> None:
    ctx = Ctx(slug)
    if not ctx.sec or ctx.sec.get("version", 1) < 2:
        print(f"overall.json has no current 'sections' - run: python specialised_report.py -t {slug}")
        return
    title = cfg.TECHNIQUE_DISPLAY_NAMES.get(slug, slug)
    stamp = f"{datetime.now():%Y-%m-%d %H:%M}"
    body = [f"# {title} — Sections Report\n",
            f"_Generated {stamp} from `overall.json` → `sections`. Caveats: [sections_issues.md](sections_issues.md) · "
            "repository lists: [sections_samples.md](sections_samples.md) · results treated as not found: "
            "[sections_excluded.md](sections_excluded.md)._\n", "# Search\n"]
    for fn in (_s1, _s2, _s3, _s4):
        fn(ctx, body)
    body.append("# Analysis\n")
    for fn in (_a1, _a2, _a3, _a4, _a5, _a6, _a7):
        fn(ctx, body)
    body.append("# Timeline (COMMITS surface)\n")
    for fn in (_t8, _t9):
        fn(ctx, body)
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

    smp = [f"# {title} — Samples for Manual Checking\n",
           f"_Generated {stamp}. Companion to [sections_report.md](sections_report.md)._\n"] + ctx.samples
    (ctx.out_dir / "sections_samples.md").write_text("\n".join(smp), encoding="utf-8")
    write_excluded(ctx, title, stamp)
    print(f"Written: {ctx.out_dir / 'sections_report.md'} (+ sections_issues.md, sections_samples.md, "
          "sections_excluded.md, usage_repos_for_review.csv)")


def main() -> None:
    p = argparse.ArgumentParser(description="Render the sections report from overall.json['sections'].")
    p.add_argument("--technique", "-t", required=True, help="mt / fuzz / pbt (or full slug)")
    run(resolve_technique(p.parse_args().technique))


if __name__ == "__main__":
    main()
