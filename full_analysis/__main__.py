"""
GitHub Mining Pipeline — CLI Entry Point
=========================================
Phases: search -> analysis -> report. Technique-specific vocabulary lives in inputs/.

Full analysis: the original clone-everything pipeline. It clones every CODE-surface repository
(with history) and scans every file, producing far more data (commit spans, per-file details,
word clouds, report.md) than the sections report uses, and takes days instead of hours. The
sections report is produced by the specialised pipeline in the project root (see README.md).

Usage examples:
  python -m full_analysis --technique mt --phase search
  python -m full_analysis --technique pbt --phase analysis --code-only
  python -m full_analysis --technique fuzz --phase analysis --noncode-only
  python -m full_analysis --technique mt --phase analysis --restart
  python -m full_analysis --technique mt --phase report
  python -m full_analysis --technique mt                  # all phases in sequence

Techniques:  mt / metamorphic_testing
             fuzz / fuzz_testing
             pbt / property_based_testing

Phases:      search | analysis | report   (omit to run all three)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from core_helpers import config as cfg
from core_helpers.utils import resolve_technique, ensure_dirs, technique_dirs


def _elapsed(t0: float) -> str:
    s = int(time.time() - t0)
    m, s = divmod(s, 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _run_search(slug: str, overwrite: bool) -> None:
    from core_helpers import github_search as search
    print(f"\n=== SEARCH phase — {slug} ===")
    t0 = time.time()
    search.run(slug, overwrite=overwrite)
    print(f"Search done in {_elapsed(t0)}")


def _run_analysis(
    slug: str,
    restart: bool,
    code_only: bool,
    noncode_only: bool,
    workers: int,
    aggregate_only: bool,
    no_size_stats: bool = False,
) -> None:
    from full_analysis import analysis
    print(f"\n=== ANALYSIS phase — {slug} ===")
    t0 = time.time()
    analysis.run(
        slug,
        code_only=code_only,
        noncode_only=noncode_only,
        restart=restart,
        workers=workers,
        aggregate_only=aggregate_only,
        no_size_stats=no_size_stats,
    )
    print(f"Analysis done in {_elapsed(t0)}")


def _run_report(slug: str) -> None:
    from full_analysis import report
    print(f"\n=== REPORT phase — {slug} ===")
    t0 = time.time()
    report.run(slug)
    print(f"Report done in {_elapsed(t0)}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m full_analysis",
        description="GitHub Mining Pipeline — study testing technique adoption.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Technique
    p.add_argument(
        "--technique", "-t", required=True, metavar="TECHNIQUE",
        help="Technique: mt / metamorphic_testing, fuzz / fuzz_testing, pbt / property_based_testing",
    )

    # Phase
    p.add_argument(
        "--phase", choices=["search", "analysis", "report"], default=None,
        help="Phase to run. Omit to run all phases in sequence.",
    )

    # Search options
    sg = p.add_argument_group("Search options")
    sg.add_argument(
        "--overwrite", action="store_true",
        help="Reset search history and result files before searching.",
    )

    # Analysis options
    ag = p.add_argument_group("Analysis options")
    ag.add_argument(
        "--restart", action="store_true",
        help="Reset all analysis data and history files before running.",
    )
    ag.add_argument(
        "--code-only", action="store_true",
        help="Run code analysis only (skip non-code surface analysis).",
    )
    ag.add_argument(
        "--noncode-only", action="store_true",
        help="Run non-code analysis only (skip cloning and file scanning).",
    )
    ag.add_argument(
        "--workers", type=int, default=cfg.ANALYSIS_WORKERS, metavar="N",
        help=f"Worker processes for parallel file scanning (default: {cfg.ANALYSIS_WORKERS}).",
    )
    ag.add_argument(
        "--aggregate-only", action="store_true",
        help="Skip cloning and scanning. Aggregate whatever is already in code_repos.json "
             "and noncode_results.json into overall.json and exit.",
    )
    ag.add_argument(
        "--no-size-stats", action="store_true",
        help="Skip fetching repo metadata (size statistics will be unavailable for non-REPOS surfaces).",
    )

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.code_only and args.noncode_only:
        parser.error("--code-only and --noncode-only are mutually exclusive.")
    if args.aggregate_only and (args.restart or args.code_only or args.noncode_only):
        parser.error("--aggregate-only cannot be combined with --restart, --code-only, or --noncode-only")

    try:
        slug = resolve_technique(args.technique)
    except ValueError as exc:
        parser.error(str(exc))
        return  # unreachable; quiets type checkers

    ensure_dirs(slug)

    # Set up root logger to console
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    t_total = time.time()
    phases = [args.phase] if args.phase else ["search", "analysis", "report"]

    for phase in phases:
        if phase == "search":
            _run_search(slug, overwrite=args.overwrite)
        elif phase == "analysis":
            _run_analysis(
                slug,
                restart=args.restart,
                code_only=args.code_only,
                noncode_only=args.noncode_only,
                workers=args.workers,
                aggregate_only=args.aggregate_only,
                no_size_stats=args.no_size_stats,
            )
        elif phase == "report":
            _run_report(slug)

    print(f"\nPipeline complete in {_elapsed(t_total)}.")


if __name__ == "__main__":
    main()
