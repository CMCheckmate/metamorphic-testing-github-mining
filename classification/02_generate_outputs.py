"""
02_generate_outputs.py
Reads all_classifications.json (produced by the LLM classification workflow),
merges with original CSV metadata, and produces:
  - outputs/usage_classification.csv
  - outputs/domain_classification.csv
  - outputs/charts/usage_distribution.png
  - outputs/charts/domain_distribution.png
  - outputs/charts/usage_distribution_filtered.png   (medium+ confidence only)
  - outputs/charts/domain_distribution_filtered.png

Usage: python3 -I 02_generate_outputs.py
"""

import csv
import json
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
MT_BASE = os.path.join(BASE, "..", "metamorphic_testing")

CLASSIFICATIONS_JSON = os.path.join(BASE, "results", "all_classifications.json")
USAGE_CSV            = os.path.join(MT_BASE, "sections_report", "usage_repos_for_review.csv")
OUT_DIR              = os.path.join(BASE, "outputs")
CHARTS_DIR           = os.path.join(OUT_DIR, "charts")
USAGE_OUT_CSV        = os.path.join(OUT_DIR, "usage_classification.csv")
DOMAIN_OUT_CSV       = os.path.join(OUT_DIR, "domain_classification.csv")

# ─── Colour palette (matches existing report style: greyed blues + accents) ───
PALETTE = {
    "actual_usage":     "#2563EB",   # blue
    "framework_library":"#16A34A",   # green
    "research_artifact":"#D97706",   # amber
    "other_usage":      "#9CA3AF",   # grey
}
DOMAIN_COLOURS = [
    "#2563EB","#16A34A","#D97706","#DC2626","#7C3AED",
    "#0891B2","#DB2777","#65A30D","#EA580C","#4F46E5","#0D9488","#B45309",
]


def load_original_meta():
    """Load url, stars, language from original CSV keyed by repo."""
    with open(USAGE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {r["repo"]: r for r in rows}


def load_classifications():
    with open(CLASSIFICATIONS_JSON, encoding="utf-8") as f:
        return json.load(f)


# ─── CSV writers ──────────────────────────────────────────────────────────────

USAGE_COLS = [
    "repo", "url", "stars", "language",
    "actual_usage", "framework_library", "research_artifact", "other_usage",
    "other_usage_description",
    "usage_confidence", "usage_reasoning",
]

DOMAIN_COLS = [
    "repo", "url", "language",
    "dom_web_api", "dom_database", "dom_security_crypto", "dom_finance",
    "dom_machine_learning", "dom_compiler_pl", "dom_scientific_computing",
    "dom_distributed_systems", "dom_operating_systems", "dom_embedded_iot",
    "dom_bioinformatics", "dom_autonomous_robotics", "dom_no_match",
    "domain_confidence", "domain_reasoning",
]

USAGE_LABEL_COLS = ["actual_usage", "framework_library", "research_artifact", "other_usage"]
DOMAIN_LABEL_COLS = [
    "dom_web_api", "dom_database", "dom_security_crypto", "dom_finance",
    "dom_machine_learning", "dom_compiler_pl", "dom_scientific_computing",
    "dom_distributed_systems", "dom_operating_systems", "dom_embedded_iot",
    "dom_bioinformatics", "dom_autonomous_robotics", "dom_no_match",
]


def _sort_key(r, label_cols):
    """Sort: most labels first, then by confidence (high > medium > low)."""
    label_count = sum(1 for c in label_cols if r.get(c) is True)
    conf_map = {"high": 0, "medium": 1, "low": 2}
    usage_conf = conf_map.get(r.get("usage_confidence", "low"), 2)
    dom_conf   = conf_map.get(r.get("domain_confidence",  "low"), 2)
    return (-label_count, usage_conf + dom_conf)


def write_usage_csv(classifications, meta):
    os.makedirs(OUT_DIR, exist_ok=True)
    enriched = []
    for c in classifications:
        repo = c.get("repo", "")
        m = meta.get(repo, {})
        row = {
            "repo": repo,
            "url": m.get("url", f"https://github.com/{repo}"),
            "stars": m.get("stars", ""),
            "language": m.get("language", ""),
            "actual_usage": c.get("actual_usage", False),
            "framework_library": c.get("framework_library", False),
            "research_artifact": c.get("research_artifact", False),
            "other_usage": c.get("other_usage", False),
            "other_usage_description": c.get("other_usage_description", ""),
            "usage_confidence": c.get("usage_confidence", ""),
            "usage_reasoning": c.get("usage_reasoning", ""),
        }
        enriched.append(row)
    enriched.sort(key=lambda r: _sort_key(r, USAGE_LABEL_COLS))
    with open(USAGE_OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=USAGE_COLS)
        writer.writeheader()
        writer.writerows(enriched)
    print(f"  Wrote {len(enriched)} rows → {USAGE_OUT_CSV}")
    return enriched


def write_domain_csv(classifications, meta):
    enriched = []
    for c in classifications:
        repo = c.get("repo", "")
        m = meta.get(repo, {})
        row = {
            "repo": repo,
            "url": m.get("url", f"https://github.com/{repo}"),
            "language": m.get("language", ""),
            **{col: c.get(col, False) for col in DOMAIN_LABEL_COLS},
            "domain_confidence": c.get("domain_confidence", ""),
            "domain_reasoning": c.get("domain_reasoning", ""),
        }
        enriched.append(row)
    enriched.sort(key=lambda r: _sort_key(r, DOMAIN_LABEL_COLS))
    with open(DOMAIN_OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DOMAIN_COLS)
        writer.writeheader()
        writer.writerows(enriched)
    print(f"  Wrote {len(enriched)} rows → {DOMAIN_OUT_CSV}")
    return enriched


# ─── Chart helpers ────────────────────────────────────────────────────────────

def _apply_report_style():
    """Apply a style matching the existing report plots (clean, greyscale-friendly)."""
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "x",
        "grid.alpha": 0.35,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "savefig.dpi": 150,
    })


