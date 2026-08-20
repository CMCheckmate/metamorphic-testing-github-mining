"""
Phase 4 — Plots & Visualisations
==================================
Reads the outputs of search.py (results/<slug>/raw/) and analyze.py
(results/<slug>/analysis/) and produces publication-quality plots saved to
results/<slug>/plots/.

Usage:
    python plot.py --technique techniques/metamorphic_testing.yaml
    python plot.py --technique techniques/fuzzing.yaml --format pdf --dpi 300

    --technique PATH  Path to technique YAML file (required)
    --output-dir      Where to save plots (default: results/<slug>/plots/)
    --dpi             Resolution for raster outputs (default: 150)
    --format          Output format: png, pdf, or svg (default: png)
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns
from rich.console import Console

from config import RESULTS_DIR

console = Console()

PALETTE = {
    "strong_explicit": "#1a6e3c",
    "weak_explicit":   "#5aad72",
    "none":            "#bdbdbd",
}
TIER_ORDER = ["strong_explicit", "weak_explicit", "none"]

sns.set_theme(style="whitegrid", font_scale=1.1)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | list:
    if not path.exists():
        console.print(f"[yellow]Missing:[/] {path} — skipping plots that need it")
        return None
    with open(path) as f:
        return json.load(f)


def load_all(raw_dir: Path, analysis_dir: Path):
    return {
        "summary":     _load_json(raw_dir / "summary.json"),
        "repos":       _load_json(raw_dir / "repos.json"),
        "code":        _load_json(raw_dir / "code.json"),
        "repo_scores": _load_json(analysis_dir / "repo_scores.json"),
        "findings":    _load_json(analysis_dir / "findings.json"),
    }


# ---------------------------------------------------------------------------
# Helper: substitute "MT" technique name in plot titles
# ---------------------------------------------------------------------------

def _title(base: str, technique_name: str) -> str:
    """Replace 'MT' placeholder in a title with the technique short name."""
    return base.replace("{technique}", technique_name)


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def _save(fig, out_dir: Path, name: str, fmt: str, dpi: int) -> None:
    path = out_dir / f"{name}.{fmt}"
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    console.print(f"  [green]saved[/] {path.name}")


# ---------------------------------------------------------------------------
# 1. Query hit counts (from summary.json)
# ---------------------------------------------------------------------------

def plot_query_hits(summary: dict, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
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
    colors = [sns.color_palette("Blues_d", as_cmap=False, n_colors=8)[5]] * len(df)
    ax.barh(df["surface_query"], df["hits"], color=colors)
    ax.set_xlabel("Total hits")
    ax.set_title(f"GitHub Search Hit Counts by Query and Surface — {technique_name}")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    _save(fig, out_dir, "query_hits", fmt, dpi)


# ---------------------------------------------------------------------------
# 2. Classification tier distribution (from repo_scores.json)
# ---------------------------------------------------------------------------

def plot_classification_dist(repo_scores: list, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    if not repo_scores:
        return

    counts = Counter(r["classification"] for r in repo_scores)
    tiers  = [t for t in TIER_ORDER if t in counts]
    values = [counts[t] for t in tiers]
    colors = [PALETTE[t] for t in tiers]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(tiers, values, color=colors, edgecolor="white", linewidth=0.8)
    ax.bar_label(bars, padding=3, fontsize=10)
    ax.set_xlabel("Classification tier")
    ax.set_ylabel("Number of repositories")
    ax.set_title(f"{technique_name} Classification Tier Distribution")
    ax.set_xticklabels([t.replace("_", " ").title() for t in tiers], rotation=20, ha="right")
    _save(fig, out_dir, "classification_dist", fmt, dpi)


# ---------------------------------------------------------------------------
# 3. Yearly trend (MT-adopting repos created per year)
# ---------------------------------------------------------------------------

def plot_yearly_trend(repo_scores: list, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    if not repo_scores:
        return

    rows = []
    for r in repo_scores:
        created = r.get("created_at", "")
        if not created:
            continue
        year = int(created[:4])
        rows.append({"year": year, "classification": r["classification"]})

    if not rows:
        console.print("  [yellow]No created_at data in repo_scores — skipping yearly trend[/]")
        return

    df = pd.DataFrame(rows)
    explicit = df[df["classification"].isin(["strong_explicit", "weak_explicit"])]
    yearly   = explicit.groupby("year").size().reset_index(name="count")
    yearly   = yearly[yearly["year"] >= 2010]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(yearly["year"], yearly["count"], marker="o", linewidth=2,
            color=PALETTE["strong_explicit"])
    ax.fill_between(yearly["year"], yearly["count"], alpha=0.15,
                    color=PALETTE["strong_explicit"])
    ax.set_xlabel("Year repository created")
    ax.set_ylabel(f"Repositories with explicit {technique_name} adoption")
    ax.set_title(f"Yearly Trend: Explicit {technique_name} Adoption in New Repositories")
    ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
    ax.xaxis.set_tick_params(rotation=45)
    _save(fig, out_dir, "yearly_trend", fmt, dpi)


# ---------------------------------------------------------------------------
# 4. Language distribution (explicit MT repos only)
# ---------------------------------------------------------------------------

def plot_language_dist(repo_scores: list, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    if not repo_scores:
        return

    explicit = [r for r in repo_scores if r["classification"] in ("strong_explicit", "weak_explicit")]
    if not explicit:
        return

    langs  = Counter(r["language"] or "Unknown" for r in explicit)
    top    = langs.most_common(15)
    labels = [l for l, _ in top]
    values = [v for _, v in top]

    fig, ax = plt.subplots(figsize=(9, 5))
    palette = sns.color_palette("viridis", n_colors=len(labels))
    bars = ax.bar(labels, values, color=palette, edgecolor="white", linewidth=0.8)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_xlabel("Primary language")
    ax.set_ylabel(f"Repositories with explicit {technique_name} adoption")
    ax.set_title(f"Language Distribution — Explicit {technique_name} Repos (Top 15)")
    ax.set_xticklabels(labels, rotation=35, ha="right")
    _save(fig, out_dir, "language_dist", fmt, dpi)


# ---------------------------------------------------------------------------
# 5. Stars vs explicit hit count (scatter, log scale)
# ---------------------------------------------------------------------------

def plot_stars_scatter(repo_scores: list, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    if not repo_scores:
        return

    with_signal = [r for r in repo_scores if r["classification"] != "none"]
    if not with_signal:
        return

    df = pd.DataFrame(with_signal)
    df["stars_log"] = (df["stars"] + 1).apply(lambda x: x ** 0.5)

    fig, ax = plt.subplots(figsize=(9, 6))
    for tier in TIER_ORDER:
        sub = df[df["classification"] == tier]
        if sub.empty:
            continue
        ax.scatter(sub["stars_log"], sub["direct_matches"],
                   label=tier.replace("_", " ").title(),
                   color=PALETTE[tier], alpha=0.7, edgecolors="white", linewidth=0.5, s=60)

    ax.set_xlabel("√(Stars + 1)  (monotone proxy for popularity)")
    ax.set_ylabel(f"Number of direct {technique_name} pattern matches")
    ax.set_title(f"Repository Popularity vs Explicit {technique_name} Hit Count")
    ax.legend(title="Classification", fontsize=9)
    _save(fig, out_dir, "stars_vs_score", fmt, dpi)


# ---------------------------------------------------------------------------
# 6. Explicit pattern hit frequency (from findings.json)
# ---------------------------------------------------------------------------

def plot_pattern_freq(findings: list, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    if not findings:
        return

    if not findings:
        return

    counts = Counter(f["label"] for f in findings)
    top    = counts.most_common(20)
    labels = [l for l, _ in reversed(top)]
    values = [v for _, v in reversed(top)]

    fig, ax = plt.subplots(figsize=(10, max(5, len(labels) * 0.38)))
    palette = sns.color_palette("Blues_d", n_colors=len(labels))
    ax.barh(labels, values, color=palette)
    ax.set_xlabel("Number of individual matches")
    ax.set_title(f"{technique_name} Explicit Pattern Hit Frequency (top 20)")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    _save(fig, out_dir, "pattern_freq", fmt, dpi)


# ---------------------------------------------------------------------------
# 7. Language × Classification tier heatmap
# ---------------------------------------------------------------------------

def plot_domain_heatmap(repo_scores: list, out_dir: Path, fmt: str, dpi: int) -> None:
    if not repo_scores:
        return

    df = pd.DataFrame(repo_scores)
    df["language"] = df["language"].fillna("Unknown").replace("", "Unknown")

    top_langs = df["language"].value_counts().head(12).index.tolist()
    df_top    = df[df["language"].isin(top_langs)].copy()

    pivot = (
        df_top.groupby(["language", "classification"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=[t for t in TIER_ORDER if t in df_top["classification"].unique()], fill_value=0)
    )

    if pivot.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(
        pivot,
        annot=True,
        fmt="d",
        cmap="YlOrRd",
        linewidths=0.4,
        ax=ax,
        cbar_kws={"label": "Repository count"},
    )
    ax.set_xlabel("Classification tier")
    ax.set_ylabel("Primary language")
    ax.set_title("Language × Classification Heatmap (Top 12 Languages)")
    ax.set_xticklabels(
        [t.replace("_", " ").title() for t in pivot.columns],
        rotation=25, ha="right",
    )
    _save(fig, out_dir, "domain_heatmap", fmt, dpi)


# ---------------------------------------------------------------------------
# 8. Matched-query overlap (how many repos found by multiple queries)
# ---------------------------------------------------------------------------

def plot_query_overlap(repo_scores: list, out_dir: Path, fmt: str, dpi: int) -> None:
    if not repo_scores:
        return

    query_counts = Counter(len(r.get("found_by_queries", [])) for r in repo_scores)
    if not query_counts:
        return

    labels = sorted(query_counts.keys())
    values = [query_counts[k] for k in labels]
    str_labels = [str(k) for k in labels]

    fig, ax = plt.subplots(figsize=(7, 4))
    palette = sns.color_palette("crest", n_colors=len(labels))
    bars = ax.bar(str_labels, values, color=palette, edgecolor="white")
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_xlabel("Number of distinct search queries that found the repo")
    ax.set_ylabel("Repository count")
    ax.set_title("Search Query Coverage Overlap per Repository")
    _save(fig, out_dir, "query_overlap", fmt, dpi)


# ---------------------------------------------------------------------------
# 9. Author / organisation concentration (Q6)
# ---------------------------------------------------------------------------

def plot_author_dist(repo_scores: list, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Top organisations/users by count of explicit repositories (Q6)."""
    if not repo_scores:
        return

    from collections import Counter as _Counter

    explicit = [r for r in repo_scores if r["classification"] in ("strong_explicit", "weak_explicit")]
    if not explicit:
        return

    org_counts = _Counter(r["repo"].split("/")[0] for r in explicit)
    top = org_counts.most_common(20)
    if not top:
        return

    labels = [o for o, _ in reversed(top)]
    values = [v for _, v in reversed(top)]

    fig, ax = plt.subplots(figsize=(10, max(6, len(labels) * 0.37)))
    palette = sns.color_palette("mako_r", n_colors=len(labels))
    ax.barh(labels, values, color=palette)
    ax.set_xlabel(f"Repositories with explicit {technique_name} adoption")
    ax.set_title(f"Top Organisations / Users by Explicit {technique_name} Repository Count (Q6)")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    _save(fig, out_dir, "author_dist", fmt, dpi)


