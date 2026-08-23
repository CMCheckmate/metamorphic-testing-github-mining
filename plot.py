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
    """Histogram: number of detections (x) vs number of repositories (y)."""
    detected = _detected(repo_scores)
    scores   = [r["score"] for r in detected]
    if not scores:
        return

    max_s = max(scores)
    if max_s <= 25:
        bins = list(range(1, max_s + 2))
    else:
        bins = list(range(1, 21)) + [25, 35, 50, 75, 100, max_s + 1]
        bins = sorted(set(b for b in bins if b <= max_s + 1))

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(scores, bins=bins, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
    mean_v   = sum(scores) / len(scores)
    median_v = sorted(scores)[len(scores) // 2]
    ax.axvline(mean_v,   color="#e15759", linestyle="--", linewidth=1.5, label=f"Mean = {mean_v:.1f}")
    ax.axvline(median_v, color="#4e79a7", linestyle="--", linewidth=1.5, label=f"Median = {median_v:.1f}")
    ax.set_xlabel("Detection count (pattern matches per repository)")
    ax.set_ylabel("Number of repositories")
    ax.set_title(f"{technique_name} — Detection Count Distribution")
    ax.legend(fontsize=9)
    _save(fig, out_dir, "detection_count_hist", fmt, dpi)


def plot_yearly_trend(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Bar chart: all repos by creation year, detected highlighted."""
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
    ax.bar(merged["year"], merged["total"],    color="#d9d9d9", label="Not detected", zorder=2)
    ax.bar(merged["year"], merged["detected"], color=PRIMARY_COLOR, label="Detected",     zorder=3)
    ax.set_xlabel("Repository creation year")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Detected Repos by Creation Year")
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

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    if line_density:
        axes[0].hist(line_density, bins=25, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
        med = statistics.median(line_density)
        axes[0].axvline(med, color="#e15759", linestyle="--", linewidth=1.5, label=f"Median = {med*100:.2f}%")
        axes[0].xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0, decimals=2))
        axes[0].set_xlabel("Technique lines ÷ total lines scanned")
        axes[0].set_ylabel("Repositories")
        axes[0].set_title("Technique Line Density")
        axes[0].legend(fontsize=9)

    if file_ratio:
        axes[1].hist(file_ratio, bins=25, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
        med = statistics.median(file_ratio)
        axes[1].axvline(med, color="#e15759", linestyle="--", linewidth=1.5, label=f"Median = {med*100:.1f}%")
        axes[1].xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0, decimals=0))
        axes[1].set_xlabel("Technique files ÷ total files scanned")
        axes[1].set_ylabel("Repositories")
        axes[1].set_title("Technique File Ratio")
        axes[1].legend(fontsize=9)

    fig.suptitle(f"{technique_name} — Detection Coverage Ratios (Detected Repos)", fontweight="bold")
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
    """Bar chart: top languages by detected repo count."""
    detected = _detected(repo_scores)
    if not detected:
        return
    langs  = Counter(r.get("language") or "Unknown" for r in detected)
    top    = langs.most_common(15)
    labels = [l for l, _ in top]
    values = [v for _, v in top]

    fig, ax = plt.subplots(figsize=(9, 5))
    palette = sns.color_palette("viridis", n_colors=len(labels))
    bars = ax.bar(labels, values, color=palette, edgecolor="white", linewidth=0.8)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_ylabel("Detected repositories")
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



def plot_coverage_depth(findings, repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Bar: distribution of files-with-signals per detected repo."""
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
    bins   = [(1, 1, "1"), (2, 2, "2"), (3, 5, "3–5"), (6, 10, "6–10"),
              (11, 20, "11–20"), (21, 10**9, ">20")]
    labels = [l for _, _, l in bins]
    values = [sum(1 for c in counts if lo <= c <= hi) for lo, hi, _ in bins]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, values, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.8)
    ax.bar_label(bars, padding=3, fontsize=10)
    ax.set_xlabel("Files with technique signals per repository")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — Signal Coverage Depth")
    _save(fig, out_dir, "coverage_depth", fmt, dpi)


def plot_keyword_density(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Histogram: average technique mentions per technique-file."""
    detected = _detected(repo_scores)
    values = [r["avg_mentions_per_technique_file"] for r in detected
              if r.get("avg_mentions_per_technique_file", 0) > 0]
    if not values:
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(values, bins=30, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
    mean_v = sum(values) / len(values)
    ax.axvline(mean_v, color="#e15759", linestyle="--", linewidth=1.5, label=f"Mean = {mean_v:.1f}")
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
    """Two-panel: % of detected repos and % of signals in each test-infrastructure category."""
    if not findings or not repo_scores:
        return
    detected_repos = {r["repo"] for r in repo_scores if r.get("score", 0) > 0}
    n_det = len(detected_repos)
    if not n_det:
        return

    repo_cats: dict = defaultdict(set)   # repo → set of categories
    sig_counts: Counter = Counter()      # category → total signal count

    for f in findings:
        if f.get("repo") not in detected_repos:
            continue
        cat = _classify_test_file(f.get("file", ""))
        repo_cats[f["repo"]].add(cat)
        sig_counts[cat] += 1

    cats   = ["Test case files", "Test suite directory", "Test fixtures / setup", "Source / non-test"]
    colors = [PRIMARY_COLOR, "#4472c4", "#f0ad3a", "#bdbdbd"]

    repo_pcts = [sum(1 for sets in repo_cats.values() if c in sets) / n_det * 100 for c in cats]
    total_sig = max(sum(sig_counts.values()), 1)
    sig_pcts  = [sig_counts[c] / total_sig * 100 for c in cats]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    for ax, vals, title, ylabel in [
        (axes[0], repo_pcts, "% of detected repos with signals here",  "% of detected repos"),
        (axes[1], sig_pcts,  "% of total signals in each category",    "% of signal matches"),
    ]:
        bars = ax.bar(cats, vals, color=colors, edgecolor="white", linewidth=0.7)
        ax.bar_label(bars, fmt=lambda v: f"{v:.0f}%", padding=3, fontsize=9)
        ax.yaxis.set_major_formatter(mticker.PercentFormatter())
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels(cats, rotation=15, ha="right", fontsize=9)

    fig.suptitle(f"{technique_name} — Technique Signal Location in Test Infrastructure", fontweight="bold")
    plt.tight_layout()
    _save(fig, out_dir, "test_structure", fmt, dpi)

def plot_commit_first_last(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Overlaid histograms: first and last technique commit year per detected repo."""
    detected = _detected(repo_scores)
    first_years, last_years = [], []
    for r in detected:
        fd = r.get("first_technique_commit_date", "")
        ld = r.get("last_technique_commit_date", "")
        if fd and len(fd) >= 4 and fd[:4].isdigit():
            first_years.append(int(fd[:4]))
        if ld and len(ld) >= 4 and ld[:4].isdigit():
            last_years.append(int(ld[:4]))
    if not first_years and not last_years:
        return

    all_years = first_years + last_years
    min_y = max(min(all_years) - 1, 2008)
    max_y = min(max(all_years) + 1, 2026)
    bins  = list(range(min_y, max_y + 2))

    fig, ax = plt.subplots(figsize=(10, 5))
    if first_years:
        ax.hist(first_years, bins=bins, alpha=0.65, color=PRIMARY_COLOR,
                label=f"First commit (n={len(first_years):,})", edgecolor="white", linewidth=0.4)
    if last_years:
        ax.hist(last_years, bins=bins, alpha=0.55, color=SECONDARY_COLOR,
                label=f"Last commit (n={len(last_years):,})", edgecolor="white", linewidth=0.4)
    ax.set_xlabel("Year")
    ax.set_ylabel("Repositories")
    ax.set_title(f"{technique_name} — First and Last Technique Commit Year")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(fontsize=9)
    _save(fig, out_dir, "commit_first_last", fmt, dpi)


def plot_technique_commit_timeline(repo_scores, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Bar chart: total technique commits per year across all detected repos."""
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
    ax.bar(years, counts, color=PRIMARY_COLOR, edgecolor="white", linewidth=0.5)
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
    if not repo_scores:
        return
    raw_to_surface = _build_raw_to_surface(summary)
    surface_repo_sets: dict = defaultdict(set)
    for r in repo_scores:
        for entry in r.get("found_by_queries", []):
            s = _query_surface(entry)
            if s == "discussion":
                s = raw_to_surface.get(entry, "discussion")
            surface_repo_sets[s].add(r["repo"])
    if not surface_repo_sets:
        return
    surface_order = ["code", "repo", "commit", "issue", "pr", "discussion"]
    labels = [s.capitalize() for s in surface_order if s in surface_repo_sets]
    values = [len(surface_repo_sets[s]) for s in surface_order if s in surface_repo_sets]
    colors = [_SURFACE_COLORS[s] for s in surface_order if s in surface_repo_sets]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=0.8)
    ax.bar_label(bars, padding=3, fontsize=10)
    ax.set_xlabel("Search surface")
    ax.set_ylabel("Distinct repositories found")
    ax.set_title(f"{technique_name} — Repositories Found per Search Surface")
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
    pass  # replaced by plot_commit_first_last


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

    # Usage (RQ2) — project role first, then detection distribution, then language/artifact/extension
    plot_project_type_dist(   scores,                out_dir, fmt, dpi, tech)
    plot_coverage_depth(      findings, scores,      out_dir, fmt, dpi, tech)
    plot_keyword_density(     scores,                out_dir, fmt, dpi, tech)
    plot_test_structure(      findings, scores,      out_dir, fmt, dpi, tech)
    plot_language_dist(       scores,                out_dir, fmt, dpi, tech)
    plot_artifact_breakdown(  scores,                out_dir, fmt, dpi, tech)
    plot_extension_breakdown( findings,              out_dir, fmt, dpi, tech)
    plot_domain_dist(         scores,                out_dir, fmt, dpi, tech)
    plot_pattern_freq(        findings,              out_dir, fmt, dpi, tech)

    # Timeline (RQ3)
    plot_technique_commit_timeline(scores,                out_dir, fmt, dpi, tech)
    plot_commit_first_last(        scores,                out_dir, fmt, dpi, tech)
    plot_commit_span(              scores,                out_dir, fmt, dpi, tech)
    plot_commit_ratio_dist(        scores,                out_dir, fmt, dpi, tech)

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
