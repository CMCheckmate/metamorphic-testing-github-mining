"""
Comparative Analysis — combine.py
===================================
Reads all completed technique analyses and produces a cross-technique
comparative report covering all RQ1/2/3 metrics.

Outputs:
  results/combined/comparative_report.md
  results/combined/plots/

Usage:
    python combine.py
    python combine.py --techniques metamorphic_testing fuzzing property_based_testing
    python combine.py --format pdf --dpi 300
"""

import argparse
import json
import os
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import seaborn as sns
from rich.console import Console

console = Console()

BASE_DIR     = Path(__file__).parent.resolve()
RESULTS_DIR  = BASE_DIR / "results"
COMBINED_DIR = RESULTS_DIR / "combined"

_FALLBACK_COLOURS = [
    "#1b5e20", "#1565c0", "#b71c1c", "#e65100", "#6a1b9a",
    "#00695c", "#4e342e", "#37474f",
]

_PLOT_STYLE = {
    "figure.facecolor":  "white",
    "axes.facecolor":    "white",
    "axes.grid":         True,
    "grid.alpha":        0.35,
    "grid.linestyle":    "--",
    "axes.spines.top":   False,
    "axes.spines.right": False,
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _load_yaml(yaml_path: Path) -> dict:
    try:
        import yaml
        with open(yaml_path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def discover_techniques(results_dir: Path, slug_filter=None) -> list:
    techniques = []
    colour_idx = 0
    for subdir in sorted(results_dir.iterdir()):
        if not subdir.is_dir() or subdir.name == "combined":
            continue
        if slug_filter and subdir.name not in slug_filter:
            continue
        scores_path = subdir / "analysis" / "repo_scores.json"
        if not scores_path.exists():
            continue
        scores = _load_json(scores_path)
        if not scores:
            continue
        name       = subdir.name.replace("_", " ").title()
        short_name = subdir.name.upper()
        colour     = _FALLBACK_COLOURS[colour_idx % len(_FALLBACK_COLOURS)]
        for yp in [BASE_DIR / "techniques" / f"{subdir.name}.yaml"]:
            if yp.exists():
                data       = _load_yaml(yp)
                name       = data.get("name",       name)
                short_name = data.get("short_name", short_name)
                colour     = data.get("color",      colour)
                break
        techniques.append({
            "slug":       subdir.name,
            "name":       name,
            "short_name": short_name,
            "color":      colour,
            "scores":     scores,
            "findings":   _load_json(subdir / "analysis" / "findings.json") or [],
            "summary":    _load_json(subdir / "raw" / "summary.json"),
        })
        colour_idx += 1
    return techniques


# ---------------------------------------------------------------------------
# Metric extraction helpers
# ---------------------------------------------------------------------------

def _detected(scores):
    return [r for r in (scores or []) if r.get("score", 0) > 0]


def _det_counts(scores) -> list:
    return [r["score"] for r in scores if r.get("score", 0) > 0]


def _yearly_detected(scores) -> dict:
    c: Counter = Counter()
    for r in scores:
        d = (r.get("created_at") or "")[:4]
        if d.isdigit() and int(d) >= 2010 and r.get("score", 0) > 0:
            c[int(d)] += 1
    return dict(c)


def _lang_detected(scores) -> Counter:
    c: Counter = Counter()
    for r in _detected(scores):
        c[r.get("language") or "Unknown"] += 1
    return c


def _project_type_dist(scores) -> Counter:
    return Counter(r.get("project_type", "unknown") for r in _detected(scores))


def _domain_dist(scores) -> Counter:
    c: Counter = Counter()
    for r in _detected(scores):
        for d in (r.get("inferred_domains") or []):
            c[d] += 1
    return c


def _file_ratio_vals(scores) -> list:
    return [r["technique_file_ratio"] for r in _detected(scores)
            if r.get("technique_file_ratio") is not None and r.get("technique_file_ratio", 0) > 0]


def _line_density_vals(scores) -> list:
    return [r["technique_line_density"] for r in _detected(scores)
            if r.get("technique_line_density") is not None and r.get("technique_line_density", 0) > 0]


def _commit_ratio_vals(scores) -> list:
    return [r["technique_commit_ratio"] * 100 for r in _detected(scores)
            if r.get("technique_commit_ratio") is not None
            and r.get("total_commits_sampled", 0) > 0]


def _commit_span_vals(scores) -> list:
    return [r.get("technique_commit_span_days", 0) / 365.25 for r in _detected(scores)
            if r.get("technique_commit_span_days", 0) > 0]


def _contributor_vals(scores) -> list:
    return [r.get("contributor_count_git", 0) for r in _detected(scores)
            if r.get("contributor_count_git", 0) > 0]


def _total_lines_vals(scores) -> list:
    return [r.get("total_lines_scanned", 0) for r in _detected(scores)
            if r.get("total_lines_scanned", 0) > 0]


def _total_files_vals(scores) -> list:
    return [r.get("total_files_scanned", 0) for r in _detected(scores)
            if r.get("total_files_scanned", 0) > 0]


def _avg_mentions_vals(scores) -> list:
    return [r.get("avg_mentions_per_technique_file", 0) for r in _detected(scores)
            if r.get("avg_mentions_per_technique_file", 0) > 0]


def _pat_breadth_vals(scores) -> list:
    return [len(r.get("patterns_matched", [])) for r in _detected(scores)]


def _concentration_vals(scores) -> list:
    return [r.get("max_mentions_in_file", 0) / max(r.get("score", 1), 1)
            for r in _detected(scores) if r.get("score", 0) > 0]


def _first_commit_years(scores) -> list:
    out = []
    for r in _detected(scores):
        d = r.get("first_technique_commit_date", "")
        if d and len(d) >= 4 and d[:4].isdigit():
            y = int(d[:4])
            if 2005 <= y <= 2026:
                out.append(y)
    return out


def _last_commit_years(scores) -> list:
    out = []
    for r in _detected(scores):
        d = r.get("last_technique_commit_date", "")
        if d and len(d) >= 4 and d[:4].isdigit():
            y = int(d[:4])
            if 2005 <= y <= 2026:
                out.append(y)
    return out


def _extension_dist(findings) -> Counter:
    c: Counter = Counter()
    for f in (findings or []):
        fname = f.get("file", "")
        if fname:
            dot = fname.rfind(".")
            ext = fname[dot:].lower() if dot >= 0 else "(none)"
            c[ext] += 1
    return c


def _artifact_pct(scores) -> dict:
    totals: Counter = Counter()
    for r in _detected(scores):
        for atype, cnt in (r.get("artifact_breakdown") or {}).items():
            totals[atype] += cnt
    total = sum(totals.values()) or 1
    return {k: v / total * 100 for k, v in totals.items()}


def _det_stats(scores) -> dict:
    n    = len(scores)
    det  = len(_detected(scores))
    cnts = _det_counts(scores)
    return {
        "total":    n,
        "detected": det,
        "rate":     det / n * 100 if n else 0.0,
        "median":   statistics.median(cnts) if cnts else 0,
        "mean":     statistics.mean(cnts)   if cnts else 0.0,
    }


def _pct(v: float) -> str:
    return f"{v:.1f}%"


def _img(plots_rel: str, name: str, fmt: str, caption: str) -> str:
    return f"![{caption}]({plots_rel}/{name}.{fmt})\n*{caption}*\n"


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _save(fig, out_dir: Path, name: str, fmt: str, dpi: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{name}.{fmt}", dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def _violin_or_box(ax, data_list, names, colours, ylabel, title, use_violin=True, pct_fmt=False):
    """Helper: draw violin or box plot per technique."""
    rows = []
    for name, vals in zip(names, data_list):
        for v in vals:
            rows.append({"Technique": name, "val": v})
    if not rows:
        return
    df  = pd.DataFrame(rows)
    pal = {n: c for n, c in zip(names, colours)}
    if use_violin and sum(len(v) for v in data_list) > 10:
        sns.violinplot(data=df, x="Technique", y="val",
                       hue="Technique", order=names, palette=pal,
                       ax=ax, cut=0, inner="box", legend=False)
    else:
        sns.boxplot(data=df, x="Technique", y="val",
                    hue="Technique", order=names, palette=pal, ax=ax,
                    flierprops=dict(marker=".", markersize=4, alpha=0.5), legend=False)
    if pct_fmt:
        ax.yaxis.set_major_formatter(ticker.PercentFormatter())
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight="bold")


# ---------------------------------------------------------------------------
# Comparative plots — Adoption (RQ1)
# ---------------------------------------------------------------------------

def plot_adoption_rates(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    with plt.style.context(_PLOT_STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(max(10, len(techniques) * 2), 5))
        names   = [t["short_name"] for t in techniques]
        rates   = [_det_stats(t["scores"])["rate"]     for t in techniques]
        counts  = [_det_stats(t["scores"])["detected"] for t in techniques]
        colours = [t["color"] for t in techniques]

        bars = axes[0].bar(names, rates, color=colours, width=0.55, zorder=3)
        for bar, rate in zip(bars, rates):
            axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                         f"{rate:.1f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")
        axes[0].set_ylabel("Detection rate (%)")
        axes[0].set_title("Detection Rate", fontweight="bold")
        axes[0].yaxis.set_major_formatter(ticker.PercentFormatter())
        axes[0].set_ylim(0, max(rates) * 1.25 + 3 if rates else 10)

        bars2 = axes[1].bar(names, counts, color=colours, width=0.55, zorder=3)
        for bar, cnt in zip(bars2, counts):
            axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                         f"{cnt:,}", ha="center", va="bottom", fontsize=10, fontweight="bold")
        axes[1].set_ylabel("Detected repositories")
        axes[1].set_title("Detected Repository Count", fontweight="bold")

        fig.suptitle("Adoption by Testing Technique", fontsize=13, fontweight="bold")
        fig.tight_layout()
    _save(fig, out_dir, "adoption_overview", fmt, dpi)


def plot_detection_depth(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    data    = [(_det_counts(t["scores"]) or [0]) for t in techniques]
    names   = [t["short_name"] for t in techniques]
    colours = [t["color"] for t in techniques]
    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(max(8, len(techniques) * 1.6), 5))
        bp = ax.boxplot(data, patch_artist=True, notch=False, showfliers=True, widths=0.5)
        for patch, colour in zip(bp["boxes"], colours):
            patch.set_facecolor(colour); patch.set_alpha(0.7)
        ax.set_xticklabels(names)
        ax.set_yscale("log")
        ax.set_ylabel("Detection count (log scale)")
        ax.set_title("Detection Count Distribution — Detected Repos", fontweight="bold")
        fig.tight_layout()
    _save(fig, out_dir, "detection_depth", fmt, dpi)


def plot_size_comparison(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    pass  # removed — repository scale not shown before classification


def plot_contributor_comparison(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Bar: median contributor count per technique (detected repos)."""
    names   = [t["short_name"] for t in techniques]
    colours = [t["color"] for t in techniques]
    medians = []
    for t in techniques:
        vals = _contributor_vals(t["scores"])
        medians.append(statistics.median(vals) if vals else 0)

    if not any(medians):
        return

    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(max(8, len(techniques) * 1.8), 5))
        bars = ax.bar(names, medians, color=colours, width=0.55, zorder=3)
        for bar, val in zip(bars, medians):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                    f"{val:.0f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylabel("Median unique contributors (git log)")
        ax.set_title("Contributor Count — Median per Technique (Detected Repos)", fontweight="bold")
        fig.tight_layout()
    _save(fig, out_dir, "contributor_comparison", fmt, dpi)


def plot_technique_ratios(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Two-panel bar: median technique line density and file ratio per technique."""
    names   = [t["short_name"] for t in techniques]
    colours = [t["color"] for t in techniques]

    ld_medians = []
    fr_medians = []
    for t in techniques:
        ld = _line_density_vals(t["scores"])
        fr = _file_ratio_vals(t["scores"])
        ld_medians.append(statistics.median(ld) * 100 if ld else 0)
        fr_medians.append(statistics.median(fr) * 100 if fr else 0)

    if not any(ld_medians) and not any(fr_medians):
        return

    with plt.style.context(_PLOT_STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(max(10, len(techniques) * 2.5), 5))
        for ax, medians, title, ylabel in [
            (axes[0], ld_medians, "Technique Line Density", "Median technique lines ÷ total lines (%)"),
            (axes[1], fr_medians, "Technique File Ratio",   "Median technique files ÷ total files (%)"),
        ]:
            bars = ax.bar(names, medians, color=colours, width=0.55, zorder=3)
            for bar, val in zip(bars, medians):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.001,
                        f"{val:.2f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")
            ax.yaxis.set_major_formatter(ticker.PercentFormatter())
            ax.set_ylabel(ylabel)
            ax.set_title(title, fontweight="bold")
        fig.suptitle("Detection Coverage Ratios — Median per Technique", fontsize=12, fontweight="bold")
        fig.tight_layout()
    _save(fig, out_dir, "technique_ratios", fmt, dpi)


# ---------------------------------------------------------------------------
# Comparative plots — Usage (RQ2)
# ---------------------------------------------------------------------------

def plot_language_comparison(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Grouped horizontal bar: top languages per technique (% of detected repos)."""
    all_lang: Counter = Counter()
    for t in techniques:
        all_lang.update(_lang_detected(t["scores"]))
    top_langs = [l for l, _ in all_lang.most_common(10)]
    if not top_langs:
        return

    names   = [t["short_name"] for t in techniques]
    colours = [t["color"] for t in techniques]
    n_tech  = len(techniques)
    x       = np.arange(len(top_langs))
    w       = 0.8 / n_tech

    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(max(12, len(top_langs) * 1.4), max(5, n_tech * 1.5)))
        for idx, (t, col) in enumerate(zip(techniques, colours)):
            counts = _lang_detected(t["scores"])
            total  = max(len(_detected(t["scores"])), 1)
            pcts   = [counts.get(lang, 0) / total * 100 for lang in top_langs]
            offset = (idx - n_tech / 2 + 0.5) * w
            ax.bar(x + offset, pcts, w * 0.88, label=t["short_name"], color=col, zorder=3)

        ax.set_xticks(x)
        ax.set_xticklabels(top_langs, rotation=30, ha="right")
        ax.yaxis.set_major_formatter(ticker.PercentFormatter())
        ax.set_ylabel("% of detected repos")
        ax.set_title("Language Distribution by Technique (top 10 languages)", fontweight="bold")
        ax.legend(title="Technique", fontsize=9)
        fig.tight_layout()
    _save(fig, out_dir, "language_comparison", fmt, dpi)


def plot_project_type_comparison(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    type_order   = ["general_usage", "framework", "mixed", "research_artifact", "unknown"]
    type_colours = {"general_usage": "#1a6e3c", "framework": "#4472c4", "mixed": "#f0ad3a",
                    "research_artifact": "#d62728", "unknown": "#bdbdbd"}
    type_display = {"general_usage": "Actual Usage", "framework": "Framework",
                    "mixed": "Mixed", "research_artifact": "Research Artifact", "unknown": "Unknown"}
    all_types: set = set()
    for t in techniques:
        all_types |= set(_project_type_dist(t["scores"]).keys())
    present = [tp for tp in type_order if tp in all_types]
    if not present:
        return
    names = [t["short_name"] for t in techniques]
    x = np.arange(len(names))
    w = 0.8 / len(present)
    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(max(10, len(techniques) * 1.8), 5))
        for idx, pt in enumerate(present):
            dists  = [_project_type_dist(t["scores"]) for t in techniques]
            totals = [max(sum(d.values()), 1) for d in dists]
            pcts   = [d.get(pt, 0) / tot * 100 for d, tot in zip(dists, totals)]
            ax.bar(x + (idx - len(present)/2 + 0.5) * w, pcts, w * 0.9,
                   label=type_display.get(pt, pt),
                   color=type_colours.get(pt, "#aaa"), zorder=3)
        ax.set_xticks(x); ax.set_xticklabels(names)
        ax.yaxis.set_major_formatter(ticker.PercentFormatter())
        ax.set_ylabel("% of detected repos")
        ax.set_title("Project Role Distribution by Technique", fontweight="bold")
        ax.legend(fontsize=9); fig.tight_layout()
    _save(fig, out_dir, "project_type_comparison", fmt, dpi)


def plot_artifact_comparison(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Stacked horizontal bar per technique showing artifact type split."""
    art_order  = ["test_code", "source_code", "documentation", "config", "other"]
    art_colors = {"test_code": "#2166ac", "source_code": "#4dac26",
                  "documentation": "#d6604d", "config": "#f4a582", "other": "#bababa"}

    names = [t["short_name"] for t in techniques]
    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(11, max(3, len(techniques) * 0.8 + 1.5)))
        for y_idx, t in enumerate(techniques):
            pct_map = _artifact_pct(t["scores"])
            left = 0.0
            for atype in art_order:
                pct = pct_map.get(atype, 0.0)
                if pct > 0:
                    ax.barh([t["short_name"]], [pct], left=left,
                            color=art_colors.get(atype, "#aaa"),
                            label=atype.replace("_", " ").title() if y_idx == 0 else "_nolegend_",
                            edgecolor="white", linewidth=0.5)
                    if pct >= 6:
                        ax.text(left + pct / 2, y_idx, f"{pct:.0f}%",
                                va="center", ha="center", fontsize=8,
                                color="white" if atype in ("test_code", "source_code") else "black")
                    left += pct

        ax.set_xlim(0, 100)
        ax.set_xlabel("% of signal matches")
        ax.set_title("Artifact Type Distribution by Technique", fontweight="bold")
        ax.legend(loc="upper right", fontsize=8, bbox_to_anchor=(1.02, 1.05))
        fig.tight_layout()
    _save(fig, out_dir, "artifact_comparison", fmt, dpi)


def plot_extension_comparison(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Grouped bar: top file extensions across techniques."""
    all_ext: Counter = Counter()
    for t in techniques:
        all_ext.update(_extension_dist(t["findings"]))
    top_exts = [e for e, _ in all_ext.most_common(10)]
    if not top_exts:
        return

    names   = [t["short_name"] for t in techniques]
    colours = [t["color"] for t in techniques]
    n_tech  = len(techniques)
    x       = np.arange(len(top_exts))
    w       = 0.8 / n_tech

    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(max(11, len(top_exts) * 1.3), 5))
        for idx, (t, col) in enumerate(zip(techniques, colours)):
            ext_counts = _extension_dist(t["findings"])
            total      = max(sum(ext_counts.values()), 1)
            pcts       = [ext_counts.get(ext, 0) / total * 100 for ext in top_exts]
            offset     = (idx - n_tech / 2 + 0.5) * w
            ax.bar(x + offset, pcts, w * 0.88, label=t["short_name"], color=col, zorder=3)

        ax.set_xticks(x)
        ax.set_xticklabels(top_exts, rotation=30, ha="right")
        ax.yaxis.set_major_formatter(ticker.PercentFormatter())
        ax.set_ylabel("% of signal matches")
        ax.set_title("File Extension Distribution by Technique (top 10 extensions)", fontweight="bold")
        ax.legend(title="Technique", fontsize=9)
        fig.tight_layout()
    _save(fig, out_dir, "extension_comparison", fmt, dpi)


def plot_detection_spread(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    pass  # replaced by plot_test_structure_comb


def _classify_test_file(path: str) -> str:
    p = path.lower().replace("\\", "/")
    segs = p.split("/")
    n    = segs[-1]
    test_case = (
        (n.startswith("test_") and "." in n) or
        n.endswith(("_test.py", "_test.rb", "_test.go", "_test.rs",
                    "_test.cpp", "_test.c", "_test.js", "_test.ts")) or
        n.endswith(("test.java", "tests.java", "test.kt", "tests.kt")) or
        n.endswith(("_spec.rb", "_spec.js", "_spec.ts",
                    ".spec.js", ".spec.ts", ".test.js", ".test.ts")) or
        "testcase" in n or "testsuit" in n
    )
    if test_case:
        return "Test case files"
    infra = (
        "conftest" in n or "fixture" in n or
        ("helper" in n and any(s in ("tests", "test", "spec") for s in segs)) or
        ("setup"  in n and any(s in ("tests", "test", "spec") for s in segs))
    )
    if infra:
        return "Test fixtures / setup"
    in_test_dir = any(s in ("tests", "test", "spec", "__tests__", "__test__") for s in segs[:-1])
    if in_test_dir:
        return "Test suite directory"
    return "Source / non-test"


def plot_test_structure_comb(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Grouped bar: test infrastructure signal breakdown per technique (% of signals)."""
    from collections import defaultdict
    cats    = ["Test case files", "Test suite directory", "Test fixtures / setup", "Source / non-test"]
    names   = [t["short_name"] for t in techniques]
    colours = [t["color"] for t in techniques]
    n_tech  = len(techniques)
    x       = np.arange(len(cats))
    w       = 0.8 / n_tech

    cat_pcts = []
    for t in techniques:
        sig_counts: Counter = Counter()
        detected_repos = {r["repo"] for r in t["scores"] if r.get("score", 0) > 0}
        for f in t["findings"]:
            if f.get("repo") in detected_repos:
                cat = _classify_test_file(f.get("file", ""))
                sig_counts[cat] += 1
        total = max(sum(sig_counts.values()), 1)
        cat_pcts.append([sig_counts[c] / total * 100 for c in cats])

    if not any(any(p > 0 for p in row) for row in cat_pcts):
        return

    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(max(12, len(cats) * 1.8), 5))
        for idx, (t, col, pcts) in enumerate(zip(techniques, colours, cat_pcts)):
            offset = (idx - n_tech / 2 + 0.5) * w
            ax.bar(x + offset, pcts, w * 0.88, label=t["short_name"], color=col, zorder=3)
        ax.set_xticks(x)
        ax.set_xticklabels(cats, rotation=15, ha="right", fontsize=9)
        ax.yaxis.set_major_formatter(ticker.PercentFormatter())
        ax.set_ylabel("% of signal matches")
        ax.set_title("Signal Location in Test Infrastructure by Technique", fontweight="bold")
        ax.legend(title="Technique", fontsize=9)
        fig.tight_layout()
    _save(fig, out_dir, "test_structure_comb", fmt, dpi)


def plot_domain_comparison(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Grouped horizontal bar: top domains per technique (% of detected repos)."""
    all_dom: Counter = Counter()
    for t in techniques:
        all_dom.update(_domain_dist(t["scores"]))
    top_doms = [d for d, _ in all_dom.most_common(8)]
    if not top_doms:
        return

    names   = [t["short_name"] for t in techniques]
    colours = [t["color"] for t in techniques]
    n_tech  = len(techniques)
    x       = np.arange(len(top_doms))
    w       = 0.8 / n_tech

    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(max(11, len(top_doms) * 1.4), max(5, n_tech * 1.3)))
        for idx, (t, col) in enumerate(zip(techniques, colours)):
            counts = _domain_dist(t["scores"])
            n_det  = max(len(_detected(t["scores"])), 1)
            pcts   = [counts.get(d, 0) / n_det * 100 for d in top_doms]
            offset = (idx - n_tech / 2 + 0.5) * w
            ax.bar(x + offset, pcts, w * 0.88, label=t["short_name"], color=col, zorder=3)

        ax.set_xticks(x)
        ax.set_xticklabels([d.replace("_", " ").title() for d in top_doms], rotation=30, ha="right")
        ax.yaxis.set_major_formatter(ticker.PercentFormatter())
        ax.set_ylabel("% of detected repos")
        ax.set_title("Application Domain Distribution by Technique (top 8)", fontweight="bold")
        ax.legend(title="Technique", fontsize=9)
        fig.tight_layout()
    _save(fig, out_dir, "domain_comparison", fmt, dpi)


# ---------------------------------------------------------------------------
# Comparative plots — Timeline (RQ3)
# ---------------------------------------------------------------------------

def plot_yearly_trend(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    all_years = set()
    for t in techniques:
        all_years |= set(_yearly_detected(t["scores"]).keys())
    if not all_years:
        return
    years = sorted(y for y in all_years if 2010 <= y <= datetime.now(timezone.utc).year)
    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(12, 5))
        for t in techniques:
            by_year = _yearly_detected(t["scores"])
            ax.plot(years, [by_year.get(y, 0) for y in years],
                    marker="o", linewidth=2, label=t["short_name"], color=t["color"])
        ax.set_xlabel("Repository creation year")
        ax.set_ylabel("Detected repositories")
        ax.set_title("Detected Repositories by Creation Year", fontweight="bold")
        ax.legend(); ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        fig.tight_layout()
    _save(fig, out_dir, "yearly_trend", fmt, dpi)


def plot_first_technique_commit_year(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Overlaid histograms of first technique commit year per technique."""
    all_first = {t["short_name"]: _first_commit_years(t["scores"]) for t in techniques}
    all_years = [y for v in all_first.values() for y in v]
    if not all_years:
        return
    min_y = max(min(all_years) - 1, 2008)
    max_y = min(max(all_years) + 1, 2026)
    bins  = list(range(min_y, max_y + 2))
    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(10, 5))
        for t in techniques:
            vals = all_first[t["short_name"]]
            if vals:
                ax.hist(vals, bins=bins, alpha=0.6, label=t["short_name"],
                        color=t["color"], edgecolor="white", linewidth=0.4)
        ax.set_xlabel("Year")
        ax.set_ylabel("Repositories")
        ax.set_title("First Technique Commit Year", fontweight="bold")
        ax.tick_params(axis="x", rotation=45)
        ax.legend(fontsize=9)
        fig.tight_layout()
    _save(fig, out_dir, "commit_first_year", fmt, dpi)


def plot_last_technique_commit_year(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Overlaid histograms of last technique commit year per technique."""
    all_last = {t["short_name"]: _last_commit_years(t["scores"]) for t in techniques}
    all_years = [y for v in all_last.values() for y in v]
    if not all_years:
        return
    min_y = max(min(all_years) - 1, 2008)
    max_y = min(max(all_years) + 1, 2026)
    bins  = list(range(min_y, max_y + 2))
    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(10, 5))
        for t in techniques:
            vals = all_last[t["short_name"]]
            if vals:
                ax.hist(vals, bins=bins, alpha=0.6, label=t["short_name"],
                        color=t["color"], edgecolor="white", linewidth=0.4)
        ax.set_xlabel("Year")
        ax.set_ylabel("Repositories")
        ax.set_title("Last Technique Commit Year", fontweight="bold")
        ax.tick_params(axis="x", rotation=45)
        ax.legend(fontsize=9)
        fig.tight_layout()
    _save(fig, out_dir, "commit_last_year", fmt, dpi)


def plot_project_life_year_comb(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Multi-line chart: technique commits per year of repo life, one line per technique."""
    all_life_years: set = set()
    year_data = {}
    for t in techniques:
        life_counts: Counter = Counter()
        for r in _detected(t["scores"]):
            created = (r.get("created_at") or "")[:4]
            if not created or not created.isdigit():
                continue
            created_year = int(created)
            for dt in (r.get("technique_commit_dates") or []):
                if isinstance(dt, str) and len(dt) >= 4 and dt[:4].isdigit():
                    yol = int(dt[:4]) - created_year + 1
                    if 1 <= yol <= 20:
                        life_counts[yol] += 1
                        all_life_years.add(yol)
        year_data[t["short_name"]] = life_counts

    if not all_life_years:
        return

    max_yr     = min(max(all_life_years), 20)
    life_years = list(range(1, max_yr + 1))
    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(12, 5))
        for t in techniques:
            counts = year_data[t["short_name"]]
            if counts:
                ax.plot(life_years, [counts.get(y, 0) for y in life_years],
                        marker="o", linewidth=2, label=t["short_name"], color=t["color"])
        ax.set_xlabel("Year of repository life (1 = first year)")
        ax.set_ylabel("Technique commits (across detected repos)")
        ax.set_title("Technique Commits by Year of Repository Life", fontweight="bold")
        if max_yr <= 15:
            ax.set_xticks(life_years)
            ax.set_xticklabels([f"Yr {y}" for y in life_years], rotation=45)
        else:
            tick_positions = list(range(1, max_yr + 1, 2))
            ax.set_xticks(tick_positions)
            ax.set_xticklabels([f"Yr {y}" for y in tick_positions], rotation=45)
        ax.legend()
        fig.tight_layout()
    _save(fig, out_dir, "project_life_year_comb", fmt, dpi)


def plot_technique_commit_timeline_comb(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Multi-line chart: technique commits per year across detected repos, per technique."""
    from collections import defaultdict
    year_data = {}
    all_years: set = set()
    for t in techniques:
        counts: Counter = Counter()
        for r in _detected(t["scores"]):
            for dt in (r.get("technique_commit_dates") or []):
                if isinstance(dt, str) and len(dt) >= 4 and dt[:4].isdigit():
                    y = int(dt[:4])
                    if 2005 <= y <= 2026:
                        counts[y] += 1
                        all_years.add(y)
        year_data[t["short_name"]] = counts

    if not all_years:
        return

    years = sorted(all_years)
    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(12, 5))
        for t in techniques:
            counts = year_data[t["short_name"]]
            if counts:
                ax.plot(years, [counts.get(y, 0) for y in years],
                        marker="o", linewidth=2, label=t["short_name"], color=t["color"])
        ax.set_xlabel("Year")
        ax.set_ylabel("Technique commits (across all detected repos)")
        ax.set_title("Technique Commit Activity Over Time", fontweight="bold")
        ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax.legend(); fig.tight_layout()
    _save(fig, out_dir, "commit_timeline_comb", fmt, dpi)


def plot_commit_span(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Box plot: technique commit span in years per technique."""
    names   = [t["short_name"] for t in techniques]
    colours = [t["color"] for t in techniques]
    data    = [_commit_span_vals(t["scores"]) for t in techniques]

    if not any(data):
        return

    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(max(8, len(techniques) * 1.6), 5))
        _violin_or_box(ax, data, names, colours,
                       "Span (years, first → last technique commit)",
                       "Technique Commit Activity Span", use_violin=False)
        fig.tight_layout()
    _save(fig, out_dir, "commit_span", fmt, dpi)


def plot_commit_ratio(techniques, out_dir: Path, fmt: str, dpi: int) -> None:
    """Box plot: technique commit ratio per technique."""
    names   = [t["short_name"] for t in techniques]
    colours = [t["color"] for t in techniques]
    data    = [_commit_ratio_vals(t["scores"]) for t in techniques]

    if not any(data):
        return

    rows = []
    for name, vals in zip(names, data):
        for v in vals:
            rows.append({"Technique": name, "pct": v})
    if not rows:
        return
    df  = pd.DataFrame(rows)
    pal = {n: c for n, c in zip(names, colours)}
    with plt.style.context(_PLOT_STYLE):
        fig, ax = plt.subplots(figsize=(max(8, len(techniques) * 1.6), 5))
        sns.boxplot(data=df, x="Technique", y="pct",
                    hue="Technique", order=names, palette=pal, ax=ax,
                    flierprops=dict(marker=".", markersize=4, alpha=0.5), legend=False)
        ax.yaxis.set_major_formatter(ticker.PercentFormatter())
        ax.set_ylabel("% of sampled commits mentioning technique")
        ax.set_title("Technique Commit Ratio — Detected Repos", fontweight="bold")
        fig.tight_layout()
    _save(fig, out_dir, "commit_ratio", fmt, dpi)


# ---------------------------------------------------------------------------
# Report text sections
# ---------------------------------------------------------------------------

def sec_overview(techniques) -> str:
    rows = "\n".join(
        f"| **{t['name']} ({t['short_name']})** "
        f"| {_det_stats(t['scores'])['total']:,} "
        f"| {_det_stats(t['scores'])['detected']:,} "
        f"| {_pct(_det_stats(t['scores'])['rate'])} "
        f"| {_det_stats(t['scores'])['median']:.0f} "
        f"| {_det_stats(t['scores'])['mean']:.1f} |"
        for t in techniques
    )
    return f"""\
## Dataset Overview

Detection rate = repos with ≥ 1 pattern match ÷ total analysed. All rates are lower-bound estimates.
All subsequent comparisons use only detected repos unless stated otherwise.

| Technique | Analysed | Detected | Detection rate | Median detections | Mean detections |
|---|---|---|---|---|---|
{rows}
"""


def sec_adoption(techniques, plots_rel: str, fmt: str) -> str:
    # Per-type artifact breakdown per technique
    art_order  = ["test_code", "source_code", "documentation", "config", "other"]
    art_header = "| Technique | " + " | ".join(k.replace("_", " ").title() for k in art_order) + " |"
    art_sep    = "|---|" + "---|" * len(art_order)
    art_rows   = []
    for t in techniques:
        pct_map = _artifact_pct(t["scores"])
        cells   = " | ".join(_pct(pct_map.get(k, 0)) for k in art_order)
        art_rows.append(f"| {t['short_name']} | {cells} |")
    art_table = "\n".join(art_rows)

    # Contributor stats
    contrib_rows = []
    for t in techniques:
        vals = _contributor_vals(t["scores"])
        if vals:
            contrib_rows.append(
                f"| {t['short_name']} | {statistics.median(vals):.0f} | {statistics.mean(vals):.1f} | {max(vals):,} |"
            )
    contrib_table = "\n".join(contrib_rows)

    # Technique ratios
    ratio_rows = []
    for t in techniques:
        ld = _line_density_vals(t["scores"])
        fr = _file_ratio_vals(t["scores"])
        ratio_rows.append(
            f"| {t['short_name']} "
            f"| {_pct(statistics.median(ld)*100) if ld else '—'} "
            f"| {_pct(statistics.median(fr)*100) if fr else '—'} |"
        )
    ratio_table = "\n".join(ratio_rows)

    return f"""\
## Adoption Overview

{_img(plots_rel, 'adoption_overview', fmt, 'Detection rate and detected repo count by technique')}

### Detection Depth

{_img(plots_rel, 'detection_depth', fmt, 'Detection count distribution per technique (log scale)')}

| Technique | Median detections | Mean detections | Max |
|---|---|---|---|
{chr(10).join(
    f"| {t['short_name']} | {_det_stats(t['scores'])['median']:.0f} | {_det_stats(t['scores'])['mean']:.1f} | {max((_det_counts(t['scores']) or [0])):,} |"
    for t in techniques
)}

### Artifact Type Distribution

Signal matches broken down by artifact type (test code, source code, documentation, config, other).

{art_header}
{art_sep}
{art_table}

{_img(plots_rel, 'artifact_comparison', fmt, 'Artifact type distribution by technique')}

### Technique Coverage Ratios (Detected Repos)

| Technique | Median line density | Median file ratio |
|---|---|---|
{ratio_table}

{_img(plots_rel, 'technique_ratios', fmt, 'Technique line density and file ratio distributions per technique')}

### Contributor Activity (Detected Repos)

| Technique | Median contributors | Mean contributors | Max |
|---|---|---|---|
{contrib_table}

{_img(plots_rel, 'contributor_comparison', fmt, 'Contributor count — median per technique (detected repos)')}
"""


def sec_usage(techniques, plots_rel: str, fmt: str) -> str:
    # Project type comparison table
    type_order   = ["general_usage", "framework", "mixed", "research_artifact", "unknown"]
    type_display = {"general_usage": "Actual Usage", "framework": "Framework",
                    "mixed": "Mixed", "research_artifact": "Research Artifact", "unknown": "Unknown"}
    pt_rows = []
    for pt in type_order:
        row_vals = []
        for t in techniques:
            dist  = _project_type_dist(t["scores"])
            total = max(sum(dist.values()), 1)
            row_vals.append(_pct(dist.get(pt, 0) / total * 100))
        pt_rows.append(f"| {type_display.get(pt, pt)} | " + " | ".join(row_vals) + " |")
    pt_table = "\n".join(pt_rows)
    pt_header = "| Project Role | " + " | ".join(t["short_name"] for t in techniques) + " |"
    pt_sep    = "|---|" + "---|" * len(techniques)

    return f"""\
## Usage Patterns

### Project Role Comparison

{pt_header}
{pt_sep}
{pt_table}

{_img(plots_rel, 'project_type_comparison', fmt, 'Project role distribution by technique')}

### Detection Distribution

Signal location in test infrastructure across techniques.

{_img(plots_rel, 'test_structure_comb', fmt, 'Signal location in test infrastructure by technique')}

### Language Distribution

{_img(plots_rel, 'language_comparison', fmt, 'Language distribution per technique (top 10 languages, % of detected repos)')}

### Artifact Type Distribution

{_img(plots_rel, 'artifact_comparison', fmt, 'Artifact type distribution by technique (stacked)')}

### File Extension Breakdown

{_img(plots_rel, 'extension_comparison', fmt, 'File extension distribution by technique (top 10 extensions)')}

### Application Domain

Domains inferred from repo name, description, and GitHub topics. A repo can match multiple domains.

{_img(plots_rel, 'domain_comparison', fmt, 'Application domain distribution per technique (top 8 domains, % of detected repos)')}
"""


def sec_timeline(techniques, plots_rel: str, fmt: str) -> str:
    def _ms(vals, fmt_s="{:.0f}", suffix=""):
        return (fmt_s.format(statistics.median(vals)) + suffix) if vals else "—"

    commit_rows = []
    for t in techniques:
        first_y = _first_commit_years(t["scores"])
        last_y  = _last_commit_years(t["scores"])
        span_v  = _commit_span_vals(t["scores"])
        ratio_v = _commit_ratio_vals(t["scores"])
        commit_rows.append(
            f"| {t['short_name']}"
            f" | {_ms(first_y)}"
            f" | {_ms(last_y)}"
            f" | {_ms(span_v, '{:.1f}', ' yrs')}"
            f" | {_ms(ratio_v, '{:.1f}', '%')} |"
        )
    commit_table = "\n".join(commit_rows)

    return f"""\
## Timeline

### Repository Creation Trend

{_img(plots_rel, 'yearly_trend', fmt, 'Detected repos by creation year per technique')}

### Technique Commit Activity

Commit metrics derived from up to 500 most-recent commits per repo.

| Technique | Median first commit yr | Median last commit yr | Median span | Median commit ratio |
|---|---|---|---|---|
{commit_table}

{_img(plots_rel, 'commit_timeline_comb', fmt, 'Technique commit activity over time per technique')}
{_img(plots_rel, 'commit_first_year', fmt, 'First technique commit year distribution per technique')}
{_img(plots_rel, 'commit_last_year', fmt, 'Last technique commit year distribution per technique')}
{_img(plots_rel, 'commit_span', fmt, 'First-to-last commit duration per technique (years)')}
{_img(plots_rel, 'commit_ratio', fmt, 'Technique commit ratio per technique')}
{_img(plots_rel, 'project_life_year_comb', fmt, 'Technique commits by year of repository life per technique')}
"""


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_report(techniques, plots_rel: str, fmt: str) -> str:
    ts         = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tech_names = ", ".join(t["short_name"] for t in techniques)
    parts = [
        f"# Comparative Testing Technique Analysis\n\n"
        f"**Techniques:** {tech_names}  \n*Generated: {ts}*\n\n---\n",
        sec_overview(techniques),
        "---\n",
        sec_adoption(techniques, plots_rel, fmt),
        "---\n",
        sec_usage(techniques, plots_rel, fmt),
        "---\n",
        sec_timeline(techniques, plots_rel, fmt),
    ]
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run(out_path: Path, plots_dir: Path, fmt: str, dpi: int, slug_filter=None) -> None:
    console.rule("[bold blue]Comparative Analysis[/]")
    techniques = discover_techniques(RESULTS_DIR, slug_filter)
    if not techniques:
        console.print("[red]No completed analyses found. Run each technique pipeline first.[/]")
        return
    console.print(f"  Found {len(techniques)} technique(s): {', '.join(t['short_name'] for t in techniques)}")
    console.print("  Generating comparative plots…")

    # Adoption (RQ1)
    plot_adoption_rates(        techniques, plots_dir, fmt, dpi)
    plot_detection_depth(       techniques, plots_dir, fmt, dpi)
    plot_contributor_comparison(techniques, plots_dir, fmt, dpi)
    plot_technique_ratios(      techniques, plots_dir, fmt, dpi)

    # Usage (RQ2)
    plot_project_type_comparison(techniques, plots_dir, fmt, dpi)
    plot_test_structure_comb(   techniques, plots_dir, fmt, dpi)
    plot_language_comparison(   techniques, plots_dir, fmt, dpi)
    plot_artifact_comparison(   techniques, plots_dir, fmt, dpi)
    plot_extension_comparison(  techniques, plots_dir, fmt, dpi)
    plot_domain_comparison(     techniques, plots_dir, fmt, dpi)

    # Timeline (RQ3)
    plot_yearly_trend(                   techniques, plots_dir, fmt, dpi)
    plot_technique_commit_timeline_comb( techniques, plots_dir, fmt, dpi)
    plot_first_technique_commit_year(    techniques, plots_dir, fmt, dpi)
    plot_last_technique_commit_year(     techniques, plots_dir, fmt, dpi)
    plot_commit_span(                    techniques, plots_dir, fmt, dpi)
    plot_commit_ratio(                   techniques, plots_dir, fmt, dpi)
    plot_project_life_year_comb(         techniques, plots_dir, fmt, dpi)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plots_rel = os.path.relpath(plots_dir.resolve(), out_path.parent.resolve()).replace("\\", "/")
    report = build_report(techniques, plots_rel, fmt)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    console.print(f"[bold green]Saved:[/] {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python combine.py")
    parser.add_argument("--output",     type=Path, default=None)
    parser.add_argument("--plots-dir",  type=Path, default=None)
    parser.add_argument("--format",     choices=["png", "pdf", "svg"], default="png")
    parser.add_argument("--dpi",        type=int,  default=150)
    parser.add_argument("--techniques", nargs="+", default=None, metavar="SLUG")
    args = parser.parse_args()

    run(
        out_path    = args.output    or (COMBINED_DIR / "comparative_report.md"),
        plots_dir   = args.plots_dir or (COMBINED_DIR / "plots"),
        fmt         = args.format,
        dpi         = args.dpi,
        slug_filter = args.techniques,
    )


if __name__ == "__main__":
    main()