# ---------------------------------------------------------------------------
# 10. MT coverage depth within repos (Q7)
# ---------------------------------------------------------------------------

def plot_coverage_depth(findings: list, repo_scores: list, out_dir: Path, fmt: str, dpi: int, technique_name: str = "Technique") -> None:
    """Distribution of files-with-explicit-signals per repo, by tier (Q7)."""
    if not findings or not repo_scores:
        return

    from collections import defaultdict as _dd

    class_map = {r["repo"]: r["classification"] for r in repo_scores}
    files_per_repo: dict = _dd(set)

    for f in findings:
        repo = f.get("repo", "")
        tier = class_map.get(repo, "none")
        if tier in ("strong_explicit", "weak_explicit"):
            files_per_repo[(repo, tier)].add(f.get("file", ""))

    if not files_per_repo:
        return

    rows = [{"tier": tier, "files": len(files)} for (_, tier), files in files_per_repo.items()]
    df = pd.DataFrame(rows)

    bin_edges  = [0, 1, 2, 5, 10, 20, float("inf")]
    bin_labels = ["1", "2", "3–5", "6–10", "11–20", ">20"]
    df["bin"] = pd.cut(df["files"], bins=bin_edges, labels=bin_labels, right=True)

    pivot = (
        df.groupby(["bin", "tier"])
        .size()
        .unstack(fill_value=0)
        .reindex(bin_labels)
    )
    # Ensure both tiers are present
    for tier in ("strong_explicit", "weak_explicit"):
        if tier not in pivot.columns:
            pivot[tier] = 0
    pivot = pivot[["strong_explicit", "weak_explicit"]]

    fig, ax = plt.subplots(figsize=(9, 5))
    pivot.plot(
        kind="bar", ax=ax, stacked=True,
        color=[PALETTE["strong_explicit"], PALETTE["weak_explicit"]],
        edgecolor="white", linewidth=0.5,
    )
    ax.set_xlabel(f"Number of files with explicit {technique_name} signals per repository")
    ax.set_ylabel("Number of repositories")
    ax.set_title(f"{technique_name} Coverage Depth within Repositories (Q7)")
    ax.legend(
        [t.replace("_", " ").title() for t in ["strong_explicit", "weak_explicit"]],
        title="Tier", fontsize=9,
    )
    ax.set_xticklabels(bin_labels, rotation=0)
    _save(fig, out_dir, "coverage_depth", fmt, dpi)


