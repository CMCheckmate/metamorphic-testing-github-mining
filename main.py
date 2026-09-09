"""
GitHub Mining Pipeline — CLI Entry Point
=========================================
Three phases: search → analysis → report.
Technique-specific vocabulary lives in inputs/ keyword files.

Usage examples:
  python main.py --technique mt --phase search
  python main.py --technique mt --phase search --overwrite
  python main.py --technique pbt --phase analysis --code-only
  python main.py --technique fuzz --phase analysis --noncode-only
  python main.py --technique mt --phase analysis --restart
  python main.py --technique mt --phase report
  python main.py --technique mt                  # all phases in sequence

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

import config as cfg
from utils import resolve_technique, ensure_dirs, technique_dirs


def _elapsed(t0: float) -> str:
    s = int(time.time() - t0)
    m, s = divmod(s, 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _run_search(slug: str, overwrite: bool) -> None:
    import search
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
) -> None:
    import analysis
    print(f"\n=== ANALYSIS phase — {slug} ===")
    t0 = time.time()
    analysis.run(
        slug,
        code_only=code_only,
        noncode_only=noncode_only,
        restart=restart,
        workers=workers,
    )
    print(f"Analysis done in {_elapsed(t0)}")


def _run_report(slug: str) -> None:
    import report
    print(f"\n=== REPORT phase — {slug} ===")
    t0 = time.time()
    report.run(slug)
    print(f"Report done in {_elapsed(t0)}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
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

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.code_only and args.noncode_only:
        parser.error("--code-only and --noncode-only are mutually exclusive.")

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
            )
        elif phase == "report":
            _run_report(slug)

    print(f"\nPipeline complete in {_elapsed(t_total)}.")


if __name__ == "__main__":
    main()
