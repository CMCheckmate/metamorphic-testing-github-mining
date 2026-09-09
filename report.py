"""
Report Phase
============
Reads overall.json, code_repos.json, noncode_results.json.
Generates report.md and plots/ — NO calculations performed here.
All numbers come from stored values in those files.

Chart rules:
- Every bar shows exact count on top (or beside if horizontal).
- Dashed line = median, dotted line = mean.
- Title above plot, large. No auto-generated caption below.
- Labels legible at configured DPI.
- Wide tables truncate long values with ellipsis at a fixed column width.
"""

from __future__ import annotations

import textwrap
from collections import defaultdict
from io import StringIO
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

import config as cfg
from config import TECHNIQUE_DISPLAY_NAMES, TECHNIQUE_SHORT_NAMES
from utils import (
    resolve_technique, technique_dirs, ensure_dirs,
    setup_logging, load_json,
)

MAX_COL_WIDTH = 40  # chars for truncated table columns


# ---------------------------------------------------------------------------
# Markdown table helpers
# ---------------------------------------------------------------------------

def _trunc(s: str, n: int = MAX_COL_WIDTH) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def _fmt(v: float | int | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    if isinstance(v, int) or (isinstance(v, float) and v == int(v)):
        return str(int(v))
    return f"{v:.{decimals}f}"


def _stats_row(label: str, stats: dict) -> str:
    avg    = _fmt(stats.get("avg"))
    median = _fmt(stats.get("median"))
    max_v  = _fmt(stats.get("max"))
    min_v  = _fmt(stats.get("min"))
    rng    = _fmt(stats.get("range"))
    return f"| {label} | {avg} | {median} | {max_v} | {min_v} | {rng} |"


def _stats_header() -> list[str]:
    return [
        "| Metric | Avg | Median | Max | Min | Range |",
        "|--------|-----|--------|-----|-----|-------|",
    ]


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _bar_chart(
    labels: list[str],
    values: list[float],
    title: str,
    xlabel: str,
    ylabel: str,
    out_path: Path,
    median: float | None = None,
    mean: float | None = None,
    horizontal: bool = False,
    color: str = "#1a6e3c",
) -> None:
    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 0.6 + 2), 5))
    y = np.arange(len(labels))
    truncated_labels = [_trunc(str(l), 25) for l in labels]

    if horizontal:
        bars = ax.barh(y, values, color=color, edgecolor="white")
        ax.set_yticks(y)
        ax.set_yticklabels(truncated_labels, fontsize=8)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
                str(int(val)) if val == int(val) else f"{val:.1f}",
                va="center", ha="left", fontsize=7,
            )
        if median is not None:
            ax.axvline(median, color="#e65100", linestyle="--", linewidth=1.5, label=f"Median={_fmt(median)}")
        if mean is not None:
            ax.axvline(mean, color="#1565c0", linestyle=":", linewidth=1.5, label=f"Mean={_fmt(mean)}")
    else:
        bars = ax.bar(y, values, color=color, edgecolor="white")
        ax.set_xticks(y)
        ax.set_xticklabels(truncated_labels, rotation=45, ha="right", fontsize=8)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.01,
                str(int(val)) if val == int(val) else f"{val:.1f}",
                ha="center", va="bottom", fontsize=7,
            )
        if median is not None:
            ax.axhline(median, color="#e65100", linestyle="--", linewidth=1.5, label=f"Median={_fmt(median)}")
        if mean is not None:
            ax.axhline(mean, color="#1565c0", linestyle=":", linewidth=1.5, label=f"Mean={_fmt(mean)}")

    if median is not None or mean is not None:
        ax.legend(fontsize=8)

    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    plt.tight_layout()
    fig.savefig(out_path, dpi=cfg.PLOT_DPI, bbox_inches="tight", format=cfg.PLOT_FORMAT)
    plt.close(fig)


