"""
GitHub Mining Pipeline Orchestrator
=====================================
Runs the full 5-phase pipeline or any subset of phases for a specified testing technique.

Phases:
  1  Search   — query GitHub across 5 surfaces and write raw JSON results
  2  Clone    — filter candidates and shallow-clone qualifying repos
  3  Analyse  — walk cloned repos for technique patterns, score and classify
  4  Plot     — generate publication-quality figures from Phase 1 & 3 outputs
  5  Report   — generate comprehensive results report answering Q1–Q8

Usage examples:
  python main.py --technique techniques/metamorphic_testing.yaml
  python main.py --technique techniques/fuzzing.yaml --stages 1 2
  python main.py --technique techniques/property_based_testing.yaml --stages 3 4 5
  python main.py --technique techniques/metamorphic_testing.yaml --stages 5 --refresh-plots
  python main.py --technique techniques/mutation_testing.yaml --stages 2 3 --min-stars 5 --workers 8

Run  python main.py --help  for full parameter reference.
"""

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.rule import Rule

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _phase_header(n: int, title: str) -> None:
    console.print()
    console.print(Rule(f"[bold blue]Phase {n}: {title}[/]", style="blue"))
    console.print()


def _elapsed(t0: float) -> str:
    s = time.time() - t0
    m, s = divmod(int(s), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="GitHub Mining pipeline orchestrator — technique-agnostic.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # --- Technique selection (required) ---
    parser.add_argument(
        "--technique", required=True, metavar="YAML",
        help="Path to technique YAML file (e.g. techniques/metamorphic_testing.yaml)",
    )

    # --- Stage selection ---
    parser.add_argument(
        "--stages", nargs="+", type=int, choices=[1, 2, 3, 4, 5],
        default=[1, 2, 3, 4, 5], metavar="N",
        help="Phases to run (default: 1 2 3 4 5). Example: --stages 2 3",
    )

    # --- Phase 1: Search ---
    g1 = parser.add_argument_group("Phase 1 — Search")
    g1.add_argument(
        "--surfaces", nargs="+",
        choices=["repo", "code", "issues", "commits", "discussions"],
        default=["repo", "code", "issues", "commits", "discussions"],
        help="GitHub search surfaces to query (default: all five)",
    )
    g1.add_argument(
        "--no-slice", action="store_true",
        help="Disable adaptive date-range slicing (faster, may miss >1 000-result queries)",
    )
    g1.add_argument(
        "--max-pages", type=int, default=10,
        help="Maximum result pages per query / slice (default: 10)",
    )

    # --- Phase 2: Clone ---
    g2 = parser.add_argument_group("Phase 2 — Clone")
    g2.add_argument(
        "--min-stars", type=int, default=0,
        help="Skip repos with fewer than N stars (default: 0)",
    )
    g2.add_argument(
        "--skip-forks", action="store_true",
        help="Exclude forked repositories",
    )
    g2.add_argument(
        "--lang", type=str, default=None, metavar="LANG",
        help="Only clone repos whose primary language matches (e.g. Python)",
    )
    g2.add_argument(
        "--clone-limit", type=int, default=None, metavar="N",
        help="Cap the number of repos cloned in this run",
    )
    g2.add_argument(
        "--clone-source", choices=["repos", "code", "both"], default="both",
        help="Which Phase 1 output file(s) to pull clone candidates from (default: both)",
    )
    g2.add_argument(
        "--refresh", action="store_true",
        help="Re-clone repos that already exist locally",
    )

    # --- Phase 3: Analyse ---
    g3 = parser.add_argument_group("Phase 3 — Analyse")
    g3.add_argument(
        "--min-score", type=int, default=0,
        help="Only include repos with score >= N in output (default: 0)",
    )
    g3.add_argument(
        "--cleanup-clones", action="store_true",
        help="Delete each cloned repo after analysis to reclaim disk space",
    )
    g3.add_argument(
        "--append", action="store_true",
        help="Merge analysis results with any existing findings.json / repo_scores.json",
    )

    # --- Phase 4: Plot ---
    g4 = parser.add_argument_group("Phase 4 — Plot")
    g4.add_argument(
        "--format", choices=["png", "pdf", "svg"], default="png",
        help="Output format for plots (default: png)",
    )
    g4.add_argument(
        "--dpi", type=int, default=150,
        help="Resolution for raster plot outputs (default: 150)",
    )

    # --- Phase 5: Report ---
    g5 = parser.add_argument_group("Phase 5 — Report")
    g5.add_argument(
        "--report-output", type=Path, default=None, metavar="PATH",
        help="Output path for the results report (default: results/<slug>/analysis/summary_report.md)",
    )
    g5.add_argument(
        "--refresh-plots", action="store_true",
        help="Force-regenerate all plots before writing the report (Phase 5)",
    )
    g5.add_argument(
        "--top-repos", type=int, default=20, metavar="N",
        help="Number of top strong_explicit repos in the Q8 table (default: 20)",
    )

    # --- Performance ---
    gp = parser.add_argument_group("Performance")
    gp.add_argument(
        "--workers", type=int, default=4,
        help="Parallel worker threads for Phase 2 (clone) and Phase 3 (analyse) (default: 4)",
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()
    stages = sorted(set(args.stages))

    from config import load_technique
    profile = load_technique(args.technique)

    t_total = time.time()
    console.print(f"\n[bold]Mining Pipeline — {profile.name} ({profile.short_name})[/]  stages={stages}  workers={args.workers}\n")

    # ------------------------------------------------------------------ #
    # Phase 1 — Search                                                     #
    # ------------------------------------------------------------------ #
    if 1 in stages:
        _phase_header(1, "Search")
        t0 = time.time()
        try:
            import search as search_phase
        except ImportError as e:
            console.print(f"[red]Cannot import search.py: {e}[/]"); sys.exit(1)

        surfaces = set(args.surfaces)
        search_phase.run(
            do_repos       ="repo"        in surfaces,
            do_code        ="code"        in surfaces,
            do_issues      ="issues"      in surfaces,
            do_commits     ="commits"     in surfaces,
            do_discussions ="discussions" in surfaces,
            max_pages      =args.max_pages,
            enable_slicing =not args.no_slice,
            profile        =profile,
        )
        console.print(f"\n[dim]Phase 1 done in {_elapsed(t0)}[/]")

    # ------------------------------------------------------------------ #
    # Phase 2 — Clone                                                      #
    # ------------------------------------------------------------------ #
    if 2 in stages:
        _phase_header(2, "Clone")
        t0 = time.time()
        try:
            import clone as clone_phase
        except ImportError as e:
            console.print(f"[red]Cannot import clone.py: {e}[/]"); sys.exit(1)

        clone_phase.run(
            source    =args.clone_source,
            limit     =args.clone_limit,
            offset    =0,
            refresh   =args.refresh,
            min_stars =args.min_stars,
            skip_forks=args.skip_forks,
            lang      =args.lang,
            workers   =args.workers,
            profile   =profile,
        )
        console.print(f"\n[dim]Phase 2 done in {_elapsed(t0)}[/]")

    # ------------------------------------------------------------------ #
    # Phase 3 — Analyse                                                    #
    # ------------------------------------------------------------------ #
    if 3 in stages:
        _phase_header(3, "Analyse")
        t0 = time.time()
        try:
            import analyze as analyze_phase
        except ImportError as e:
            console.print(f"[red]Cannot import analyze.py: {e}[/]"); sys.exit(1)

        analyze_phase.run(
            target_repo=None,
            min_score  =args.min_score,
            out_dir    =profile.results_dir / "analysis",
            workers    =args.workers,
            append     =args.append,
            cleanup    =args.cleanup_clones,
            profile    =profile,
        )
        console.print(f"\n[dim]Phase 3 done in {_elapsed(t0)}[/]")

    # ------------------------------------------------------------------ #
    # Phase 4 — Plot                                                       #
    # ------------------------------------------------------------------ #
    if 4 in stages:
        _phase_header(4, "Plot")
        t0 = time.time()
        try:
            import plot as plot_phase
        except ImportError as e:
            console.print(f"[red]Cannot import plot.py: {e}[/]"); sys.exit(1)

        plot_phase.run(
            out_dir =profile.results_dir / "plots",
            fmt     =args.format,
            dpi     =args.dpi,
            profile =profile,
        )
        console.print(f"\n[dim]Phase 4 done in {_elapsed(t0)}[/]")

    # ------------------------------------------------------------------ #
    # Phase 5 — Report                                                    #
    # ------------------------------------------------------------------ #
    if 5 in stages:
        _phase_header(5, "Report")
        t0 = time.time()
        try:
            import report as report_phase
        except ImportError as e:
            console.print(f"[red]Cannot import report.py: {e}[/]"); sys.exit(1)

        out_path = args.report_output or (profile.results_dir / "analysis" / "summary_report.md")
        report_phase.run(
            results_dir   =profile.results_dir,
            out_path      =out_path,
            plots_dir     =profile.results_dir / "plots",
            refresh_plots =args.refresh_plots,
            top_n         =args.top_repos,
            fmt           =args.format,
            dpi           =args.dpi,
            profile       =profile,
        )
        console.print(f"\n[dim]Phase 5 done in {_elapsed(t0)}[/]")

    # ------------------------------------------------------------------ #
    # Done                                                                 #
    # ------------------------------------------------------------------ #
    console.print()
    console.print(Rule(style="green"))
    console.print(f"[bold green]Pipeline complete[/]  total time: [cyan]{_elapsed(t_total)}[/]\n")


if __name__ == "__main__":
    main()
