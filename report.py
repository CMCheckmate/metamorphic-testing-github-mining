"""
Report Generator
================
Reads overall.json (the single source of truth written by analysis.py) and
code_repos.json, then writes report.md plus all plots to results/<slug>/report/.

The report performs NO calculations — it reads stored values only.

Report structure (9 topic sections):
  1. Projects found & repo sizes
  2. Search keyword hit distribution
  3. Testing technique density
  4. Repo classification
  5. Artifact classification
  6. Language distribution
  7. Application domain
  8. Timeline
  9. All cloned repos
"""

from __future__ import annotations

import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import config as cfg
from utils import technique_dirs, ensure_dirs, load_json

plt.rcParams.update({
    "figure.dpi":       cfg.PLOT_DPI,
    "axes.spines.top":  False,
    "axes.spines.right":False,
    "font.size":        9,
    "axes.titlesize":   10,
    "axes.labelsize":   9,
})
_PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2", "#937860"]
_ALL_SURFACES = ["code", "repos", "commits", "prs", "issues", "discussions"]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt(n, decimals: int = 0) -> str:
    if n is None:
        return "—"
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    if decimals == 0:
        return f"{int(round(v)):,}"
    return f"{v:,.{decimals}f}"


def _trunc(s: str, max_len: int = 35) -> str:
    s = str(s)
    return s if len(s) <= max_len else s[:max_len - 1] + "…"


def _pct(n, decimals: int = 1) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):.{decimals}f}%"
    except (TypeError, ValueError):
        return str(n)


def _table(headers: list[str], rows: list[list]) -> str:
    sep  = "| " + " | ".join("---" for _ in headers) + " |"
    head = "| " + " | ".join(str(h) for h in headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return head + "\n" + sep + "\n" + body


def _stat_cells(stats: dict) -> list:
    return [
        _fmt(stats.get("avg"),    1),
        _fmt(stats.get("median"), 1),
        _fmt(stats.get("max"),    0),
        _fmt(stats.get("min"),    0),
        _fmt(stats.get("stdev"),  1),
        _fmt(stats.get("count"),  0),
    ]


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _save(fig, path: Path) -> str:
    fig.tight_layout()
    fig.savefig(path, dpi=cfg.PLOT_DPI, bbox_inches="tight")
    plt.close(fig)
    return f"plots/{path.name}"


def _bar_chart(
    labels: list[str], values: list[float], title: str, xlabel: str, ylabel: str,
    path: Path, color: str = _PALETTE[0], horizontal: bool = False,
    figsize: tuple = (8, 4), annotate: bool = False,
) -> str:
    fig, ax = plt.subplots(figsize=figsize)
    if horizontal:
        bars = ax.barh(list(reversed(labels)), list(reversed(values)), color=color)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if annotate:
            for bar, v in zip(bars, list(reversed(values))):
                ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                        _fmt(v), va="center", fontsize=7)
    else:
        xs   = range(len(labels))
        bars = ax.bar(xs, values, color=color)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=7)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if annotate:
            for bar, v in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.01,
                        _fmt(v), ha="center", va="bottom", fontsize=7)
    ax.set_title(title)
    return _save(fig, path)


def _bar_chart_with_stats_lines(
    labels: list[str], values: list[float], title: str, xlabel: str, ylabel: str,
    path: Path, color: str = _PALETTE[0], figsize: tuple = (8, 4),
) -> str:
    """Bar chart with count labels, median and mean horizontal lines."""
    fig, ax = plt.subplots(figsize=figsize)
    xs   = range(len(labels))
    bars = ax.bar(xs, values, color=color)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values, default=1) * 0.01,
                _fmt(v), ha="center", va="bottom", fontsize=7)
    if len(values) >= 2:
        med = statistics.median(values)
        mn  = sum(values) / len(values)
        ax.axhline(med, color=_PALETTE[2], linestyle="--", linewidth=1, label=f"Median {_fmt(med)}")
        ax.axhline(mn,  color=_PALETTE[3], linestyle=":",  linewidth=1, label=f"Mean {_fmt(mn, 1)}")
        ax.legend(fontsize=8)
    return _save(fig, path)