# ---------------------------------------------------------------------------
# 10. Repos matched per search query (coloured by surface)
# ---------------------------------------------------------------------------

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


def _query_display(label: str) -> str:
    for prefix in ("code_", "commit_", "issue_", "pr_", "repo_"):
        if label.startswith(prefix):
            term = label[len(prefix):].replace("_", " ")
            return f"{prefix[:-1].upper()}: {term}"
    clean = label.strip('"')[:45]
    return f"DISCUSSION: {clean}"


def _build_raw_to_surface(summary: dict | None) -> dict[str, str]:
    """Map raw query string → surface type using summary.json as ground truth.
    When the same raw query appears on multiple surfaces, the highest-priority
    surface wins (code > repo > commit > issue > pr > discussion).
    """
    priority = {"code": 0, "repo": 1, "commit": 2, "issue": 3, "pr": 4, "discussion": 5}
    out: dict[str, str] = {}
    for q in (summary or {}).get("queries", []):
        raw     = q.get("query", "")
        surface = q.get("type", "discussion")
        if raw not in out or priority.get(surface, 99) < priority.get(out[raw], 99):
            out[raw] = surface
    return out


def _build_raw_to_label(summary: dict | None) -> dict[str, str]:
    """Map raw query string → label using summary.json.
    Prefers non-discussion labels when the same raw query appears on multiple surfaces.
    """
    priority = {"code": 0, "repo": 1, "commit": 2, "issue": 3, "pr": 4, "discussion": 5}
    out: dict[str, str] = {}
    for q in (summary or {}).get("queries", []):
        raw     = q.get("query", "")
        label   = q.get("label", raw)
        surface = q.get("type", "discussion")
        if raw not in out or priority.get(surface, 99) < priority.get(
            priority.get(_query_surface(out[raw]), 99), 99
        ):
            out[raw] = label
    return out


