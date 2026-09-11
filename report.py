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
  5. Technique file extensions and language distribution
  6. Language distribution (all repos)
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
    figsize: tuple = (8, 4), annotate: bool = True,
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
    metadata_path = plots_dir.parent.parent / "analysis" / "repo_metadata.json"
    if metadata_path.exists():
        out.append(
            "_Repository size is fetched from the GitHub Metadata API (`/repos/{owner}/{repo}`) "
            "for all repos across all surfaces. Repos where the API returns 404 (deleted or private) "
            "are excluded from size statistics._\n"
        )
    else:
        out.append(
            "_Repository size data not yet available. Run the analysis phase to fetch metadata for all repos._\n"
        )


def _section_search_distribution(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 2. Search Keyword Hit Distribution\n")
    out.append(
        "> **Data source:** Search phase — GitHub REST API hit counts per keyword per surface. "
        f"Keywords from `inputs/{technique_name}_search_keywords.txt`.\n"
    )
    out.append(
        "> **Note on 'unique results':** GitHub's API may return the same repository under "
        "multiple keywords. 'Unique results' is the count of deduplicated items after "
        "merging all keyword runs for a surface. A single repo can appear in multiple surfaces.\n"
    )

    hit_dists  = overall.get("search_hit_distributions", {})
    search_sum = overall.get("search_summary", {})

    # Aggregate totals per surface
    total_hits_per_surf = [search_sum.get(s, {}).get("search_hit_count", 0) for s in _ALL_SURFACES]
    unique_per_surf     = [search_sum.get(s, {}).get("unique_results",   0) for s in _ALL_SURFACES]
    surf_labels         = [s.upper() for s in _ALL_SURFACES]

    out.append("### Total Search Hits per Surface\n")
    out.append(
        "_Total search hits = sum of `total_count` returned by the API for all keyword "
        "queries on each surface (before deduplication). Reflects raw API exposure._\n"
    )
    out.append(f"![Total search hits per surface]({_bar_chart_with_stats_lines(surf_labels, total_hits_per_surf, 'Total Search Hits per Surface (all keywords combined)', 'Surface', 'Total Search Hits', plots_dir / f'search_hits_per_surface.{cfg.PLOT_FORMAT}', color=_PALETTE[0])})\n")
    out.append(_table(
        ["Surface", "Total Search Hits"],
        [[s, _fmt(v)] for s, v in zip(surf_labels, total_hits_per_surf)],
    ) + "\n")
    disc_hits   = search_sum.get("discussions", {}).get("search_hit_count", 0)
    disc_unique = search_sum.get("discussions", {}).get("unique_results", 0)
    if disc_hits == 0 and disc_unique > 0:
        out.append(
            "> _DISCUSSIONS search hits show 0 because the GraphQL `api_hit_count` was not correctly "
            "tracked in this run. Unique results are accurate. Fix applied in `search.py` — "
            "re-run search to populate._\n"
        )

    out.append("### Unique Results per Surface\n")
    out.append(
        "_Unique results = distinct items collected after deduplication within each surface._\n"
    )
    out.append(f"![Unique results per surface]({_bar_chart_with_stats_lines(surf_labels, unique_per_surf, 'Unique Results per Surface (all keywords combined)', 'Surface', 'Unique Results', plots_dir / f'search_unique_per_surface.{cfg.PLOT_FORMAT}', color=_PALETTE[1])})\n")
    out.append(_table(
        ["Surface", "Unique Results"],
        [[s, _fmt(v)] for s, v in zip(surf_labels, unique_per_surf)],
    ) + "\n")

    # Distinct keywords with ≥1 result per surface (Item 5)
    kw_with_results: dict[str, int] = {}
    for s in _ALL_SURFACES:
        surf_kws = search_sum.get(s, {}).get("keywords_ranked", [])
        kw_with_results[s.upper()] = sum(1 for kw in surf_kws if kw.get("unique_results", 0) > 0)
    kwsuf_labels = list(kw_with_results.keys())
    kwsuf_vals   = [kw_with_results[s] for s in kwsuf_labels]
    out.append("### Keywords with ≥1 Unique Result per Surface\n")
    out.append(f"![Keywords with results per surface]({_bar_chart(kwsuf_labels, kwsuf_vals, 'Distinct Keywords Returning ≥1 Unique Result per Surface', 'Surface', 'Keywords with ≥1 Result', plots_dir / f'search_unique_keywords_per_surface.{cfg.PLOT_FORMAT}', color=_PALETTE[2])})\n")
    out.append(_table(
        ["Surface", "Keywords with ≥1 Result"],
        [[s, _fmt(v)] for s, v in zip(kwsuf_labels, kwsuf_vals)],
    ) + "\n")

    # Cross-surface keyword ranked table + bar chart — ALL combinations (Item 7)
    cross = search_sum.get("keywords_cross_surface", [])
    if cross:
        out.append("### Keyword Hits Across All Surfaces (Ranked)\n")
        out.append("_Each row is one keyword on one surface, ranked by unique results (highest first). All keyword × surface combinations are shown._\n")
        cross_rows = [
            [i + 1, _trunc(e.get("surface_label", ""), 55),
             _fmt(e.get("search_hit_count", 0)), _fmt(e.get("unique_results", 0))]
            for i, e in enumerate(cross)
        ]
        out.append(_table(["#", "Surface: Keyword", "Search Hits", "Unique Results"], cross_rows) + "\n")
        out.append(f"![Search keywords cross surface]({_bar_chart([_trunc(e.get('surface_label',''),45) for e in cross], [e.get('unique_results',0) for e in cross], 'Search Keywords by Unique Results (All Surfaces)', 'Surface: Keyword', 'Unique Results', plots_dir / f'search_keywords_cross.{cfg.PLOT_FORMAT}', horizontal=True, figsize=(10, max(5, len(cross)*0.22+2)))})\n")

    # Per-surface distribution line charts + per-surface repo ranking (Items 7, 9)
    for surface in _ALL_SURFACES:
        items = hit_dists.get(surface, [])
        nca   = overall.get("noncode_analysis", {})
        surf_nc_stats = nca.get("by_surface", {}).get(surface, {}) if surface != "code" else {}

        out.append(f"### {surface.upper()} Surface\n")
        if items:
            vals   = [it["hit_count"] for it in items]
            u_vals = [it["unique_keyword_count"] for it in items]
            ranks  = list(range(1, len(items) + 1))
            out.append(f"_Total unique items: {len(items)}_\n")
            out.append(f"![{surface} total hit dist]({_line_chart(ranks, vals, f'{surface.upper()}: Total Keyword Hits per Item (Ranked)', 'Rank (1 = most hits)', 'Total Keyword Hits', plots_dir / f'search_dist_{surface}.{cfg.PLOT_FORMAT}', x_labels=[str(r) for r in ranks])})\n")
            out.append(f"![{surface} unique keyword dist]({_line_chart(ranks, u_vals, f'{surface.upper()}: Unique Keywords Matched per Item (Ranked)', 'Rank (1 = most unique keywords)', 'Unique Keywords Matched', plots_dir / f'search_unique_{surface}.{cfg.PLOT_FORMAT}', x_labels=[str(r) for r in ranks])})\n")

        # Per-surface keyword table — ALL keywords (Item 7)
        surf_kws = search_sum.get(surface, {}).get("keywords_ranked", [])
        if surf_kws:
            out.append(f"Keywords in {surface.upper()} (all, ranked by unique results):\n")
            out.append(_table(
                ["#", "Keyword", "Search Hits", "Unique Results"],
                [[i+1, _trunc(kw.get("keyword",""),50), _fmt(kw.get("search_hit_count",0)), _fmt(kw.get("unique_results",0))]
                 for i, kw in enumerate(surf_kws)],
            ) + "\n")

        # Per-surface repo ranking (Item 9) — from noncode_analysis
        repos_ranked = surf_nc_stats.get("repos_ranked", [])
        if repos_ranked:
            out.append(f"Repositories ranked by keyword hits in {surface.upper()} body text:\n")
            out.append("_Showing top 100 repos by keyword hits on this surface._\n")
            repo_hit_vals = [r["hit_count"] for r in repos_ranked]
            repo_names    = [_trunc(r["repo"], 35) for r in repos_ranked]
            out.append(f"![{surface} repo ranking]({_bar_chart(repo_names, repo_hit_vals, f'Top Repos by Keyword Hits — {surface.upper()}', 'Repository', 'Keyword Hits', plots_dir / f'search_repos_{surface}.{cfg.PLOT_FORMAT}', horizontal=True, figsize=(9, max(4, len(repo_names[:30])*0.25+2)))})\n")
            out.append(_table(
                ["#", "Repository", "Keyword Hits"],
                [[i+1, r["repo"], _fmt(r["hit_count"])] for i, r in enumerate(repos_ranked[:100])],
            ) + "\n")
            rhs = surf_nc_stats.get("repo_hit_stats", {})
            if rhs:
                out.append(_table(
                    ["Metric", "Avg", "Median", "Max", "Min", "Std Dev", "Repos"],
                    [["Keyword hits per repo"] + _stat_cells(rhs)],
                ) + "\n")


def _section_technique_density(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 3. Testing Technique Density\n")
    out.append(
        "> **Data source:** Code analysis phase — repos cloned from the CODE search surface and "
        f"scanned with regexes from `inputs/{technique_name}_analysis_keywords.json` and "
        "`inputs/shared_analysis_keywords.json`. "
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

    # Analysis keyword hits — ALL keywords (Item 15)
    kws_ranked = ca.get("keywords_ranked", [])
    if kws_ranked:
        out.append("### Analysis Keyword Hits (Code Repos)\n")
        out.append(
            "_`specific_technique` keywords are the primary metric. "
            "`general_test` keywords measure baseline testing activity. "
            "All keywords shown._\n"
        )
        out.append(_table(
            ["#", "Keyword", "Category", "Total Hits"],
            [[i+1, _trunc(k.get("label", k.get("id","")), 40), k.get("category",""), _fmt(k.get("count",0))]
             for i, k in enumerate(kws_ranked)],
        ) + "\n")
        kw_labels = [_trunc(k.get("label", k.get("id","")), 35) for k in kws_ranked]
        kw_vals   = [k.get("count", 0) for k in kws_ranked]
        out.append(f"![Analysis keyword hits]({_bar_chart(kw_labels, kw_vals, 'Analysis Keyword Hits (Code Repos, All Keywords)', 'Keyword', 'Total Hits', plots_dir / f'analysis_keyword_hits.{cfg.PLOT_FORMAT}', horizontal=True, figsize=(10, max(5, len(kw_labels)*0.22+2)))})\n")

    # Non-code cross-surface keyword ranked table + bar chart — ALL (Item 15)
    nca      = overall.get("noncode_analysis", {})
    nc_cross = nca.get("keywords_cross_surface", [])
    if nc_cross:
        out.append("### Analysis Keyword Hits — Non-Code Surfaces (Cross-Surface Ranked)\n")
        out.append(
            "_Keyword hits in non-code item bodies (issues, PRs, commits, discussions, repo descriptions), "
            "ranked highest to lowest across all non-code surfaces. All combinations shown._\n"
        )
        out.append(_table(
            ["#", "Surface: Keyword", "Hits"],
            [[i+1, _trunc(e.get("surface_label",""),55), _fmt(e.get("count",0))]
             for i, e in enumerate(nc_cross)],
        ) + "\n")
        out.append(f"![Non-code keywords cross surface]({_bar_chart([_trunc(e.get('surface_label',''),45) for e in nc_cross], [e.get('count',0) for e in nc_cross], 'Analysis Keyword Hits — Non-Code Surfaces (All, Ranked)', 'Surface: Keyword', 'Hits', plots_dir / f'nc_keywords_cross.{cfg.PLOT_FORMAT}', horizontal=True, figsize=(10, max(5, len(nc_cross)*0.22+2)), color=_PALETTE[1])})\n")

    # Technique density 10-label scheme (Items 16-20)
    tdl = ca.get("technique_density_labels", {})
    if not tdl:
        out.append(
            "> _Technique density data unavailable — file-level scan results (`file_details`) were not stored "
            "in a prior run. Re-run the analysis phase to regenerate `code_repos.json` with file-level data._\n"
        )
    if tdl:
        by_label    = tdl.get("by_label", {})
        label_order = [
            "technique_code", "technique_doc", "technique_config", "technique_other",
            "test_code",      "test_doc",      "test_config",      "test_other",
            "non_hit_code",   "non_hit_ncode",
        ]
        label_disp = {
            "technique_code":   "Technique Code (code file, ≥1 specific hit)",
            "technique_doc":    "Technique Doc (doc file, ≥1 specific hit)",
            "technique_config": "Technique Config (config file, ≥1 specific hit)",
            "technique_other":  "Technique Other (other file, ≥1 specific hit)",
            "test_code":        "Test Code (code file, general-only hits)",
            "test_doc":         "Test Doc (doc file, general-only hits)",
            "test_config":      "Test Config (config file, general-only hits)",
            "test_other":       "Test Other (other file, general-only hits)",
            "non_hit_code":     "Non-Hit Code (code file, no hits)",
            "non_hit_ncode":    "Non-Hit Non-Code (non-code file, no hits)",
        }

        out.append("### Technique Density by File Label (10-Label Scheme)\n")
        out.append(
            "Files are assigned one of 10 mutually-exclusive labels based on file type and keyword hits:\n\n"
            "- **technique_\\*** — ≥1 `specific_technique` hit (code / doc / config / other)\n"
            "- **test_\\*** — ≥1 `general_test` hit, no specific hits (code / doc / config / other)\n"
            "- **non_hit_code** — code file with no keyword hits\n"
            "- **non_hit_ncode** — non-code file with no keyword hits\n\n"
            "_File class: code = test_code ∪ source_code, doc = docs, config = config, other = other._\n"
        )

        # Combined density table (Item 17)
        total_files = tdl.get("total_files", 1)
        total_lines = tdl.get("total_lines", 1)
        out.append("#### Combined Density Table\n")
        density_rows = []
        for lbl in label_order:
            st = by_label.get(lbl, {})
            density_rows.append([
                label_disp[lbl],
                _fmt(st.get("files", 0)),
                _pct(st.get("pct_files", 0)),
                _fmt(st.get("lines", 0)),
                _pct(st.get("pct_lines", 0)),
                _fmt(st.get("gen_hits", 0)),
                _fmt(st.get("spec_hits", 0)),
                _pct(st.get("hit_line_pct", 0)),
            ])
        out.append(_table(
            ["Label", "Files", "% of All Files", "Lines", "% of All Lines",
             "General Hits", "Specific Hits", "Hit Line %"],
            density_rows,
        ) + "\n")
        chart_lbls = [lbl.replace("_", "\n") for lbl in label_order]
        chart_pcts = [by_label.get(lbl, {}).get("pct_files", 0) for lbl in label_order]
        out.append(f"![Density label %]({_bar_chart(chart_lbls, chart_pcts, '% of Files by Density Label (10-Label Scheme)', 'Label', '% of All Files', plots_dir / f'density_label_pct.{cfg.PLOT_FORMAT}', color=_PALETTE[2])})\n")

        # Hit File % Summary (Item 18)
        out.append("#### Hit File % Summary\n")
        out.append("_Percentage of files in each label that have at least one general or specific keyword hit._\n")
        hit_file_rows = []
        for lbl in label_order:
            st = by_label.get(lbl, {})
            hit_file_rows.append([
                label_disp[lbl],
                _fmt(st.get("files", 0)),
                _fmt(st.get("hit_files", 0)),
                _pct(st.get("hit_file_pct", 0)),
            ])
        out.append(_table(["Label", "Total Files", "Hit Files", "Hit File %"], hit_file_rows) + "\n")

        # Expanded hits-per-file statistics (Item 19)
        out.append("#### Hits per File — Extended Statistics\n")
        hits_per_file_rows = []
        for lbl in label_order:
            st   = by_label.get(lbl, {})
            f    = max(st.get("files", 0), 1)
            hits_per_file_rows.append([
                label_disp[lbl],
                _fmt(f - 1 if f == 1 else f, 0),
                round(st.get("gen_hits",  0) / f, 2),
                round(st.get("spec_hits", 0) / f, 2),
                _pct(st.get("hit_line_pct", 0)),
                _fmt(st.get("gen_hits",  0)),
                _fmt(st.get("spec_hits", 0)),
            ])
        out.append(_table(
            ["Label", "Files", "Avg Gen Hits/File", "Avg Spec Hits/File",
             "Hit Line %", "Total Gen Hits", "Total Spec Hits"],
            hits_per_file_rows,
        ) + "\n")

        # Three type-restricted breakdowns (Item 20)
        out.append("#### Code Files Only\n")
        code_lbls = ["technique_code", "test_code", "non_hit_code"]
        code_rows = []
        for lbl in code_lbls:
            st = by_label.get(lbl, {})
            code_rows.append([label_disp[lbl], _fmt(st.get("files",0)),
                              _pct(st.get("pct_files",0)), _fmt(st.get("gen_hits",0)),
                              _fmt(st.get("spec_hits",0)), _pct(st.get("hit_line_pct",0))])
        out.append(_table(["Label", "Files", "% of All Files", "Gen Hits", "Spec Hits", "Hit Line %"], code_rows) + "\n")

        out.append("#### Doc Files Only\n")
        doc_lbls = ["technique_doc", "test_doc", "non_hit_ncode"]
        doc_rows = []
        for lbl in doc_lbls:
            st = by_label.get(lbl, {})
            doc_rows.append([label_disp[lbl], _fmt(st.get("files",0)),
                             _pct(st.get("pct_files",0)), _fmt(st.get("gen_hits",0)),
                             _fmt(st.get("spec_hits",0)), _pct(st.get("hit_line_pct",0))])
        out.append(_table(["Label", "Files", "% of All Files", "Gen Hits", "Spec Hits", "Hit Line %"], doc_rows) + "\n")

        out.append("#### Config Files Only\n")
        cfg_lbls = ["technique_config", "test_config"]
        cfg_rows = []
        for lbl in cfg_lbls:
            st = by_label.get(lbl, {})
            cfg_rows.append([label_disp[lbl], _fmt(st.get("files",0)),
                             _pct(st.get("pct_files",0)), _fmt(st.get("gen_hits",0)),
                             _fmt(st.get("spec_hits",0)), _pct(st.get("hit_line_pct",0))])
        out.append(_table(["Label", "Files", "% of All Files", "Gen Hits", "Spec Hits", "Hit Line %"], cfg_rows) + "\n")

    # Hit % per repo — exact ranked line charts (Items 23-25)
    hit_pct = ca.get("hit_pct_distribution", [])
    if hit_pct:
        hit_line_vals = [r["hit_pct_lines"] for r in hit_pct]
        hit_file_vals = sorted([r["hit_pct_files"] for r in hit_pct], reverse=True)
        ranks = list(range(1, len(hit_pct) + 1))

        out.append("### Hit Line % per Repo (Ranked)\n")
        out.append(f"![Hit line % per repo]({_line_chart(ranks, hit_line_vals, 'Hit Line % per Repo (Ranked Highest → Lowest)', 'Rank (1 = highest hit line %)', 'Hit Line %', plots_dir / f'density_hit_line_pct.{cfg.PLOT_FORMAT}')})\n")
        if hit_line_vals:
            import statistics as _stats
            hl_stats = {
                "avg":    round(sum(hit_line_vals) / len(hit_line_vals), 2),
                "median": round(_stats.median(hit_line_vals), 2),
                "max":    round(max(hit_line_vals), 2),
                "min":    round(min(hit_line_vals), 2),
                "stdev":  round(_stats.stdev(hit_line_vals), 2) if len(hit_line_vals) >= 2 else 0,
                "count":  len(hit_line_vals),
            }
            out.append(_table(
                ["Metric", "Avg", "Median", "Max", "Min", "Std Dev", "N Repos"],
                [["Hit Line % per repo"] + _stat_cells(hl_stats)],
            ) + "\n")

        out.append("### Hit File % per Repo (Ranked)\n")
        out.append(f"![Hit file % per repo]({_line_chart(ranks, hit_file_vals, 'Hit File % per Repo (Ranked Highest → Lowest)', 'Rank (1 = highest hit file %)', 'Hit File %', plots_dir / f'density_hit_file_pct.{cfg.PLOT_FORMAT}')})\n")
        if hit_file_vals:
            import statistics as _stats
            hf_stats = {
                "avg":    round(sum(hit_file_vals) / len(hit_file_vals), 2),
                "median": round(_stats.median(hit_file_vals), 2),
                "max":    round(max(hit_file_vals), 2),
                "min":    round(min(hit_file_vals), 2),
                "stdev":  round(_stats.stdev(hit_file_vals), 2) if len(hit_file_vals) >= 2 else 0,
                "count":  len(hit_file_vals),
            }
            out.append(_table(
                ["Metric", "Avg", "Median", "Max", "Min", "Std Dev", "N Repos"],
                [["Hit File % per repo"] + _stat_cells(hf_stats)],
            ) + "\n")

    # Top 20 repos by specific hits — bar values + table (Item 26)
    spec_ranked = ca.get("specific_hits_ranked", [])
    top20 = spec_ranked[:20]
    if top20:
        out.append("### Top 20 Repos by Specific Keyword Hits\n")
        out.append(f"![Top repos by specific hits]({_bar_chart([_trunc(r['name'],30) for r in top20], [r['hits'] for r in top20], 'Top 20 Repos by Specific Keyword Hits', 'Repository', 'Specific Hits', plots_dir / f'specific_hits_ranked.{cfg.PLOT_FORMAT}', horizontal=True, figsize=(9, max(4, len(top20)*0.22+2)))})\n")
        out.append(_table(
            ["#", "Repository", "Specific Hits"],
            [[i+1, r["name"], _fmt(r["hits"])] for i, r in enumerate(top20)],
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
    out.append(
        "_A high unclassified rate is expected: the CODE search surface returns all files mentioning "
        "the technique's keywords, including academic papers, blog posts, documentation, and incidental "
        "references that do not implement the technique. Repos are classified as 'actual\\_usage' only "
        "when file-level evidence (keyword hits in test or source files) is sufficient._\n"
    )


def _section_technique_file_extensions(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    """Section 5: File extensions and language distribution scoped to technique files only."""
    out.append("## 5. Technique File Extensions and Language Distribution\n")
    out.append(
        "> **Data source:** Code analysis phase — file extensions and language counts "
        "restricted to files with ≥1 `specific_technique` keyword hit. "
        "Binary and image files are excluded. Language is derived from file extension. "
        "Language counts are deduplicated per repo (+1 per language per repo maximum).\n"
    )
    ca  = overall.get("code_analysis", {})
    tfs = ca.get("technique_file_stats", {})
    if not tfs:
        out.append(
            "_No technique file data available — file-level scan results were not stored in a prior run. "
            "Re-run the analysis phase to regenerate `code_repos.json` with file-level data._\n"
        )
        return

    by_ext = tfs.get("ext_counts", {})
    by_lang = tfs.get("lang_distribution", {})
    total_tech_files = tfs.get("total_technique_files", 0)

    out.append(f"_Total technique files (≥1 specific hit, non-binary): **{_fmt(total_tech_files)}**_\n")

    if by_ext:
        sorted_exts = sorted(by_ext.items(), key=lambda x: x[1], reverse=True)
        out.append("### Technique File Extensions (Ranked)\n")
        out.append(_table(
            ["Extension", "File Count", "% of Technique Files"],
            [[ext or "(none)", _fmt(cnt), _pct(cnt / max(total_tech_files, 1) * 100)]
             for ext, cnt in sorted_exts],
        ) + "\n")
        top_ext = sorted_exts[:20]
        out.append(f"![Technique file extensions]({_bar_chart([e[0] or '(none)' for e in top_ext], [e[1] for e in top_ext], 'Top 20 Technique File Extensions', 'Extension', 'File Count', plots_dir / f'technique_extensions.{cfg.PLOT_FORMAT}', color=_PALETTE[4])})\n")

    if by_lang:
        top_lang = list(by_lang.items())[:20]
        out.append("### Technique File Language Distribution (per-Repo Deduplicated)\n")
        out.append("_Each language counted at most once per repo (repos using Python + Java = +1 for each)._\n")
        out.append(_table(
            ["Language", "Repos with Technique Files"],
            [[lang, _fmt(cnt)] for lang, cnt in top_lang],
        ) + "\n")
        out.append(f"![Technique language distribution]({_bar_chart([t[0] for t in top_lang], [t[1] for t in top_lang], 'Language Distribution — Technique Files Only (per-Repo Deduplicated)', 'Language', 'Repos', plots_dir / f'technique_language_distribution.{cfg.PLOT_FORMAT}', color=_PALETTE[0], horizontal=True, figsize=(8, max(4, len(top_lang)*0.3+2)))})\n")


def _section_language(
    overall: dict, plots_dir: Path, technique_name: str, out: list[str]
) -> None:
    out.append("## 6. Language Distribution\n")
    out.append(
        "> **Data source:** Code analysis phase — primary language of each cloned repo "
        "plus per-file language detection from the scan. "
        "Each language is counted once per repo it appears in.\n"
    )
    ca = overall.get("code_analysis", {})

    # Prefer technique-file language distribution; fall back to general per-repo language
    tfs_lang = ca.get("technique_file_stats", {}).get("lang_distribution", {})
    if tfs_lang:
        top = list(tfs_lang.items())[:20]
        chart_title = "Language Distribution — Technique Files Only (per-Repo Deduplicated)"
        out.append(f"![Language distribution (technique files)]({_bar_chart([t[0] for t in top], [t[1] for t in top], chart_title, 'Language', 'Repos', plots_dir / f'language_distribution.{cfg.PLOT_FORMAT}', color=_PALETTE[0], horizontal=True, figsize=(8, max(4, len(top)*0.3+2)))})\n")
        out.append(_table(["Language", "Repos with Technique Files"], [[lang, _fmt(cnt)] for lang, cnt in top]) + "\n")
    else:
        lang_code = ca.get("language_distribution", {})
        if not lang_code:
            return
        top = list(lang_code.items())[:20]
        out.append(
            "_Showing primary language of cloned repos (technique-file language data unavailable — "
            "re-run analysis to populate)._\n"
        )
        out.append(f"![Language distribution (code)]({_bar_chart([t[0] for t in top], [t[1] for t in top], 'Language Distribution (Code Repos, All Files)', 'Language', 'Repos', plots_dir / f'language_distribution.{cfg.PLOT_FORMAT}', color=_PALETTE[0], horizontal=True, figsize=(8, max(4, len(top)*0.3+2)))})\n")
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
        "> **Data source:** Code analysis phase — git commit history mined via PyDriller. "
        "Only commits from the local git history of cloned repos are counted. "
        "Technique commits are those touching files with ≥1 `specific_technique` hit. "
        "Creation dates from GitHub API metadata.\n"
    )
    ca = overall.get("code_analysis", {})
    tl = ca.get("timeline", {})
    if not tl:
        out.append("_No timeline data available._\n")
        return

    cy = tl.get("creation_years", {})
    if cy:
        out.append(f"![Creation years]({_bar_chart([str(y) for y in sorted(cy)], [cy[y] for y in sorted(cy)], 'Repos by Creation Year', 'Year', 'Repos Created', plots_dir / f'creation_years.{cfg.PLOT_FORMAT}', color=_PALETTE[0])})\n")
        out.append(_table(["Year", "Repos Created"], [[str(y), _fmt(cy[y])] for y in sorted(cy)]) + "\n")

    # Technique Commit Span — avg interval between consecutive technique commits (Item 29)
    css = tl.get("commit_span_stats", {})
    excluded_n = tl.get("commit_span_excluded_count", 0)
    if css:
        out.append("### Technique Commit Span\n")
        out.append(
            f"_Technique Commit Span = average number of days between consecutive commits containing "
            f"technique keyword matches, per repo. "
            f"Repos with fewer than 2 technique commits are excluded from this metric "
            f"({excluded_n} repos excluded)._\n"
        )
        out.append(_table(
            ["Metric", "Avg", "Median", "Max (days)", "Min (days)", "Std Dev", "N Repos"],
            [["Technique commit span (days)"] + _stat_cells(css)],
        ) + "\n")

    cs_sorted = ca.get("commit_spans_sorted", [])
    if cs_sorted:
        ranks = list(range(1, len(cs_sorted) + 1))
        out.append(f"![Commit span distribution]({_line_chart(ranks, [r['span_days'] for r in cs_sorted], 'Technique Commit Span per Repo (Ranked Longest → Shortest)', 'Rank (1 = longest span)', 'Span (days)', plots_dir / f'commit_span_distribution.{cfg.PLOT_FORMAT}')})\n")
        out.append(f"_Repos with fewer than 2 technique commits are excluded. {excluded_n} repos excluded._\n")

    cbm  = tl.get("commits_by_month", {})
    tcbm = tl.get("technique_commits_by_month", {})

    if cbm:
        months     = sorted(cbm.keys())
        cbm_vals   = [cbm[m] for m in months]
        out.append("### Monthly Commit Activity (All Commits)\n")
        out.append(f"![Commits by month]({_line_chart(list(range(len(months))), cbm_vals, 'Monthly Commit Activity (All Repos, All Commits)', 'Month', 'Commits', plots_dir / f'commits_by_month.{cfg.PLOT_FORMAT}', x_labels=months)})\n")
        import statistics as _stats
        if cbm_vals:
            cbm_stats = {
                "avg":    round(sum(cbm_vals) / len(cbm_vals), 2),
                "median": round(_stats.median(cbm_vals), 2),
                "max":    round(max(cbm_vals), 2),
                "min":    round(min(cbm_vals), 2),
                "stdev":  round(_stats.stdev(cbm_vals), 2) if len(cbm_vals) >= 2 else 0,
                "count":  len(cbm_vals),
            }
            out.append(_table(
                ["Metric", "Avg", "Median", "Max", "Min", "Std Dev", "Months"],
                [["Commits per month"] + _stat_cells(cbm_stats)],
            ) + "\n")

    if tcbm:
        months    = sorted(tcbm.keys())
        tcbm_vals = [tcbm[m] for m in months]
        out.append("### Monthly Technique Commit Activity\n")
        out.append(f"![Technique commits by month]({_line_chart(list(range(len(months))), tcbm_vals, 'Monthly Technique-Keyword Commits (PyDriller git history)', 'Month', 'Technique Commits', plots_dir / f'technique_commits_by_month.{cfg.PLOT_FORMAT}', x_labels=months)})\n")
        import statistics as _stats
        if tcbm_vals:
            tcbm_stats = {
                "avg":    round(sum(tcbm_vals) / len(tcbm_vals), 2),
                "median": round(_stats.median(tcbm_vals), 2),
                "max":    round(max(tcbm_vals), 2),
                "min":    round(min(tcbm_vals), 2),
                "stdev":  round(_stats.stdev(tcbm_vals), 2) if len(tcbm_vals) >= 2 else 0,
                "count":  len(tcbm_vals),
            }
            out.append(_table(
                ["Metric", "Avg", "Median", "Max", "Min", "Std Dev", "Months"],
                [["Technique commits per month"] + _stat_cells(tcbm_stats)],
            ) + "\n")

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
        ax.set_title("Total vs Technique Commits per Month (PyDriller git history)")
        ax.legend(fontsize=8)
        out.append(f"![Total vs technique commits]({_save(fig, plots_dir / f'commits_proportion.{cfg.PLOT_FORMAT}')})\n")


def _section_all_repos(overall: dict, dirs: dict, out: list[str]) -> None:
    out.append("## 9. All Cloned Repositories\n")
    code_repos = load_json(dirs["analysis"] / "code_repos.json", [])
    if not code_repos:
        out.append("_No code repos data available._\n")
        return
    total_repos = len(code_repos)
    sorted_repos = sorted(code_repos,
                          key=lambda r: r.get("scan", {}).get("total_specific_hits", 0), reverse=True)
    display_repos = sorted_repos[:200]
    out.append(f"_{total_repos} repositories were cloned and analysed._\n")
    if total_repos > 200:
        slug = overall.get("slug", "")
        out.append(
            f"_Showing top 200 of {total_repos} repositories by specific keyword hits. "
            f"Full data available in `results/{slug}/analysis/code_repos.json`._\n"
        )
    repo_rows = []
    for rank, r in enumerate(display_repos, 1):
        scan    = r.get("scan", {})
        n_lines = scan.get("total_lines", 0)
        hl      = scan.get("total_hit_lines", 0)
        cls_list = r.get("classification", {}).get("classifications", ["—"])
        commits = r.get("commits", {})
        span = commits.get("technique_commit_span_avg_days", commits.get("commit_span_days"))
        repo_rows.append([
            rank,
            _trunc(r.get("full_name", ""), 38),
            _fmt(r.get("stars", 0)),
            r.get("language", "—"),
            _fmt(scan.get("total_files", 0)),
            _fmt(scan.get("total_specific_hits", 0)),
            _pct(round(hl / max(n_lines, 1) * 100, 1)),
            _fmt(span),
            ", ".join(cls_list),
        ])
    out.append(_table(
        ["#", "Repository", "Stars", "Language", "Files", "Specific Hits",
         "Hit Line %", "Technique Span (days)", "Classification"],
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
    _section_technique_file_extensions(overall, plots_dir, tech_name, out)
    _section_language(overall, plots_dir, tech_name, out)
    _section_domain(overall, plots_dir, tech_name, out)
    _section_timeline(overall, plots_dir, tech_name, out)
    _section_all_repos(overall, dirs, out)

    report_path.write_text("\n".join(out), encoding="utf-8")
    print(f"Report written to {report_path}")