def _grouped_bar_chart(
    groups: list[str], series: dict[str, list[float]],
    title: str, xlabel: str, ylabel: str, path: Path,
    figsize: tuple = (10, 5),
) -> str:
    n_groups = len(groups)
    n_series = len(series)
    width    = 0.8 / max(n_series, 1)
    xs       = np.arange(n_groups)
    fig, ax  = plt.subplots(figsize=figsize)
    for idx, (label, vals) in enumerate(series.items()):
        offset = (idx - n_series / 2 + 0.5) * width
        ax.bar(xs + offset, vals, width=width * 0.9, label=label, color=_PALETTE[idx % len(_PALETTE)])
    ax.set_xticks(xs)
    ax.set_xticklabels(groups, rotation=20, ha="right", fontsize=8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8)
    return _save(fig, path)


def _line_chart(
    xs: list, ys: list[float], title: str, xlabel: str, ylabel: str, path: Path,
    add_median: bool = True, add_mean: bool = True, figsize: tuple = (10, 4),
    x_labels: list[str] | None = None,
    extra_lines: list[tuple[list[float], str, str]] | None = None,
) -> str:
    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(xs, ys, color=_PALETTE[0], linewidth=1.2, zorder=3, label=ylabel if extra_lines else None)
    if extra_lines:
        for i, (extra_ys, extra_label, extra_color) in enumerate(extra_lines):
            ax.plot(xs[:len(extra_ys)], extra_ys, color=extra_color,
                    linewidth=1.2, zorder=3, label=extra_label, linestyle="--")
        ax.legend(fontsize=8)
    if add_median and len(ys) > 1 and not extra_lines:
        med = statistics.median(ys)
        ax.axhline(med, color=_PALETTE[2], linestyle="--", linewidth=1, label=f"Median {med:.1f}")
    if add_mean and len(ys) > 1 and not extra_lines:
        mn = sum(ys) / len(ys)
        ax.axhline(mn,  color=_PALETTE[3], linestyle=":",  linewidth=1, label=f"Mean {mn:.1f}")
    if (add_median or add_mean) and not extra_lines and len(ys) > 1:
        ax.legend(fontsize=8)
    if x_labels is not None and len(x_labels) == len(xs):
        step           = max(1, len(x_labels) // 20)
        ax.set_xticks(xs[::step])
        ax.set_xticklabels(x_labels[::step], rotation=35, ha="right", fontsize=6)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    return _save(fig, path)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _section_projects_and_sizes(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 1. Projects Found and Repository Sizes\n")
    out.append(
        "> **Data source:** Search phase — GitHub REST API across all 6 search surfaces "
        "(CODE, REPOS, COMMITS, PRs, ISSUES, DISCUSSIONS) using keywords from "
        f"`inputs/{technique_name}_search_keywords.txt`.\n"
    )

    by_surface  = overall.get("repos_by_surface", {})
    total_repos = overall.get("repos_found_total", 0)

    out.append(f"**{_fmt(total_repos)} distinct repositories** were found across all search surfaces.\n")
    out.append(
        "_A single repository may appear in multiple search surfaces. "
        "'All surfaces combined' is the union — each repo counted once — across all 6 surfaces: "
        "CODE, REPOS, COMMITS, PRs, ISSUES, DISCUSSIONS._\n"
    )

    surf_rows = [[s.upper(), _fmt(by_surface.get(s, 0))] for s in _ALL_SURFACES]
    surf_rows.append(["**All surfaces combined**", f"**{_fmt(total_repos)}**"])
    out.append(_table(["Surface", "Distinct Repos"], surf_rows) + "\n")

    surf_vals   = [by_surface.get(s, 0) for s in _ALL_SURFACES]
    surf_labels = [s.upper() for s in _ALL_SURFACES]
    out.append(f"![Repos per surface]({_bar_chart(surf_labels, surf_vals, 'Distinct Repos per Search Surface', 'Surface', 'Distinct Repo Count', plots_dir / f'repos_per_surface.{cfg.PLOT_FORMAT}', color=_PALETTE[1])})\n")

    # Size stats — grouped bar chart over all 6 surfaces (where data exists)
    size_agg     = overall.get("repo_size_stats", {})
    size_by_surf = size_agg.get("by_surface", {})
    size_overall = size_agg.get("overall", {})
    avail_surfs  = [s for s in _ALL_SURFACES if s in size_by_surf]

    if avail_surfs:
        stat_names  = ["avg", "median", "max", "min"]
        stat_labels = ["Avg", "Median", "Max", "Min"]
        series = {lbl: [size_by_surf[s].get(stat, 0) for s in avail_surfs]
                  for stat, lbl in zip(stat_names, stat_labels)}
        out.append(f"![Size statistics grouped]({_grouped_bar_chart([s.upper() for s in avail_surfs], series, 'Repository Size Statistics (KB) by Search Surface', 'Surface', 'Size (KB)', plots_dir / f'size_stats_grouped.{cfg.PLOT_FORMAT}')})\n")

    size_rows = []
    for s in _ALL_SURFACES:
        st = size_by_surf.get(s)
        if st:
            size_rows.append([s.upper()] + _stat_cells(st))
        else:
            size_rows.append([s.upper(), "—", "—", "—", "—", "—", "0"])
    if size_overall:
        # count is the total union of distinct repos
        row = [s.upper() for s in []]; row = ["**All (combined)**"] + _stat_cells(size_overall)
        size_rows.append(row)
    if size_rows:
        out.append(_table(
            ["Surface", "Avg (KB)", "Median (KB)", "Max (KB)", "Min (KB)", "Std Dev", "Count"],
            size_rows,
        ) + "\n")


def _section_search_distribution(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 2. Search Keyword Hit Distribution\n")
    out.append(
        "> **Data source:** Search phase — GitHub REST API hit counts per keyword per surface. "
        f"Keywords from `inputs/{technique_name}_search_keywords.txt`.\n"
    )

    hit_dists  = overall.get("search_hit_distributions", {})
    search_sum = overall.get("search_summary", {})

    # Aggregate totals per surface — two bar charts with count labels + median/mean lines
    total_hits_per_surf  = [search_sum.get(s, {}).get("search_hit_count", 0) for s in _ALL_SURFACES]
    unique_per_surf      = [search_sum.get(s, {}).get("unique_results", 0)   for s in _ALL_SURFACES]
    surf_labels          = [s.upper() for s in _ALL_SURFACES]

    out.append("### Total Search Hits per Surface\n")
    out.append(f"![Total search hits per surface]({_bar_chart_with_stats_lines(surf_labels, total_hits_per_surf, 'Total Search Hits per Surface (all keywords combined)', 'Surface', 'Total Search Hits', plots_dir / f'search_hits_per_surface.{cfg.PLOT_FORMAT}', color=_PALETTE[0])})\n")

    out.append("### Unique Results per Surface\n")
    out.append(f"![Unique results per surface]({_bar_chart_with_stats_lines(surf_labels, unique_per_surf, 'Unique Results per Surface (all keywords combined)', 'Surface', 'Unique Results', plots_dir / f'search_unique_per_surface.{cfg.PLOT_FORMAT}', color=_PALETTE[1])})\n")

    # Cross-surface keyword ranked table + bar chart
    cross = search_sum.get("keywords_cross_surface", [])
    if cross:
        top_cross = cross[:cfg.REPORT_TOP_N_KEYWORDS]
        out.append("### Keyword Hits Across All Surfaces (Ranked)\n")
        out.append("_Each row is one keyword on one surface, ranked by unique results (highest first)._\n")
        cross_rows = [
            [i + 1, _trunc(e.get("surface_label", ""), 55),
             _fmt(e.get("search_hit_count", 0)), _fmt(e.get("unique_results", 0))]
            for i, e in enumerate(top_cross)
        ]
        out.append(_table(["#", "Surface: Keyword", "Search Hits", "Unique Results"], cross_rows) + "\n")
        out.append(f"![Search keywords cross surface]({_bar_chart([_trunc(e.get('surface_label',''),45) for e in top_cross], [e.get('unique_results',0) for e in top_cross], 'Top Search Keywords by Unique Results (All Surfaces)', 'Surface: Keyword', 'Unique Results', plots_dir / f'search_keywords_cross.{cfg.PLOT_FORMAT}', horizontal=True, figsize=(10, max(5, len(top_cross)*0.3+2)))})\n")

    # Per-surface distribution line charts (total hits + unique keyword hits)
    for surface in _ALL_SURFACES:
        items = hit_dists.get(surface, [])
        if not items:
            continue
        vals   = [it["hit_count"] for it in items]
        u_vals = [it["unique_keyword_count"] for it in items]
        ranks  = list(range(1, len(items) + 1))
        out.append(f"**{surface.upper()} surface** — {len(items)} items\n")
        out.append(f"![{surface} total hit dist]({_line_chart(ranks, vals, f'{surface.upper()}: Total Keyword Hits per Item (Ranked)', 'Rank (1 = most hits)', 'Total Keyword Hits', plots_dir / f'search_dist_{surface}.{cfg.PLOT_FORMAT}', x_labels=[str(r) for r in ranks])})\n")
        out.append(f"![{surface} unique keyword dist]({_line_chart(ranks, u_vals, f'{surface.upper()}: Unique Keywords Matched per Item (Ranked)', 'Rank (1 = most unique keywords)', 'Unique Keywords Matched', plots_dir / f'search_unique_{surface}.{cfg.PLOT_FORMAT}', x_labels=[str(r) for r in ranks])})\n")
        surf_kws = search_sum.get(surface, {}).get("keywords_ranked", [])
        if surf_kws:
            out.append(f"Top keywords in {surface.upper()}:\n")
            out.append(_table(
                ["Keyword", "Search Hits", "Unique Results"],
                [[_trunc(kw.get("keyword",""),50), _fmt(kw.get("search_hit_count",0)), _fmt(kw.get("unique_results",0))]
                 for kw in surf_kws[:10]],
            ) + "\n")


def _section_technique_density(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 3. Testing Technique Density\n")
    out.append(
        "> **Data source:** Code analysis phase — repos cloned from the CODE search surface and "
        f"scanned with regexes from `inputs/{technique_name}_analysis_keywords.json`. "
        "Only repositories in `code_repos.json` contribute to this section.\n"
    )
    ca = overall.get("code_analysis", {})

    out.append(
        "**Counting rules:** Each regex match counts as +1 hit. "
        "Multiple matches on the same line each count as +1 hit, but only once toward "
        "the _hit line_ count. "
        "Keywords categorised `general_test` measure broad test presence; "
        "`specific_technique` keywords are the primary adoption metric.\n"
    )

    # Analysis keyword hits table (excluding test_file_detection)
    kws_ranked   = ca.get("keywords_ranked", [])
    kws_filtered = [k for k in kws_ranked if k.get("category") != "test_file_detection"]
    if kws_filtered:
        out.append("### Analysis Keyword Hits (Code Repos)\n")
        out.append(
            "_`specific_technique` keywords are the primary metric. "
            "`general_test` keywords measure baseline testing activity. "
            "`test_file_detection` keywords are used only for file classification and excluded here._\n"
        )
        out.append(_table(
            ["#", "Keyword", "Category", "Total Hits"],
            [[i+1, _trunc(k.get("label", k.get("id","")), 40), k.get("category",""), _fmt(k.get("count",0))]
             for i, k in enumerate(kws_filtered[:cfg.REPORT_TOP_N_KEYWORDS])],
        ) + "\n")

    # Non-code cross-surface keyword ranked table + bar chart
    nca      = overall.get("noncode_analysis", {})
    nc_cross = nca.get("keywords_cross_surface", [])
    if nc_cross:
        top_nc = nc_cross[:cfg.REPORT_TOP_N_KEYWORDS]
        out.append("### Analysis Keyword Hits — Non-Code Surfaces (Cross-Surface Ranked)\n")
        out.append(
            "_Keyword hits in non-code item bodies (issues, PRs, commits, discussions, repo descriptions), "
            "ranked highest to lowest across all non-code surfaces._\n"
        )
        out.append(_table(
            ["#", "Surface: Keyword", "Hits"],
            [[i+1, _trunc(e.get("surface_label",""),55), _fmt(e.get("count",0))]
             for i, e in enumerate(top_nc)],
        ) + "\n")
        out.append(f"![Non-code keywords cross surface]({_bar_chart([_trunc(e.get('surface_label',''),45) for e in top_nc], [e.get('count',0) for e in top_nc], 'Analysis Keyword Hits — Non-Code Surfaces (Top Ranked)', 'Surface: Keyword', 'Hits', plots_dir / f'nc_keywords_cross.{cfg.PLOT_FORMAT}', horizontal=True, figsize=(10, max(5, len(top_nc)*0.3+2)), color=_PALETTE[1])})\n")

    # Technique density 5-label scheme
    tdl = ca.get("technique_density_labels", {})
    if tdl:
        by_label    = tdl.get("by_label", {})
        label_order = ["technique_file", "technique_doc_file", "test_file", "test_doc_file", "non_test_file"]
        label_disp  = {
            "technique_file":     "Technique File (code, ≥1 specific hit)",
            "technique_doc_file": "Technique Doc File (non-code, ≥1 specific hit)",
            "test_file":          "Test File (code, ≥1 general hit, no specific)",
            "test_doc_file":      "Test Doc File (non-code, ≥1 general hit, no specific)",
            "non_test_file":      "Non-Test File (no hits)",
        }
        out.append("### Technique Density by File Label\n")
        out.append(
            "Files are assigned one of 5 mutually-exclusive labels:\n\n"
            "- **technique_file** — code extension, ≥1 `specific_technique` hit\n"
            "- **technique_doc_file** — non-code extension, ≥1 `specific_technique` hit\n"
            "- **test_file** — code extension, ≥1 `general_test` hit, no specific hits\n"
            "- **test_doc_file** — non-code extension, ≥1 `general_test` hit, no specific hits\n"
            "- **non_test_file** — no hits from either category\n"
        )
        out.append("#### File Count and Percentage per Label\n")
        pct_rows   = []
        chart_pcts = []
        chart_lbls = []
        for lbl in label_order:
            st = by_label.get(lbl, {})
            pct_rows.append([label_disp[lbl], _fmt(st.get("files",0)), _pct(st.get("pct_files",0)),
                             _fmt(st.get("lines",0)), _pct(st.get("pct_lines",0))])
            chart_lbls.append(lbl.replace("_", "\n"))
            chart_pcts.append(st.get("pct_files", 0))
        out.append(_table(["Label", "Files", "% of All Files", "Lines", "% of All Lines"], pct_rows) + "\n")
        out.append(f"![Density label %]({_bar_chart(chart_lbls, chart_pcts, '% of Files by Density Label', 'Label', '% of All Files', plots_dir / f'density_label_pct.{cfg.PLOT_FORMAT}', color=_PALETTE[2])})\n")

        out.append("#### Average Hits per File by Label\n")
        out.append(_table(
            ["Label", "Avg General Hits/File", "Avg Specific Hits/File", "Hit Line %"],
            [[label_disp[lbl],
              round(by_label.get(lbl,{}).get("gen_hits",0) / max(by_label.get(lbl,{}).get("files",1),1), 2),
              round(by_label.get(lbl,{}).get("spec_hits",0) / max(by_label.get(lbl,{}).get("files",1),1), 2),
              _pct(by_label.get(lbl,{}).get("hit_line_pct",0))]
             for lbl in label_order],
        ) + "\n")

    # Hit % per repo — exact ranked line charts
    hit_pct = ca.get("hit_pct_distribution", [])
    if hit_pct:
        ranks = list(range(1, len(hit_pct) + 1))
        out.append(f"![Hit line % per repo]({_line_chart(ranks, [r['hit_pct_lines'] for r in hit_pct], 'Hit Line % per Repo (Ranked Highest → Lowest)', 'Rank (1 = highest hit line %)', 'Hit Line %', plots_dir / f'density_hit_line_pct.{cfg.PLOT_FORMAT}')})\n")
        out.append(f"![Hit file % per repo]({_line_chart(ranks, [r['hit_pct_files'] for r in hit_pct], 'Hit File % per Repo (Ranked Highest → Lowest)', 'Rank (1 = highest hit file %)', 'Hit File %', plots_dir / f'density_hit_file_pct.{cfg.PLOT_FORMAT}')})\n")

    # Specific hits ranked
    spec_ranked = ca.get("specific_hits_ranked", [])[:cfg.REPORT_TOP_N_REPOS]
    if spec_ranked:
        out.append(f"![Top repos by specific hits]({_bar_chart([_trunc(r['name'],30) for r in spec_ranked], [r['hits'] for r in spec_ranked], f'Top {len(spec_ranked)} Repos by Specific Keyword Hits', 'Repository', 'Specific Hits', plots_dir / f'specific_hits_ranked.{cfg.PLOT_FORMAT}', horizontal=True, figsize=(9, max(4, len(spec_ranked)*0.22+2)))})\n")

    # Test code vs non-test
    tvn = ca.get("test_vs_nontest_stats", {})
    if tvn:
        tc = tvn.get("test_code", {})
        nt = tvn.get("non_test_code", {})
        out.append("### Test Code vs. Non-Test Code Summary\n")
        out.append("_Test code = files matched by `test_file_detection` keywords._\n")
        out.append(_table(
            ["Category", "Files", "% of All Files", "Lines", "% of All Lines",
             "General Hits", "Specific Hits", "Hit File %", "Hit Line %"],
            [["Test code",
              _fmt(tc.get("files",0)), _pct(tc.get("pct_of_all_files",0)),
              _fmt(tc.get("lines",0)), _pct(tc.get("pct_of_all_lines",0)),
              _fmt(tc.get("general_hits",0)), _fmt(tc.get("specific_hits",0)),
              _pct(tc.get("hit_file_pct",0)), _pct(tc.get("hit_line_pct",0))],
             ["Non-test code",
              _fmt(nt.get("files",0)), _pct(nt.get("pct_of_all_files",0)),
              _fmt(nt.get("lines",0)), _pct(nt.get("pct_of_all_lines",0)),
              _fmt(nt.get("general_hits",0)), _fmt(nt.get("specific_hits",0)),
              _pct(nt.get("hit_file_pct",0)), _pct(nt.get("hit_line_pct",0))]],
        ) + "\n")

    # Density summary stats
    out.append("### Code Repo Density Summary Statistics\n")
    stat_pairs = [
        ("Specific keyword hits per repo", ca.get("specific_hits_per_repo", {})),
        ("General keyword hits per repo",  ca.get("general_hits_per_repo", {})),
        ("Files per repo",                 ca.get("files_per_repo", {})),
        ("Hit files per repo",             ca.get("hit_files_per_repo", {})),
        ("Lines per repo",                 ca.get("lines_per_repo", {})),
        ("Hit lines per repo",             ca.get("hit_lines_per_repo", {})),
    ]
    stat_rows = [[metric] + _stat_cells(st) for metric, st in stat_pairs if st]
    if stat_rows:
        out.append(_table(
            ["Metric", "Avg", "Median", "Max", "Min", "Std Dev", "N Repos"], stat_rows
        ) + "\n")


def _section_repo_classification(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 4. Repo Classification\n")
    out.append(
        "> **Data source:** Code analysis phase — decision tree applied to each cloned repo. "
        "Classifications are non-exclusive (a repo may satisfy multiple).\n"
    )
    ca         = overall.get("code_analysis", {})
    cls_counts = ca.get("classification_counts", {})
    # Always include all four classification categories, even at 0
    order  = ["research_artifact", "framework", "actual_usage", "unclassified"]
    labels = order + [c for c in cls_counts if c not in order]
    vals   = [cls_counts.get(c, 0) for c in labels]
    total  = max(sum(vals), 1)
    out.append(_table(
        ["Classification", "Count", "% of Code Repos"],
        [[lbl, _fmt(v), _pct(v / total * 100)] for lbl, v in zip(labels, vals)],
    ) + "\n")
    out.append(f"![Repo classification]({_bar_chart(labels, vals, 'Repo Classification', 'Classification', 'Count', plots_dir / f'repo_classification.{cfg.PLOT_FORMAT}', color=_PALETTE[0])})\n")


def _section_artifact_classification(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 5. Artifact Classification\n")
    out.append(
        "> **Data source:** Code analysis phase — all scanned files classified by file extension "
        "(not keyword hits). Extensions are grouped into: code / docs / config / other.\n"
    )
    ca  = overall.get("code_analysis", {})
    art = ca.get("artifact_classification", {})
    if not art:
        out.append("_No artifact classification data available._\n")
        return

    by_cat      = art.get("by_category", {})
    by_cat_pct  = art.get("by_category_pct", {})
    by_ext      = art.get("by_extension", {})
    total_files = art.get("total_files", 1)

    out.append("### File Type Breakdown\n")
    cat_rows = [[c.capitalize(), _fmt(by_cat.get(c,0)), _pct(by_cat_pct.get(c,0))]
                for c in ["code", "docs", "config", "other"]]
    out.append(_table(["Type", "Files", "% of All Files"], cat_rows) + "\n")
    out.append(f"![Artifact type distribution]({_bar_chart([c.capitalize() for c in ['code','docs','config','other']], [by_cat.get(c,0) for c in ['code','docs','config','other']], 'File Type Distribution', 'File Type', 'File Count', plots_dir / f'artifact_type.{cfg.PLOT_FORMAT}', color=_PALETTE[3])})\n")

    if by_ext:
        sorted_exts = sorted(by_ext.items(), key=lambda x: x[1], reverse=True)
        out.append("### File Extensions (All Detected, Ranked)\n")
        out.append(_table(
            ["Extension", "File Count", "% of All Files"],
            [[ext or "(none)", _fmt(cnt), _pct(cnt / max(total_files,1) * 100)]
             for ext, cnt in sorted_exts[:50]],
        ) + "\n")
        top_ext = sorted_exts[:20]
        out.append(f"![Top file extensions]({_bar_chart([e[0] or '(none)' for e in top_ext], [e[1] for e in top_ext], 'Top 20 File Extensions', 'Extension', 'File Count', plots_dir / f'artifact_extensions.{cfg.PLOT_FORMAT}', color=_PALETTE[4])})\n")


def _section_language(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 6. Language Distribution\n")
    out.append(
        "> **Data source:** Code analysis phase — primary language of each cloned repo "
        "plus per-file language detection from the scan.\n"
    )
    lang_code = overall.get("code_analysis", {}).get("language_distribution", {})
    if not lang_code:
        return
    top = list(lang_code.items())[:20]
    out.append(f"![Language distribution (code)]({_bar_chart([t[0] for t in top], [t[1] for t in top], 'Language Distribution (Code Repos)', 'Language', 'Repos', plots_dir / f'language_distribution.{cfg.PLOT_FORMAT}', color=_PALETTE[0], horizontal=True, figsize=(8, max(4, len(top)*0.3+2)))})\n")
    out.append(_table(["Language", "Repos"], [[lang, _fmt(cnt)] for lang, cnt in top]) + "\n")


def _section_domain(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 7. Application Domain\n")
    out.append(
        "> **Data source:** Code analysis and non-code analysis phases — domain keywords "
        "matched against repo name, description, and topics; word cloud from "
        "non-code surface body text.\n"
    )
    nca = overall.get("noncode_analysis", {})
    wf  = nca.get("top_word_freq", {})
    dc  = nca.get("domain_counts", {})

    if dc:
        top_dc = list(dc.items())[:15]
        out.append(f"![Domain distribution]({_bar_chart([t[0] for t in top_dc], [t[1] for t in top_dc], 'Application Domain Distribution', 'Domain', 'Repo Count', plots_dir / f'domain_distribution.{cfg.PLOT_FORMAT}', color=_PALETTE[2])})\n")
        out.append(_table(["Domain", "Repos"], [[d, _fmt(c)] for d, c in top_dc]) + "\n")

    if wf:
        wc_path = plots_dir / f"wordcloud.{cfg.PLOT_FORMAT}"
        try:
            from wordcloud import WordCloud
            wc = WordCloud(width=900, height=450, background_color="white",
                           max_words=150, colormap="tab10").generate_from_frequencies(wf)
            fig, ax = plt.subplots(figsize=(9, 4.5))
            ax.imshow(wc, interpolation="bilinear")
            ax.axis("off")
            ax.set_title("Word Cloud — Non-Code Body Text")
            out.append(f"![Word cloud]({_save(fig, wc_path)})\n")
        except ImportError:
            # wordcloud not installed — fall back to bar chart
            top_wf = list(wf.items())[:30]
            out.append(f"![Word frequency]({_bar_chart([t[0] for t in top_wf], [t[1] for t in top_wf], 'Top Word Frequencies (Non-Code Bodies)', 'Word', 'Frequency', wc_path, horizontal=True, figsize=(9, max(5, len(top_wf)*0.3+2)), color=_PALETTE[1])})\n")


def _section_timeline(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 8. Timeline\n")
    out.append(
        "> **Data source:** Code analysis phase — git commit history mined via PyDriller "
        "(or `git log` fallback). Creation dates from GitHub API metadata.\n"
    )
    ca = overall.get("code_analysis", {})
    tl = ca.get("timeline", {})
    if not tl:
        out.append("_No timeline data available._\n")
        return

    cy = tl.get("creation_years", {})
    if cy:
        out.append(f"![Creation years]({_bar_chart([str(y) for y in sorted(cy)], [cy[y] for y in sorted(cy)], 'Repos by Creation Year', 'Year', 'Repos Created', plots_dir / f'creation_years.{cfg.PLOT_FORMAT}', color=_PALETTE[0])})\n")

    css = tl.get("commit_span_stats", {})
    if css:
        out.append("#### Commit Span Statistics\n")
        out.append(_table(
            ["Metric", "Avg", "Median", "Max (days)", "Min (days)", "Std Dev", "N Repos"],
            [["Commit span (days)"] + _stat_cells(css)],
        ) + "\n")

    cs_sorted = ca.get("commit_spans_sorted", [])
    if cs_sorted:
        ranks = list(range(1, len(cs_sorted) + 1))
        out.append(f"![Commit span distribution]({_line_chart(ranks, [r['span_days'] for r in cs_sorted], 'Commit Span per Repo (Ranked Longest → Shortest)', 'Rank (1 = longest span)', 'Span (days)', plots_dir / f'commit_span_distribution.{cfg.PLOT_FORMAT}')})\n")

    cbm  = tl.get("commits_by_month", {})
    tcbm = tl.get("technique_commits_by_month", {})

    if cbm:
        months = sorted(cbm.keys())
        out.append(f"![Commits by month]({_line_chart(list(range(len(months))), [cbm[m] for m in months], 'Monthly Commit Activity (All Repos)', 'Month', 'Commits', plots_dir / f'commits_by_month.{cfg.PLOT_FORMAT}', x_labels=months)})\n")

    if tcbm:
        months = sorted(tcbm.keys())
        out.append(f"![Technique commits by month]({_line_chart(list(range(len(months))), [tcbm[m] for m in months], 'Monthly Technique-Keyword Commits', 'Month', 'Technique Commits', plots_dir / f'technique_commits_by_month.{cfg.PLOT_FORMAT}', x_labels=months)})\n")

    # Proportion chart — technique commits vs total commits over time
    if cbm and tcbm:
        all_months = sorted(set(cbm.keys()) | set(tcbm.keys()))
        total_vals = [cbm.get(m, 0) for m in all_months]
        tech_vals  = [tcbm.get(m, 0) for m in all_months]
        xs         = list(range(len(all_months)))

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(xs, total_vals, color=_PALETTE[0], linewidth=1.2, label="All commits")
        ax.plot(xs, tech_vals,  color=_PALETTE[1], linewidth=1.2, label="Technique commits", linestyle="--")
        ax.fill_between(xs, tech_vals, alpha=0.25, color=_PALETTE[1])
        step = max(1, len(all_months) // 20)
        ax.set_xticks(xs[::step])
        ax.set_xticklabels(all_months[::step], rotation=35, ha="right", fontsize=6)
        ax.set_xlabel("Month")
        ax.set_ylabel("Commits")
        ax.set_title("Total vs Technique Commits per Month")
        ax.legend(fontsize=8)
        out.append(f"![Total vs technique commits]({_save(fig, plots_dir / f'commits_proportion.{cfg.PLOT_FORMAT}')})\n")


def _section_all_repos(overall: dict, dirs: dict, out: list[str]) -> None:
    out.append("## 9. All Cloned Repositories\n")
    code_repos = load_json(dirs["analysis"] / "code_repos.json", [])
    if not code_repos:
        out.append("_No code repos data available._\n")
        return
    out.append(f"_{len(code_repos)} repositories were cloned and analysed._\n")
    sorted_repos = sorted(code_repos,
                          key=lambda r: r.get("scan", {}).get("total_specific_hits", 0), reverse=True)
    repo_rows = []
    for rank, r in enumerate(sorted_repos, 1):
        scan    = r.get("scan", {})
        n_lines = scan.get("total_lines", 0)
        hl      = scan.get("total_hit_lines", 0)
        cls_list = r.get("classification", {}).get("classifications", ["—"])
        repo_rows.append([
            rank,
            _trunc(r.get("full_name", ""), 38),
            _fmt(r.get("stars", 0)),
            r.get("language", "—"),
            _fmt(scan.get("total_files", 0)),
            _fmt(scan.get("total_specific_hits", 0)),
            _pct(round(hl / max(n_lines, 1) * 100, 1)),
            _fmt(r.get("commits", {}).get("commit_span_days")),
            ", ".join(cls_list),
        ])
    out.append(_table(
        ["#", "Repository", "Stars", "Language", "Files", "Specific Hits",
         "Hit Line %", "Span (days)", "Classification"],
        repo_rows,
    ) + "\n")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(slug: str) -> None:
    ensure_dirs(slug)
    dirs = technique_dirs(slug)

    overall = load_json(dirs["analysis"] / "overall.json", {})
    if not overall:
        print("overall.json not found — run analysis phase first.")
        return

    tech_name   = cfg.TECHNIQUE_INPUT_PREFIXES.get(slug, slug)
    full_name   = cfg.TECHNIQUE_DISPLAY_NAMES.get(slug, slug)
    plots_dir   = dirs["plots"]
    report_path = dirs["report"] / "report.md"

    out: list[str] = []
    out.append(f"# {full_name} — GitHub Mining Report\n")
    out.append(
        f"_Generated from `results/{slug}/analysis/overall.json`. "
        "All statistics are sourced from the aggregation step; the report performs no calculations._\n"
    )

    _section_projects_and_sizes(overall, plots_dir, tech_name, out)
    _section_search_distribution(overall, plots_dir, tech_name, out)
    _section_technique_density(overall, plots_dir, tech_name, out)
    _section_repo_classification(overall, plots_dir, tech_name, out)
    _section_artifact_classification(overall, plots_dir, tech_name, out)
    _section_language(overall, plots_dir, tech_name, out)
    _section_domain(overall, plots_dir, tech_name, out)
    _section_timeline(overall, plots_dir, tech_name, out)
    _section_all_repos(overall, dirs, out)

    report_path.write_text("\n".join(out), encoding="utf-8")
    print(f"Report written to {report_path}")