def plot_usage_distribution(rows, outpath, title_suffix=""):
    _apply_report_style()
    labels_display = {
        "actual_usage":     "Actual Usage",
        "framework_library":"Framework / Library",
        "research_artifact":"Research Artefact",
        "other_usage":      "Other",
    }
    counts = {k: sum(1 for r in rows if r.get(k) is True) for k in USAGE_LABEL_COLS}
    total = len(rows)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    fig.suptitle(f"Usage Classification of MT Repository Sample{title_suffix}", fontsize=12, fontweight="bold", y=1.01)

    # Left: horizontal bar chart
    ax = axes[0]
    keys  = list(labels_display.keys())
    vals  = [counts[k] for k in keys]
    names = [labels_display[k] for k in keys]
    colours = [PALETTE[k] for k in keys]
    bars = ax.barh(names[::-1], vals[::-1], color=colours[::-1], edgecolor="white", height=0.6)
    ax.set_xlabel("Number of Repositories")
    ax.set_title("Repository Count by Usage Type")
    for bar, v in zip(bars, vals[::-1]):
        ax.text(bar.get_width() + total * 0.005, bar.get_y() + bar.get_height() / 2,
                f"{v:,} ({v/total*100:.1f}%)", va="center", fontsize=8.5)
    ax.set_xlim(0, max(vals) * 1.25)
    ax.tick_params(axis="y", length=0)

    # Right: pie chart
    ax2 = axes[1]
    wedge_sizes = vals
    wedge_labels = [f"{labels_display[k]}\n{counts[k]:,} ({counts[k]/total*100:.1f}%)" for k in keys]
    wedges, _ = ax2.pie(wedge_sizes, colors=colours, startangle=90,
                        wedgeprops=dict(edgecolor="white", linewidth=1.5))
    ax2.legend(wedges, wedge_labels, loc="lower center", bbox_to_anchor=(0.5, -0.28),
               fontsize=8, frameon=False, ncol=2)
    ax2.set_title(f"Proportional Distribution\n(n = {total:,})")

    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()
    print(f"  Chart → {outpath}")