def _line_chart(
    x_labels: list[str],
    series: dict[str, list[float]],
    title: str,
    xlabel: str,
    ylabel: str,
    out_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(max(10, len(x_labels) * 0.3 + 2), 5))
    colors = ["#1a6e3c", "#b71c1c", "#1565c0", "#e65100"]
    for i, (label, values) in enumerate(series.items()):
        ax.plot(x_labels, values, label=label, color=colors[i % len(colors)], linewidth=1.5)

    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    step = max(1, len(x_labels) // 12)
    ax.set_xticks(x_labels[::step])
    ax.set_xticklabels(x_labels[::step], rotation=45, ha="right", fontsize=7)
    ax.legend(fontsize=8)
    plt.tight_layout()
    fig.savefig(out_path, dpi=cfg.PLOT_DPI, bbox_inches="tight", format=cfg.PLOT_FORMAT)
    plt.close(fig)


def _histogram(
    values: list[float],
    title: str,
    xlabel: str,
    ylabel: str,
    out_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(values, bins=20, color="#1a6e3c", edgecolor="white")
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
    plt.tight_layout()
    fig.savefig(out_path, dpi=cfg.PLOT_DPI, bbox_inches="tight", format=cfg.PLOT_FORMAT)
    plt.close(fig)


def _word_cloud(word_freq: dict, title: str, out_path: Path) -> None:
    try:
        from wordcloud import WordCloud
        wc = WordCloud(width=1200, height=600, background_color="white",
                       colormap="viridis", max_words=150)
        wc.generate_from_frequencies(word_freq)
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
        plt.tight_layout()
        fig.savefig(out_path, dpi=cfg.PLOT_DPI, bbox_inches="tight", format=cfg.PLOT_FORMAT)
        plt.close(fig)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_summary(overall: dict, slug: str, buf: StringIO) -> None:
    display = TECHNIQUE_DISPLAY_NAMES.get(slug, slug)
    short   = TECHNIQUE_SHORT_NAMES.get(slug, slug)
    code_agg = overall.get("code_analysis", {})
    nc_agg   = overall.get("noncode_analysis", {})

    buf.write(f"# {display} — Mining Report\n\n")
    buf.write("## Summary\n\n")
    buf.write(f"| Metric | Value |\n|--------|-------|\n")
    buf.write(f"| Technique | {display} ({short}) |\n")
    buf.write(f"| Total distinct repos found | {overall.get('repos_found_total', 0)} |\n")
    buf.write(f"| Repos cloned & analysed (code surface) | {code_agg.get('repo_count', 0)} |\n")
    buf.write(f"| Non-code items analysed | {nc_agg.get('total_items', 0)} |\n")

    cls = code_agg.get("classification_counts", {})
    for label, count in cls.items():
        buf.write(f"| Classified as {label.replace('_',' ')} | {count} |\n")
    buf.write("\n")


def _section_rq1(overall: dict, plots_dir: Path, buf: StringIO) -> None:
    buf.write("## RQ1 — Adoption Extent\n\n")
    code_agg = overall.get("code_analysis", {})
    search   = overall.get("search_summary", {})
    size_stats = overall.get("repo_size_stats", {})

    # --- Repo discovery table ---
    buf.write("### Repo Discovery\n\n")
    buf.write("#### Size Statistics (KB)\n\n")
    buf.write("\n".join(_stats_header()) + "\n")
    buf.write(_stats_row("All repos", size_stats.get("overall", {})) + "\n")
    for surface, stats in size_stats.get("by_surface", {}).items():
        buf.write(_stats_row(surface.capitalize(), stats) + "\n")
    buf.write("\n")

    # Search hits by surface
    buf.write("#### Search Hits by Surface\n\n")
    buf.write("| Surface | API Hit Count | Unique Results |\n")
    buf.write("|---------|--------------|----------------|\n")
    for surface in ["code", "repos", "commits", "prs", "issues", "discussions"]:
        data = search.get(surface, {})
        buf.write(f"| {surface.upper()} | {data.get('api_hit_count', 0)} | {data.get('unique_results', 0)} |\n")
    buf.write("\n")

    # --- Technique density ---
    buf.write("### Technique Density\n\n")
    buf.write("#### Per-Repo Hit Statistics\n\n")
    buf.write("\n".join(_stats_header()) + "\n")
    buf.write(_stats_row("Specific hits / repo", code_agg.get("specific_hits_per_repo", {})) + "\n")
    buf.write(_stats_row("General hits / repo",  code_agg.get("general_hits_per_repo", {})) + "\n")
    buf.write(_stats_row("Files / repo",          code_agg.get("files_per_repo", {})) + "\n")
    buf.write(_stats_row("Hit files / repo",      code_agg.get("hit_files_per_repo", {})) + "\n")
    buf.write(_stats_row("Lines / repo",          code_agg.get("lines_per_repo", {})) + "\n")
    buf.write(_stats_row("Hit lines / repo",      code_agg.get("hit_lines_per_repo", {})) + "\n")
    buf.write("\n")

    # By file category
    buf.write("#### Hits by File Category\n\n")
    buf.write("| Category | Files | Hit Files | Hit% | Lines | Hit Lines | Hit Line% | Gen Hits | Spec Hits |\n")
    buf.write("|----------|-------|-----------|------|-------|-----------|-----------|----------|-----------|\n")
    for cat, stats in code_agg.get("by_category", {}).items():
        buf.write(
            f"| {cat} | {stats['total_files']} | {stats['hit_file_count']} | "
            f"{stats['hit_file_pct']}% | {stats['total_lines']} | "
            f"{stats['hit_line_count']} | {stats['hit_line_pct']}% | "
            f"{stats['total_general_hits']} | {stats['total_specific_hits']} |\n"
        )
    buf.write("\n")

    # Density bands chart
    bands = code_agg.get("density_bands_hits", {})
    if bands:
        labels = list(bands.keys())
        values = [float(v) for v in bands.values()]
        out = plots_dir / f"density_bands_hits.{cfg.PLOT_FORMAT}"
        _bar_chart(labels, values, "Repos by Technique Hit Count Band",
                   "Hit Count Band", "Number of Repos", out)
        buf.write(f"![Density bands](plots/density_bands_hits.{cfg.PLOT_FORMAT})\n\n")


def _section_rq2(overall: dict, plots_dir: Path, buf: StringIO) -> None:
    buf.write("## RQ2 — Usage Patterns\n\n")
    code_agg = overall.get("code_analysis", {})
    nc_agg   = overall.get("noncode_analysis", {})

    # --- Keyword hits ---
    buf.write("### Search Keyword Hit Distribution\n\n")
    search = overall.get("search_summary", {})
    kw_total = search.get("keywords_total", {})
    if kw_total:
        buf.write("| Keyword | Total Unique Results |\n|---------|---------------------|\n")
        for kw, cnt in list(kw_total.items())[:cfg.REPORT_TOP_N_KEYWORDS]:
            buf.write(f"| {_trunc(kw)} | {cnt} |\n")
        buf.write("\n")
        top_kws = list(kw_total.items())[:20]
        if top_kws:
            out = plots_dir / f"keyword_hits.{cfg.PLOT_FORMAT}"
            _bar_chart(
                [_trunc(k, 30) for k, _ in top_kws],
                [float(v) for _, v in top_kws],
                "Top Search Keywords by Unique Results",
                "Keyword", "Unique Results", out, horizontal=True,
            )
            buf.write(f"![Keyword hits](plots/keyword_hits.{cfg.PLOT_FORMAT})\n\n")

    # --- Analysis keyword hits ---
    buf.write("### Analysis Keyword Hits (Cloned Repos)\n\n")
    kws_ranked = code_agg.get("keywords_ranked", [])
    if kws_ranked:
        buf.write("| Rank | Keyword | Count |\n|------|---------|-------|\n")
        for i, entry in enumerate(kws_ranked[:cfg.REPORT_TOP_N_KEYWORDS], 1):
            label = entry.get("label") or entry.get("id", "")
            buf.write(f"| {i} | {_trunc(label)} | {entry['count']} |\n")
        buf.write("\n")
        top = kws_ranked[:20]
        if top:
            out = plots_dir / f"analysis_keyword_hits.{cfg.PLOT_FORMAT}"
            _bar_chart(
                [_trunc(e.get("label", e["id"]), 30) for e in top],
                [float(e["count"]) for e in top],
                "Top Analysis Keywords by Match Count",
                "Keyword", "Total Hits", out, horizontal=True,
            )
            buf.write(f"![Analysis keyword hits](plots/analysis_keyword_hits.{cfg.PLOT_FORMAT})\n\n")

    # --- Classification ---
    buf.write("### Repo Classification\n\n")
    cls = code_agg.get("classification_counts", {})
    if cls:
        buf.write("| Classification | Count |\n|----------------|-------|\n")
        for label, count in cls.items():
            buf.write(f"| {label.replace('_',' ')} | {count} |\n")
        buf.write("\n")
        out = plots_dir / f"classification.{cfg.PLOT_FORMAT}"
        _bar_chart(
            [k.replace("_", " ") for k in cls.keys()],
            [float(v) for v in cls.values()],
            "Repo Classification Breakdown",
            "Classification", "Number of Repos", out,
        )
        buf.write(f"![Classification](plots/classification.{cfg.PLOT_FORMAT})\n\n")

    # --- Language distribution ---
    buf.write("### Language Distribution\n\n")
    lang_dist = code_agg.get("language_distribution", {})
    if lang_dist:
        buf.write("| Language | Repos |\n|----------|-------|\n")
        for lang, cnt in list(lang_dist.items())[:20]:
            buf.write(f"| {lang} | {cnt} |\n")
        buf.write("\n")
        top_langs = list(lang_dist.items())[:15]
        if top_langs:
            out = plots_dir / f"language_distribution.{cfg.PLOT_FORMAT}"
            _bar_chart(
                [l for l, _ in top_langs],
                [float(c) for _, c in top_langs],
                "Language Distribution (Cloned Repos)",
                "Language", "Number of Repos", out,
            )
            buf.write(f"![Language distribution](plots/language_distribution.{cfg.PLOT_FORMAT})\n\n")

    # --- Domain word cloud ---
    buf.write("### Application Domain\n\n")
    top_words = nc_agg.get("top_word_freq", {})
    if top_words:
        out = plots_dir / f"wordcloud.{cfg.PLOT_FORMAT}"
        _word_cloud(top_words, "Domain Word Cloud", out)
        buf.write(f"![Word cloud](plots/wordcloud.{cfg.PLOT_FORMAT})\n\n")

    domain_counts = nc_agg.get("domain_counts", {})
    if domain_counts:
        buf.write("#### Domain Distribution\n\n")
        buf.write("| Domain | Count |\n|--------|-------|\n")
        for domain, cnt in domain_counts.items():
            buf.write(f"| {domain.replace('_',' ')} | {cnt} |\n")
        buf.write("\n")


def _section_rq3(overall: dict, plots_dir: Path, buf: StringIO) -> None:
    buf.write("## RQ3 — Timeline\n\n")
    code_agg = overall.get("code_analysis", {})
    timeline = code_agg.get("timeline", {})
    if not timeline:
        buf.write("_No timeline data available._\n\n")
        return

    # Creation dates histogram
    creation_years = timeline.get("creation_years", {})
    if creation_years:
        years = sorted(creation_years.keys())
        counts = [creation_years[y] for y in years]
        out = plots_dir / f"creation_years.{cfg.PLOT_FORMAT}"
        _bar_chart(
            [str(y) for y in years], [float(c) for c in counts],
            "Repository Creation Year Distribution",
            "Year", "Number of Repos", out,
        )
        buf.write(f"![Creation years](plots/creation_years.{cfg.PLOT_FORMAT})\n\n")

    # Commit activity over time
    commits_by_month = timeline.get("commits_by_month", {})
    tech_by_month    = timeline.get("technique_commits_by_month", {})
    if commits_by_month:
        all_months = sorted(set(list(commits_by_month.keys()) + list(tech_by_month.keys())))
        if all_months:
            out = plots_dir / f"commits_over_time.{cfg.PLOT_FORMAT}"
            _line_chart(
                all_months,
                {
                    "All commits": [float(commits_by_month.get(m, 0)) for m in all_months],
                    "Technique commits": [float(tech_by_month.get(m, 0)) for m in all_months],
                },
                "Commit Activity Over Time",
                "Month", "Commit Count", out,
            )
            buf.write(f"![Commit activity](plots/commits_over_time.{cfg.PLOT_FORMAT})\n\n")

    # Commit span histogram
    span_bands = timeline.get("repos_by_commit_span", {})
    if span_bands:
        labels = list(span_bands.keys())
        values = [float(span_bands[l]) for l in labels]
        out = plots_dir / f"commit_span_bands.{cfg.PLOT_FORMAT}"
        _bar_chart(labels, values, "Repos by Commit Span", "Span", "Number of Repos", out)
        buf.write(f"![Commit span](plots/commit_span_bands.{cfg.PLOT_FORMAT})\n\n")

    span_stats = timeline.get("commit_span_stats", {})
    if span_stats:
        buf.write("#### Commit Span Statistics\n\n")
        buf.write("\n".join(_stats_header()) + "\n")
        buf.write(_stats_row("Commit span (days)", span_stats) + "\n\n")


def _section_all_repos(code_repos: list[dict], buf: StringIO) -> None:
    buf.write("## All Cloned Repos\n\n")
    buf.write("| Repo | URL | Stars | Language | Classifications |\n")
    buf.write("|------|-----|-------|----------|-----------------|\n")
    for r in code_repos[:cfg.REPORT_TOP_N_REPOS]:
        name  = _trunc(r.get("full_name", ""), 35)
        url   = _trunc(r.get("html_url", ""), 50)
        stars = r.get("stars", "—")
        lang  = r.get("language", "—") or "—"
        cls   = ", ".join(r.get("classification", {}).get("classifications", []))
        buf.write(f"| {name} | {url} | {stars} | {lang} | {cls} |\n")
    buf.write("\n")


def _section_search_hits(overall: dict, buf: StringIO) -> None:
    buf.write("## Search Hit Counts\n\n")
    buf.write("| Surface | API Hit Count | Unique Results |\n")
    buf.write("|---------|--------------|----------------|\n")
    search = overall.get("search_summary", {})
    for surface in ["code", "repos", "commits", "prs", "issues", "discussions"]:
        data = search.get(surface, {})
        buf.write(
            f"| {surface.upper()} | {data.get('api_hit_count', '—')} "
            f"| {data.get('unique_results', '—')} |\n"
        )
    buf.write("\n")


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(slug: str) -> None:
    ensure_dirs(slug)
    dirs = technique_dirs(slug)
    logger = setup_logging(slug, "report")

    plots_dir = dirs["plots"]
    plots_dir.mkdir(parents=True, exist_ok=True)

    overall_path     = dirs["analysis"] / "overall.json"
    code_repos_path  = dirs["analysis"] / "code_repos.json"

    overall: dict    = load_json(overall_path, {})
    code_repos: list = load_json(code_repos_path, [])

    if not overall:
        print(f"overall.json not found — run analysis phase first.")
        return

    buf = StringIO()

    _section_summary(overall, slug, buf)
    _section_search_hits(overall, buf)
    _section_rq1(overall, plots_dir, buf)
    _section_rq2(overall, plots_dir, buf)
    _section_rq3(overall, plots_dir, buf)
    _section_all_repos(code_repos, buf)

    report_path = dirs["report"] / "report.md"
    report_path.write_text(buf.getvalue(), encoding="utf-8")

    print(f"\nReport written to {report_path}")
    logger.info(f"Report written: {report_path}")