def plot_query_repos(repo_scores: list, summary: dict | None, out_dir: Path, fmt: str, dpi: int) -> None:
    """Distinct repos in the analysed set matched per search query, coloured by surface."""
    if not repo_scores:
        return

    # Build lookup from raw query strings (what found_by_queries actually stores in
    # existing data) to surface type and a display label.
    raw_to_surface = _build_raw_to_surface(summary)
    raw_to_label   = _build_raw_to_label(summary)

    repos_per_query: Counter = Counter()
    for r in repo_scores:
        for entry in r.get("found_by_queries", []):
            # entry may be a label (new data) or a raw query string (old data)
            repos_per_query[entry] += 1

    if not repos_per_query:
        return

    def _surface(entry: str) -> str:
        # New data: entry is already a label with a known prefix
        s = _query_surface(entry)
        if s != "discussion":
            return s
        # Old data: entry is a raw string — look it up in the summary map
        return raw_to_surface.get(entry, "discussion")

    def _display(entry: str) -> str:
        s = _query_surface(entry)
        if s != "discussion":
            # Already a label; strip the prefix and un-underscore
            return _query_display(entry)
        # Raw string — use the label from summary if available, else show raw
        lbl = raw_to_label.get(entry, "")
        if lbl and lbl != "discussion":
            return _query_display(lbl)
        # Discussion or unknown — show the raw query stripped of quotes
        clean = entry.strip('"')[:45]
        return f"DISCUSSION: {clean}"

    # Sort ascending so largest bar is at top
    items       = sorted(repos_per_query.items(), key=lambda x: x[1])
    disp_labels = [_display(e) for e, _ in items]
    values      = [cnt for _, cnt in items]
    colors      = [_SURFACE_COLORS.get(_surface(e), "#aaaaaa") for e, _ in items]

    fig, ax = plt.subplots(figsize=(12, max(8, len(items) * 0.32)))
    ax.barh(disp_labels, values, color=colors)
    ax.set_xlabel("Distinct repos matched (in analysed set)")
    ax.set_title("Repos Matched per Search Query")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    from matplotlib.patches import Patch
    surfaces_used = {_surface(e) for e, _ in items}
    legend_handles = [
        Patch(facecolor=_SURFACE_COLORS[s], label=s.capitalize())
        for s in ("repo", "code", "commit", "issue", "pr", "discussion")
        if s in surfaces_used
    ]
    ax.legend(handles=legend_handles, title="Search surface", loc="lower right", fontsize=9)

    _save(fig, out_dir, "query_repos", fmt, dpi)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(out_dir: Path, fmt: str, dpi: int, profile=None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir      = profile.results_dir / "raw"
    analysis_dir = profile.results_dir / "analysis"
    tech         = profile.name if profile else "Technique"

    data = load_all(raw_dir, analysis_dir)

    console.rule(f"[bold blue]Generating plots — {tech}[/]")
    plot_query_hits(         data["summary"],                      out_dir, fmt, dpi, tech)
    plot_classification_dist(data["repo_scores"],                  out_dir, fmt, dpi, tech)
    plot_yearly_trend(       data["repo_scores"],                  out_dir, fmt, dpi, tech)
    plot_language_dist(      data["repo_scores"],                  out_dir, fmt, dpi, tech)
    plot_stars_scatter(      data["repo_scores"],                  out_dir, fmt, dpi, tech)
    plot_pattern_freq(       data["findings"],                     out_dir, fmt, dpi, tech)
    plot_query_overlap(      data["repo_scores"],                  out_dir, fmt, dpi)
    plot_author_dist(        data["repo_scores"],                  out_dir, fmt, dpi, tech)
    plot_coverage_depth(     data["findings"], data["repo_scores"],out_dir, fmt, dpi, tech)
    plot_query_repos(        data["repo_scores"], data["summary"],  out_dir, fmt, dpi)

    console.print(f"\n[bold green]Done.[/]  All plots saved to [dim]{out_dir}[/]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4: generate plots from mining results")
    parser.add_argument("--technique",   required=True,
                        help="Path to technique YAML file (e.g. techniques/metamorphic_testing.yaml)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory (default: results/<slug>/plots/)")
    parser.add_argument("--dpi",        type=int,  default=150)
    parser.add_argument("--format",     choices=["png", "pdf", "svg"], default="png")
    args = parser.parse_args()

    from config import load_technique
    profile = load_technique(args.technique)
    out_dir = args.output_dir or (profile.results_dir / "plots")
    run(out_dir, args.format, args.dpi, profile=profile)


if __name__ == "__main__":
    main()