def plot_domain_distribution(rows, outpath, title_suffix=""):
    _apply_report_style()
    domain_display = {
        "dom_web_api":             "Web / API",
        "dom_machine_learning":    "Machine Learning",
        "dom_database":            "Database",
        "dom_security_crypto":     "Security / Crypto",
        "dom_compiler_pl":         "Compiler / PL",
        "dom_finance":             "Finance",
        "dom_scientific_computing":"Scientific Computing",
        "dom_distributed_systems": "Distributed Systems",
        "dom_operating_systems":   "Operating Systems",
        "dom_embedded_iot":        "Embedded / IoT",
        "dom_bioinformatics":      "Bioinformatics",
        "dom_autonomous_robotics": "Autonomous / Robotics",
        "dom_no_match":            "No Domain Matched",
    }
    # Only repos with at least one domain (exclude those only matching no_match for the main bar)
    counts_all = {k: sum(1 for r in rows if r.get(k) is True) for k in DOMAIN_LABEL_COLS}
    total = len(rows)

    # Sort by count descending, put no_match last
    domain_keys = [k for k in DOMAIN_LABEL_COLS if k != "dom_no_match"]
    domain_keys.sort(key=lambda k: counts_all[k], reverse=True)
    domain_keys.append("dom_no_match")

    fig, ax = plt.subplots(figsize=(10, 6))
    names   = [domain_display[k] for k in domain_keys]
    vals    = [counts_all[k]     for k in domain_keys]
    colours_list = DOMAIN_COLOURS[:len(domain_keys)-1] + ["#9CA3AF"]  # grey for no match

    bars = ax.barh(names[::-1], vals[::-1], color=colours_list[::-1], edgecolor="white", height=0.65)
    ax.set_xlabel("Number of Repositories")
    ax.set_title(f"Application Domain Distribution of MT Usage Repositories{title_suffix}\n"
                 f"(multi-label; n = {total:,} repos)", fontweight="bold")
    pct_base = total - counts_all["dom_no_match"]
    for bar, v, k in zip(bars, vals[::-1], domain_keys[::-1]):
        label = f"{v:,} ({v/total*100:.1f}%)"
        ax.text(bar.get_width() + total * 0.003, bar.get_y() + bar.get_height() / 2,
                label, va="center", fontsize=8)
    ax.set_xlim(0, max(vals) * 1.22)
    ax.tick_params(axis="y", length=0)
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()
    print(f"  Chart → {outpath}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(CHARTS_DIR, exist_ok=True)

    print("Loading classifications...")
    classifications = load_classifications()
    print(f"  {len(classifications)} repos classified")

    print("Loading original CSV metadata...")
    meta = load_original_meta()

    print("Writing CSVs...")
    usage_rows  = write_usage_csv(classifications, meta)
    domain_rows = write_domain_csv(classifications, meta)

    # Summary stats
    print("\n=== Usage classification summary ===")
    total = len(usage_rows)
    for col in USAGE_LABEL_COLS:
        n = sum(1 for r in usage_rows if r.get(col) is True)
        print(f"  {col}: {n} ({n/total*100:.1f}%)")

    for conf in ("high", "medium", "low"):
        n = sum(1 for r in usage_rows if r.get("usage_confidence") == conf)
        print(f"  confidence={conf}: {n} ({n/total*100:.1f}%)")

    medium_plus = [r for r in usage_rows if r.get("usage_confidence") in ("high", "medium")]
    print(f"\n  Medium+ confidence: {len(medium_plus)}/{total}")

    print("\n=== Domain classification summary ===")
    for col in DOMAIN_LABEL_COLS:
        n = sum(1 for r in domain_rows if r.get(col) is True)
        print(f"  {col}: {n} ({n/total*100:.1f}%)")

    print("\nGenerating charts...")
    # All repos
    plot_usage_distribution(usage_rows,  os.path.join(CHARTS_DIR, "usage_distribution.png"))
    plot_domain_distribution(domain_rows, os.path.join(CHARTS_DIR, "domain_distribution.png"))

    # Medium+ confidence only
    medium_plus_domain = [r for r in domain_rows if r.get("domain_confidence") in ("high", "medium")]
    plot_usage_distribution(medium_plus,  os.path.join(CHARTS_DIR, "usage_distribution_filtered.png"),
                            " (medium+ confidence)")
    plot_domain_distribution(medium_plus_domain, os.path.join(CHARTS_DIR, "domain_distribution_filtered.png"),
                             " (medium+ confidence)")

    print("\nAll outputs generated.")


if __name__ == "__main__":
    main()
