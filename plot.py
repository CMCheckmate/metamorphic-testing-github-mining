"""
Phase 4 — Plots & Visualisations
==================================
All per-technique plots apply only to detected repositories (score > 0).
No tier (strong/weak) grouping is used.

Usage:
    python plot.py --technique techniques/metamorphic_testing.yaml
    python plot.py --technique techniques/fuzzing.yaml --format pdf --dpi 300
"""

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from rich.console import Console

from config import RESULTS_DIR

console = Console()

PRIMARY_COLOR   = "#1a6e3c"
SECONDARY_COLOR = "#4472c4"

sns.set_theme(style="whitegrid", font_scale=1.1)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path):
    if not path.exists():
        console.print(f"[yellow]Missing:[/] {path}")
        return None
    with open(path) as f:
        return json.load(f)


def load_all(raw_dir: Path, analysis_dir: Path):
    return {
        "summary":     _load_json(raw_dir      / "summary.json"),
        "repo_scores": _load_json(analysis_dir / "repo_scores.json"),
        "findings":    _load_json(analysis_dir / "findings.json"),
    }


def _detected(repo_scores):
    return [r for r in (repo_scores or []) if r.get("score", 0) > 0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save(fig, out_dir: Path, name: str, fmt: str, dpi: int) -> None:
    path = out_dir / f"{name}.{fmt}"
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    console.print(f"  [green]saved[/] {path.name}")


_SURFACE_COLORS = {
    "repo":       "#4e79a7",
    "code":       "#f28e2b",
    "commit":     "#59a14f",
    "issue":      "#e15759",
    "pr":         "#76b7b2",
    "discussion": "#edc948",
}


def _query_surface(label: str) -> str:
    for prefix in ("code", "commit", "issue", "pr", "repo"):
        if label.startswith(prefix + "_"):
            return prefix
    return "discussion"


def _build_raw_to_surface(summary) -> dict:
    priority = {"code": 0, "repo": 1, "commit": 2, "issue": 3, "pr": 4, "discussion": 5}
    out = {}
    for q in (summary or {}).get("queries", []):
        raw, surface = q.get("query", ""), q.get("type", "discussion")
        if raw not in out or priority.get(surface, 99) < priority.get(out[raw], 99):
            out[raw] = surface
    return out


# ===========================================================================
# ADOPTION — RQ1
# ===========================================================================

def plot_detection_count_hist(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Line rank plot: detection counts sorted descending (rank vs count)."""
    detected = _detected(repo_scores)
    scores   = sorted([r["score"] for r in detected], reverse=True)
    if not scores:
        return

    mean_v   = sum(scores) / len(scores)
    median_v = sorted(scores)[len(scores) // 2]
    ranks    = list(range(1, len(scores) + 1))

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ranks, scores, color=PRIMARY_COLOR, linewidth=1.5, label="Detection count")
    ax.axhline(mean_v,   color="#e15759", linestyle="--", linewidth=1.5, label=f"Mean = {mean_v:.1f}")
    ax.axhline(median_v, color="#4e79a7", linestyle="--", linewidth=1.5, label=f"Median = {median_v:.1f}")
    ax.set_xlabel("Repository rank (sorted by detection count)")
    ax.set_ylabel("Detection count (pattern matches)")
    ax.set_title(f"{technique_name} — Detection Count Distribution (Rank Plot)")
    ax.legend(fontsize=9)
    _save(fig, out_dir, "detection_count_hist", fmt, dpi)


def plot_yearly_trend(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Line chart: repos by creation year — total and detected as separate lines."""
    if not repo_scores:
        return
    rows = []
    for r in repo_scores:
        created = r.get("created_at", "")
        if created and len(created) >= 4 and created[:4].isdigit():
            rows.append({"year": int(created[:4]), "detected": r.get("score", 0) > 0})
    if not rows:
        return
    df = pd.DataFrame(rows)
    df = df[df["year"] >= 2010]
    detected_yearly = df[df["detected"]].groupby("year").size().reset_index(name="detected")
    all_yearly      = df.groupby("year").size().reset_index(name="total")
    merged = all_yearly.merge(detected_yearly, on="year", how="left").fillna(0)

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(merged["year"], merged["total"],    color="#9e9e9e", linewidth=2,
            marker="o", markersize=5, label="Total repos")
    ax.plot(merged["year"], merged["detected"], color=PRIMARY_COLOR, linewidth=2,
            marker="o", markersize=5, label="Detected")
    ax.fill_between(merged["year"], merged["detected"], alpha=0.15, color=PRIMARY_COLOR)
    ax.set_xlabel("Repository creation year")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Repos by Creation Year")
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    ax.tick_params(axis="x", rotation=45)
    ax.legend()
    _save(fig, out_dir, "yearly_trend", fmt, dpi)


def plot_size_comparison(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Two-panel boxplot: total lines and total files, detected vs not-detected repos."""
    detected = _detected(repo_scores)
    not_det  = [r for r in (repo_scores or []) if r.get("score", 0) == 0]

    det_lines = [r.get("total_lines_scanned", 0) for r in detected if r.get("total_lines_scanned", 0) > 0]
    not_lines = [r.get("total_lines_scanned", 0) for r in not_det  if r.get("total_lines_scanned", 0) > 0]
    det_files = [r.get("total_files_scanned", 0) for r in detected if r.get("total_files_scanned", 0) > 0]
    not_files = [r.get("total_files_scanned", 0) for r in not_det  if r.get("total_files_scanned", 0) > 0]

    if not det_lines and not det_files:
        return

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for ax, det_vals, not_vals, title, ylabel in [
        (axes[0], det_lines, not_lines, "Total Lines Scanned", "Lines"),
        (axes[1], det_files, not_files, "Total Files Scanned", "Files"),
    ]:
        data_to_plot, tick_labels = [], []
        if det_vals:
            data_to_plot.append(det_vals)
            tick_labels.append(f"Detected\n(n={len(det_vals):,})")
        if not_vals:
            data_to_plot.append(not_vals)
            tick_labels.append(f"Not Detected\n(n={len(not_vals):,})")
        if data_to_plot:
            bp = ax.boxplot(data_to_plot, tick_labels=tick_labels, patch_artist=True, showfliers=False)
            for patch, color in zip(bp["boxes"], [PRIMARY_COLOR, "#bdbdbd"]):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)
            if any(v > 0 for vals in data_to_plot for v in vals):
                ax.set_yscale("log")
            ax.set_ylabel(f"{ylabel} (log scale)")
            ax.set_title(title)

    fig.suptitle(f"{technique_name} — Repository Scale: Detected vs Not Detected", fontweight="bold")
    plt.tight_layout()
    _save(fig, out_dir, "size_comparison", fmt, dpi)


def plot_technique_ratios(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Two-panel: technique line density and file ratio distributions for detected repos."""
    detected = _detected(repo_scores)
    if not detected:
        return

    line_density = [r.get("technique_line_density", 0) for r in detected if r.get("technique_line_density", 0) > 0]
    file_ratio   = [r.get("technique_file_ratio", 0)   for r in detected if r.get("technique_file_ratio", 0) > 0]

    if not line_density and not file_ratio:
        return

    ld_main, ld_out = _split_outliers(line_density)
    fr_main, fr_out = _split_outliers(file_ratio)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    if line_density:
        plot_ld = ld_main if ld_main else line_density
        axes[0].hist(plot_ld, bins=25, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
        med = statistics.median(plot_ld)
        axes[0].axvline(med, color="#e15759", linestyle="--", linewidth=1.5, label=f"Median = {med*100:.2f}%")
        axes[0].xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0, decimals=2))
        axes[0].set_xlabel("Technique code lines ÷ total lines")
        axes[0].set_ylabel("Repositories")
        axes[0].set_title("Share of code that is technique code")
        if ld_out:
            axes[0].text(0.98, 0.96, f"+{len(ld_out)} outliers", transform=axes[0].transAxes,
                         ha="right", va="top", fontsize=9, color="#e15759")
        axes[0].legend(fontsize=9)

    if file_ratio:
        plot_fr = fr_main if fr_main else file_ratio
        axes[1].hist(plot_fr, bins=25, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
        med = statistics.median(plot_fr)
        axes[1].axvline(med, color="#e15759", linestyle="--", linewidth=1.5, label=f"Median = {med*100:.1f}%")
        axes[1].xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0, decimals=0))
        axes[1].set_xlabel("Technique files ÷ total files")
        axes[1].set_ylabel("Repositories")
        axes[1].set_title("Share of files using the technique")
        if fr_out:
            axes[1].text(0.98, 0.96, f"+{len(fr_out)} outliers", transform=axes[1].transAxes,
                         ha="right", va="top", fontsize=9, color="#e15759")
        axes[1].legend(fontsize=9)

    fig.suptitle(f"{technique_name} — Technique Code & File Coverage", fontweight="bold")
    plt.tight_layout()
    _save(fig, out_dir, "technique_ratios", fmt, dpi)


def plot_contributor_dist(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Histogram: unique git contributors per detected repo."""
    detected = _detected(repo_scores)
    values = [r.get("contributor_count_git", 0) for r in detected if r.get("contributor_count_git", 0) > 0]
    if not values:
        return
    cap  = min(max(values) + 2, 31)
    bins = list(range(1, cap))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(values, bins=bins, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Unique contributors (git log, sampled commits)")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Contributor Count Distribution")
    _save(fig, out_dir, "contributor_dist", fmt, dpi)


# ===========================================================================
# USAGE — RQ2
# ===========================================================================

def plot_language_dist(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Bar chart: top languages by detected repo count, derived from scanned file extensions."""
    detected = _detected(repo_scores)
    if not detected:
        return
    langs: Counter = Counter()
    for r in detected:
        lb = r.get("language_breakdown") or {}
        if lb:
            for lang in lb:
                langs[lang] += 1          # count repos containing this language
        elif r.get("language"):
            langs[r["language"]] += 1     # fallback: GitHub-reported primary language
    top    = langs.most_common(15)
    labels = [l for l, _ in top]
    values = [v for _, v in top]

    fig, ax = plt.subplots(figsize=(9, 5))
    palette = sns.color_palette("viridis", n_colors=len(labels))
    bars = ax.bar(labels, values, color=palette, edgecolor="white", linewidth=0.8)
    ax.bar_label(bars, padding=3, fontsize=9)
    ylabel = "Detected repositories"
    if len(values) > 1:
        sv = sorted(values, reverse=True)
        if sv[0] > 4 * sv[1]:
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
            ylabel = "Detected repositories (log scale)"
    ax.set_ylabel(ylabel)
    ax.set_title(f"{technique_name} — Language Distribution (Top 15, Detected Repos)")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right")
    _save(fig, out_dir, "language_dist", fmt, dpi)


def plot_project_type_dist(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Bar chart: project type for detected repos (non-detected shown separately)."""
    scores   = repo_scores or []
    detected = _detected(scores)
    not_det  = [r for r in scores if r.get("score", 0) == 0]
    if not detected:
        return
    det_counts  = Counter(r.get("project_type", "unknown") for r in detected)
    order  = ["general_usage", "framework", "mixed", "research_artifact", "documentation_only", "unknown"]
    colors_map = {
        "general_usage":      "#1a6e3c",
        "framework":          "#4472c4",
        "mixed":              "#f0ad3a",
        "research_artifact":  "#d62728",
        "documentation_only": "#9467bd",
        "unknown":            "#bdbdbd",
        "not_detected":       "#e0e0e0",
    }
    display_map = {
        "general_usage":      "Actual Usage",
        "framework":          "Framework / Library",
        "mixed":              "Mixed",
        "research_artifact":  "Research Artifact",
        "documentation_only": "Docs Only",
        "unknown":            "Unknown",
        "not_detected":       "Not Detected",
    }

    labels  = [k for k in order if det_counts.get(k, 0) > 0]
    values  = [det_counts[k] for k in labels]
    # append not-detected
    if not_det:
        labels.append("not_detected")
        values.append(len(not_det))
    colors  = [colors_map[k] for k in labels]
    display = [display_map.get(k, k) for k in labels]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(display, values, color=colors, edgecolor="white", linewidth=0.8)
    ax.bar_label(bars, padding=3, fontsize=10)
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Project Role Distribution")
    ax.set_xticks(range(len(display)))
    ax.set_xticklabels(display, rotation=20, ha="right")
    _save(fig, out_dir, "project_type_dist", fmt, dpi)


def plot_artifact_breakdown(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Horizontal stacked bar: signal matches by artifact type."""
    detected = _detected(repo_scores)
    if not detected:
        return
    totals: Counter = Counter()
    for r in detected:
        for atype, cnt in (r.get("artifact_breakdown") or {}).items():
            totals[atype] += cnt
    if not totals:
        return
    artifact_order  = ["test_code", "source_code", "documentation", "config", "other"]
    artifact_colors = {
        "test_code":     "#2166ac", "source_code": "#4dac26",
        "documentation": "#d6604d", "config":      "#f4a582", "other": "#bababa",
    }
    keys  = [k for k in artifact_order if k in totals]
    total = sum(totals.values())
    pcts  = [totals[k] / total * 100 for k in keys]

    fig, ax = plt.subplots(figsize=(11, 3))
    left = 0.0
    for k, pct in zip(keys, pcts):
        ax.barh([""], [pct], left=left, color=artifact_colors.get(k, "#aaa"),
                label=k.replace("_", " ").title(), edgecolor="white", linewidth=0.5)
        if pct >= 4:
            ax.text(left + pct / 2, 0, f"{pct:.1f}%", va="center", ha="center",
                    fontsize=9, color="white" if k in ("test_code", "source_code") else "black")
        left += pct
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of signal matches")
    ax.set_title(f"{technique_name} — Signal Distribution by Artifact Type")
    ax.legend(loc="upper right", fontsize=9, bbox_to_anchor=(1, 1.35))
    ax.set_yticks([])
    _save(fig, out_dir, "artifact_breakdown", fmt, dpi)


def plot_extension_breakdown(findings, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Horizontal bar: top file extensions with technique signal matches."""
    if not findings:
        return
    ext_counts: Counter = Counter()
    for f in findings:
        fname = f.get("file", "")
        if fname:
            dot = fname.rfind(".")
            ext = fname[dot:].lower() if dot >= 0 else "(none)"
            ext_counts[ext] += 1
    if not ext_counts:
        return
    top    = ext_counts.most_common(15)
    labels = [l for l, _ in reversed(top)]
    values = [v for _, v in reversed(top)]

    fig, ax = plt.subplots(figsize=(9, max(5, len(labels) * 0.38)))
    palette = sns.color_palette("Blues_d", n_colors=len(labels))
    bars = ax.barh(labels, values, color=palette)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_xlabel("Signal matches")
    ax.set_title(f"{technique_name} — Signal Matches by File Extension")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    plt.tight_layout()
    _save(fig, out_dir, "extension_breakdown", fmt, dpi)


def plot_domain_wordcloud(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Word cloud from domain_text_sample fields of detected repos (requires wordcloud package)."""
    try:
        from wordcloud import WordCloud, STOPWORDS as _WC_STOPWORDS
    except ImportError:
        console.print("[yellow]wordcloud not installed — skipping domain_wordcloud (pip install wordcloud)[/]")
        return
    detected = _detected(repo_scores)
    corpus = " ".join(
        r.get("domain_text_sample", "") or ""
        for r in detected
        if r.get("domain_text_sample")
    )
    if not corpus.strip():
        return
    stopwords = set(_WC_STOPWORDS) | {
        "http", "https", "github", "com", "org", "www", "code",
        "test", "testing", "repo", "repository", "project", "use", "used",
    }
    wc = WordCloud(
        width=1200, height=600, background_color="white",
        colormap="viridis", stopwords=stopwords,
        max_words=150, collocations=False,
    ).generate(corpus)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(f"{technique_name} — Domain Word Cloud (Detected Repos)", fontsize=13)
    _save(fig, out_dir, "domain_wordcloud", fmt, dpi)


def plot_domain_dist(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Horizontal bar: inferred domain frequencies for detected repos."""
    detected = _detected(repo_scores)
    domain_counts: Counter = Counter()
    for r in detected:
        for d in (r.get("inferred_domains") or []):
            domain_counts[d] += 1
    if not domain_counts:
        return
    top    = domain_counts.most_common()
    labels = [k.replace("_", " ").title() for k, _ in reversed(top)]
    values = [v for _, v in reversed(top)]

    fig, ax = plt.subplots(figsize=(9, max(4, len(labels) * 0.42)))
    palette = sns.color_palette("Set2", n_colors=len(labels))
    bars = ax.barh(labels, values, color=palette)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_xlabel("Detected repositories")
    ax.set_title(f"{technique_name} — Inferred Application Domain Distribution")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    _save(fig, out_dir, "domain_dist", fmt, dpi)


def plot_pattern_freq(findings, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Horizontal bar: total pattern match frequency."""
    if not findings:
        return
    counts = Counter(f["label"] for f in findings)
    top    = counts.most_common(20)
    labels = [l for l, _ in reversed(top)]
    values = [v for _, v in reversed(top)]

    fig, ax = plt.subplots(figsize=(10, max(5, len(labels) * 0.38)))
    palette = sns.color_palette("Blues_d", n_colors=len(labels))
    ax.barh(labels, values, color=palette)
    ax.set_xlabel("Total matches")
    ax.set_title(f"{technique_name} — Pattern Match Frequency (Top 20)")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    _save(fig, out_dir, "pattern_freq", fmt, dpi)


def plot_detection_spread(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    pass  # content moved into coverage_depth, keyword_density, and test_structure



def _split_outliers(values: list) -> tuple[list, list]:
    """Split values into main distribution and outliers using Tukey fence (Q3 + 1.5*IQR)."""
    if len(values) < 4:
        return list(values), []
    sorted_v = sorted(values)
    n   = len(sorted_v)
    q1  = sorted_v[n // 4]
    q3  = sorted_v[(3 * n) // 4]
    iqr = q3 - q1
    fence = q3 + 1.5 * iqr
    return [v for v in values if v <= fence], [v for v in values if v > fence]


def plot_coverage_depth(findings, repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Histogram: files-with-signals per detected repo (outliers annotated separately)."""
    if not findings or not repo_scores:
        return
    detected_repos = {r["repo"] for r in repo_scores if r.get("score", 0) > 0}
    files_per_repo: dict = defaultdict(set)
    for f in (findings or []):
        if f.get("repo") in detected_repos:
            files_per_repo[f.get("repo")].add(f.get("file", ""))
    if not files_per_repo:
        for r in repo_scores:
            if r.get("score", 0) > 0 and r.get("technique_files", 0) > 0:
                for i in range(int(r.get("technique_files", 0))):
                    files_per_repo[r["repo"]].add(f"file_{i}")
    if not files_per_repo:
        return
    counts = [len(v) for v in files_per_repo.values()]
    main, outliers = _split_outliers(counts)

    fig, ax = plt.subplots(figsize=(9, 5))
    if main:
        max_val = max(main)
        bins = list(range(1, max_val + 2))
        ax.hist(main, bins=bins, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
        if outliers:
            ax.text(0.98, 0.96, f"+{len(outliers)} outliers (up to {max(outliers):,})",
                    transform=ax.transAxes, ha="right", va="top", fontsize=9, color="#e15759")
    ax.set_xlabel("Files with technique signals per repository")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Signal Coverage Depth")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    _save(fig, out_dir, "coverage_depth", fmt, dpi)


def plot_keyword_density(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Histogram: average technique mentions per technique-file (outliers annotated separately)."""
    detected = _detected(repo_scores)
    values = [r["avg_mentions_per_technique_file"] for r in detected
              if r.get("avg_mentions_per_technique_file", 0) > 0]
    if not values:
        return
    main, outliers = _split_outliers(values)
    fig, ax = plt.subplots(figsize=(9, 5))
    plot_vals = main if main else values
    ax.hist(plot_vals, bins=30, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
    mean_v = sum(plot_vals) / len(plot_vals)
    ax.axvline(mean_v, color="#e15759", linestyle="--", linewidth=1.5, label=f"Mean = {mean_v:.1f}")
    if outliers:
        ax.text(0.98, 0.96, f"+{len(outliers)} outliers (up to {max(outliers):.0f})",
                transform=ax.transAxes, ha="right", va="top", fontsize=9, color="#e15759")
    ax.set_xlabel("Average mentions per technique-containing file")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Keyword Density per Technique File")
    ax.legend(fontsize=9)
    _save(fig, out_dir, "keyword_density", fmt, dpi)


def _classify_test_file(path: str) -> str:
    """Classify a file path into a test-infrastructure category."""
    p = path.lower().replace("\\", "/")
    segs = p.split("/")
    n    = segs[-1]

    # Dedicated test case file — named like a test
    test_case = (
        (n.startswith("test_") and "." in n) or
        n.endswith(("_test.py",  "_test.rb",   "_test.go", "_test.rs",
                    "_test.cpp", "_test.c",     "_test.js", "_test.ts")) or
        n.endswith(("test.java", "tests.java", "test.kt",  "tests.kt")) or
        n.endswith(("_spec.rb",  "_spec.js",   "_spec.ts",
                    ".spec.js",  ".spec.ts",   ".test.js", ".test.ts")) or
        "testcase" in n or "testsuit" in n
    )
    if test_case:
        return "Test case files"

    # Test infrastructure — conftest, fixtures, helpers
    infra = (
        "conftest" in n or
        "fixture"  in n or
        ("helper"  in n and any(s in ("tests", "test", "spec") for s in segs)) or
        ("setup"   in n and any(s in ("tests", "test", "spec") for s in segs))
    )
    if infra:
        return "Test fixtures / setup"

    # Test suite directory (not individually named as a test file)
    in_test_dir = any(s in ("tests", "test", "spec", "__tests__", "__test__") for s in segs[:-1])
    if in_test_dir:
        return "Test suite directory"

    return "Source / non-test"


def plot_test_structure(findings, repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    pass  # removed — "signal location in test infrastructure" section dropped

def plot_project_metadata(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Three-panel: stars, repo age, and total files — detected vs not-detected."""
    if not repo_scores:
        return
    detected = _detected(repo_scores)
    not_det  = [r for r in repo_scores if r.get("score", 0) == 0]

    now_year = 2026
    det_stars = [r.get("stars", 0) for r in detected]
    not_stars = [r.get("stars", 0) for r in not_det]
    det_age   = [now_year - int(r["created_at"][:4]) for r in detected
                 if (r.get("created_at") or "")[:4].isdigit()]
    not_age   = [now_year - int(r["created_at"][:4]) for r in not_det
                 if (r.get("created_at") or "")[:4].isdigit()]
    det_files = [r.get("total_files_scanned", 0) for r in detected if r.get("total_files_scanned", 0) > 0]
    not_files = [r.get("total_files_scanned", 0) for r in not_det  if r.get("total_files_scanned", 0) > 0]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    panels = [
        (axes[0], det_stars, not_stars, "Stars",       "Stars (log scale)"),
        (axes[1], det_age,   not_age,   "Age (years)", "Repo age (years)"),
        (axes[2], det_files, not_files, "Total files", "Files scanned (log scale)"),
    ]
    for ax, det_v, not_v, title, ylabel in panels:
        data_to_plot, tick_labels = [], []
        if det_v:
            data_to_plot.append(det_v)
            tick_labels.append(f"Detected\n(n={len(det_v):,})")
        if not_v:
            data_to_plot.append(not_v)
            tick_labels.append(f"Not Detected\n(n={len(not_v):,})")
        if data_to_plot:
            bp = ax.boxplot(data_to_plot, tick_labels=tick_labels, patch_artist=True, showfliers=False)
            for patch, color in zip(bp["boxes"], [PRIMARY_COLOR, "#bdbdbd"]):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)
            if title != "Age (years)" and any(v > 0 for vals in data_to_plot for v in vals):
                ax.set_yscale("log")
            ax.set_ylabel(ylabel)
            ax.set_title(title)

    fig.suptitle(f"{technique_name} — Project Metadata: Detected vs Not Detected", fontweight="bold")
    plt.tight_layout()
    _save(fig, out_dir, "project_metadata", fmt, dpi)


def plot_first_technique_commit_year(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Histogram: year of first technique commit per detected repo."""
    detected = _detected(repo_scores)
    years = []
    for r in detected:
        fd = r.get("first_technique_commit_date", "")
        if fd and len(fd) >= 4 and fd[:4].isdigit():
            years.append(int(fd[:4]))
    if not years:
        return
    min_y = max(min(years) - 1, 2008)
    max_y = min(max(years) + 1, 2026)
    bins  = list(range(min_y, max_y + 2))
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(years, bins=bins, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.4)
    ax.set_xlabel("Year")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — First Technique Commit Year (n={len(years):,})")
    ax.tick_params(axis="x", rotation=45)
    _save(fig, out_dir, "commit_first_year", fmt, dpi)


def plot_last_technique_commit_year(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Histogram: year of last technique commit per detected repo."""
    detected = _detected(repo_scores)
    years = []
    for r in detected:
        ld = r.get("last_technique_commit_date", "")
        if ld and len(ld) >= 4 and ld[:4].isdigit():
            years.append(int(ld[:4]))
    if not years:
        return
    min_y = max(min(years) - 1, 2008)
    max_y = min(max(years) + 1, 2026)
    bins  = list(range(min_y, max_y + 2))
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(years, bins=bins, color=SECONDARY_COLOR, edgecolor="white", linewidth=0.4)
    ax.set_xlabel("Year")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Last Technique Commit Year (n={len(years):,})")
    ax.tick_params(axis="x", rotation=45)
    _save(fig, out_dir, "commit_last_year", fmt, dpi)


def plot_domain_activity_over_time(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Multi-line chart: detected repos created per year, broken down by top domains."""
    detected = _detected(repo_scores)
    all_dom: Counter = Counter()
    for r in detected:
        for d in (r.get("inferred_domains") or []):
            all_dom[d] += 1
    top_domains = [d for d, _ in all_dom.most_common(6)]
    if not top_domains:
        return

    domain_by_year: dict = defaultdict(Counter)
    all_years: set = set()
    for r in detected:
        created = (r.get("created_at") or "")[:4]
        if not created or not created.isdigit():
            continue
        yr = int(created)
        if 2010 <= yr <= 2026:
            all_years.add(yr)
            for d in (r.get("inferred_domains") or []):
                if d in top_domains:
                    domain_by_year[d][yr] += 1
    if not all_years:
        return

    years   = sorted(all_years)
    palette = sns.color_palette("Set2", n_colors=len(top_domains))
    fig, ax = plt.subplots(figsize=(12, 5))
    for i, domain in enumerate(top_domains):
        counts = [domain_by_year[domain].get(y, 0) for y in years]
        ax.plot(years, counts, marker="o", markersize=4, linewidth=1.8,
                label=domain.replace("_", " ").title(), color=palette[i])
    ax.set_xlabel("Repository creation year")
    ax.set_ylabel("Detected repositories")
    ax.set_title(f"{technique_name} — Detected Repos by Domain Over Time (Top 6 Domains)")
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    ax.tick_params(axis="x", rotation=45)
    ax.legend(fontsize=9, bbox_to_anchor=(1.01, 1), loc="upper left")
    plt.tight_layout()
    _save(fig, out_dir, "domain_activity_over_time", fmt, dpi)


def plot_project_life_year(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Line chart: technique commits by year of repo life (1 = first year after creation)."""
    detected = _detected(repo_scores)
    life_counts: Counter = Counter()
    for r in detected:
        created = (r.get("created_at") or "")[:4]
        if not created or not created.isdigit():
            continue
        created_year = int(created)
        for dt in (r.get("technique_commit_dates") or []):
            if isinstance(dt, str) and len(dt) >= 4 and dt[:4].isdigit():
                yol = int(dt[:4]) - created_year + 1
                if 1 <= yol <= 20:
                    life_counts[yol] += 1
    if not life_counts:
        return
    max_yr     = min(max(life_counts.keys()), 20)
    life_years = list(range(1, max_yr + 1))
    counts     = [life_counts.get(y, 0) for y in life_years]

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(life_years, counts, color=PRIMARY_COLOR, linewidth=2, marker="o", markersize=5)
    ax.fill_between(life_years, counts, alpha=0.15, color=PRIMARY_COLOR)
    ax.set_xlabel("Year of repository life (1 = first year after creation)")
    ax.set_ylabel("Technique commits (across all detected repos)")
    ax.set_title(f"{technique_name} — Technique Commits by Year of Repository Life")
    if max_yr <= 15:
        ax.set_xticks(life_years)
        ax.set_xticklabels([f"Yr {y}" for y in life_years], rotation=45)
    else:
        tick_positions = list(range(1, max_yr + 1, 2))
        ax.set_xticks(tick_positions)
        ax.set_xticklabels([f"Yr {y}" for y in tick_positions], rotation=45)
    _save(fig, out_dir, "project_life_year", fmt, dpi)


def plot_technique_commit_timeline(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Line chart: total technique commits per year across all detected repos."""
    detected = _detected(repo_scores)
    year_counts: Counter = Counter()
    for r in detected:
        for dt in (r.get("technique_commit_dates") or []):
            if isinstance(dt, str) and len(dt) >= 4 and dt[:4].isdigit():
                y = int(dt[:4])
                if 2005 <= y <= 2026:
                    year_counts[y] += 1
    if not year_counts:
        return

    years  = sorted(year_counts)
    counts = [year_counts[y] for y in years]

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(years, counts, color=PRIMARY_COLOR, linewidth=2, marker="o", markersize=5)
    ax.fill_between(years, counts, alpha=0.15, color=PRIMARY_COLOR)
    ax.set_xlabel("Year")
    ax.set_ylabel("Technique commits (across all detected repos)")
    ax.set_title(f"{technique_name} — Technique Commit Activity Over Time")
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    ax.tick_params(axis="x", rotation=45)
    _save(fig, out_dir, "commit_timeline", fmt, dpi)


def plot_commit_ratio_dist(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Histogram: technique commit ratio for detected repos."""
    detected = _detected(repo_scores)
    values = [r["technique_commit_ratio"] for r in detected
              if r.get("technique_commit_ratio") is not None
              and r.get("total_commits_sampled", 0) > 0]
    if not values:
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(values, bins=30, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0, decimals=0))
    mean_v = sum(values) / len(values)
    ax.axvline(mean_v, color="#e15759", linestyle="--", linewidth=1.5, label=f"Mean = {mean_v*100:.1f}%")
    ax.set_xlabel("% of sampled commits mentioning technique")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Technique Commit Ratio Distribution")
    ax.legend(fontsize=9)
    _save(fig, out_dir, "commit_ratio_dist", fmt, dpi)


def plot_commit_span(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Histogram: span in years from first to last technique commit."""
    detected = _detected(repo_scores)
    values = [r.get("technique_commit_span_days", 0) / 365.25 for r in detected
              if r.get("technique_commit_span_days", 0) > 0]
    if not values:
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(values, bins=20, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
    med = statistics.median(values)
    ax.axvline(med, color="#e15759", linestyle="--", linewidth=1.5, label=f"Median = {med:.1f} yrs")
    ax.set_xlabel("Technique commit activity span (years, first → last)")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Technique Commit Span Distribution")
    ax.legend(fontsize=9)
    _save(fig, out_dir, "commit_span", fmt, dpi)


# ===========================================================================
# SEARCH / PIPELINE CHARTS
# ===========================================================================

def plot_query_hits(summary, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    if not summary:
        return
    queries = summary.get("queries", [])
    if not queries:
        return
    df = pd.DataFrame(queries)
    df = df[df["hits"] > 0].copy()
    df["surface_query"] = df["type"].str.upper() + ": " + df["query"].str[:50]
    df = df.sort_values("hits", ascending=True)

    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.28)))
    ax.barh(df["surface_query"], df["hits"], color=SECONDARY_COLOR)
    ax.set_xlabel("Total hits")
    ax.set_title(f"{technique_name} — GitHub Search Hit Counts by Query")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    _save(fig, out_dir, "query_hits", fmt, dpi)


def plot_surface_breakdown(repo_scores, summary, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Bar: search results per surface using top-level counts from summary.json."""
    if not summary:
        return
    surface_counts = {
        "repo":       summary.get("repos", 0) or 0,
        "code":       summary.get("code_files", 0) or 0,
        "commit":     summary.get("commits", 0) or 0,
        "issue":      summary.get("issues", 0) or 0,
        "pr":         summary.get("prs", 0) or 0,
        "discussion": summary.get("discussions", 0) or 0,
    }
    surface_order = ["code", "repo", "commit", "issue", "pr", "discussion"]
    active = [s for s in surface_order if surface_counts[s] > 0]
    if not active:
        return
    labels = [s.capitalize() for s in active]
    values = [surface_counts[s] for s in active]
    colors = [_SURFACE_COLORS[s] for s in active]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=0.8)
    ax.bar_label(bars, padding=3, fontsize=10)
    ax.set_xlabel("Search surface")
    ylabel = "Distinct results found"
    if len(values) > 1:
        sv = sorted(values, reverse=True)
        if sv[0] > 4 * sv[1]:
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
            ylabel = "Distinct results found (log scale)"
    ax.set_ylabel(ylabel)
    ax.set_title(f"{technique_name} — Search Results per Surface")
    _save(fig, out_dir, "surface_breakdown", fmt, dpi)


# ===========================================================================
# Kept for backward compat (not called from run())
# ===========================================================================

def plot_stars_scatter(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    pass  # removed from pipeline


def plot_author_dist(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    pass  # removed from pipeline


def plot_file_coverage_ratio(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    pass  # replaced by plot_technique_ratios


def plot_query_overlap(repo_scores, out_dir: Path, fmt: str, dpi: int) -> None:
    pass  # removed from pipeline


def plot_commit_timeline(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    pass  # replaced by plot_technique_commit_timeline


def plot_commit_first_last(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    pass  # replaced by plot_first_technique_commit_year + plot_last_technique_commit_year


# ===========================================================================
# Main
# ===========================================================================

def run(out_dir: Path, fmt: str, dpi: int, profile=None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir      = profile.results_dir / "raw"
    analysis_dir = profile.results_dir / "analysis"
    tech         = profile.name if profile else "Technique"

    data = load_all(raw_dir, analysis_dir)
    console.rule(f"[bold blue]Generating plots — {tech}[/]")

    scores   = data["repo_scores"]
    findings = data["findings"]
    summary  = data["summary"]

    # Adoption (RQ1)
    plot_detection_count_hist(scores,                out_dir, fmt, dpi, tech)
    plot_yearly_trend(        scores,                out_dir, fmt, dpi, tech)
    plot_technique_ratios(    scores,                out_dir, fmt, dpi, tech)
    plot_contributor_dist(    scores,                out_dir, fmt, dpi, tech)
    plot_project_metadata(    scores,                out_dir, fmt, dpi, tech)

    # Usage (RQ2) — project role first, then detection distribution, then language/artifact/extension
    plot_project_type_dist(           scores,                out_dir, fmt, dpi, tech)
    plot_coverage_depth(              findings, scores,      out_dir, fmt, dpi, tech)
    plot_keyword_density(             scores,                out_dir, fmt, dpi, tech)
    plot_language_dist(               scores,                out_dir, fmt, dpi, tech)
    plot_artifact_breakdown(          scores,                out_dir, fmt, dpi, tech)
    plot_extension_breakdown(         findings,              out_dir, fmt, dpi, tech)
    plot_domain_dist(                 scores,                out_dir, fmt, dpi, tech)
    plot_domain_wordcloud(            scores,                out_dir, fmt, dpi, tech)
    plot_domain_activity_over_time(   scores,                out_dir, fmt, dpi, tech)
    plot_pattern_freq(                findings,              out_dir, fmt, dpi, tech)

    # Timeline (RQ3)
    plot_technique_commit_timeline(   scores,                out_dir, fmt, dpi, tech)
    plot_first_technique_commit_year( scores,                out_dir, fmt, dpi, tech)
    plot_last_technique_commit_year(  scores,                out_dir, fmt, dpi, tech)
    plot_commit_span(                 scores,                out_dir, fmt, dpi, tech)
    plot_commit_ratio_dist(           scores,                out_dir, fmt, dpi, tech)
    plot_project_life_year(           scores,                out_dir, fmt, dpi, tech)

    # Pipeline / search
    plot_surface_breakdown(   scores, summary,       out_dir, fmt, dpi, tech)
    plot_query_hits(          summary,               out_dir, fmt, dpi, tech)

    console.print(f"\n[bold green]Done.[/]  Plots saved to [dim]{out_dir}[/]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4: generate plots from mining results")
    parser.add_argument("--technique",   required=True)
    parser.add_argument("--output-dir",  type=Path, default=None)
    parser.add_argument("--dpi",         type=int,  default=150)
    parser.add_argument("--format",      choices=["png", "pdf", "svg"], default="png")
    args = parser.parse_args()

    from config import load_technique
    profile = load_technique(args.technique)
    out_dir = args.output_dir or (profile.results_dir / "plots")
    run(out_dir, args.format, args.dpi, profile=profile)


if __name__ == "__main__":
    main()
