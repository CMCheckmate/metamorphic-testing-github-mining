"""
Specialised report (last step)
==============================
Aggregates everything collected by search.py, code_specialised_analysis.py and
non_code_specialised_analysis.py into results/<slug>/analysis/overall.json["sections"] and
renders results/<slug>/sections_report/:

  sections_report.md (+ plots/)   the tables and plots used in the report
  sections_issues.md               caveats, decisions, data sources
  sections_samples.md              repository / commit lists for manual checking
  sections_excluded.md             every search result treated as not found, with the reason
  usage_repos_for_review.csv       MT only

Local only (no API, no cloning); safe to rerun at any time — missing inputs are listed as
actions in sections_issues.md.

Usage:
  python specialised_report.py -t mt
  python specialised_report.py -t pbt
  python specialised_report.py -t fuzz
"""

from __future__ import annotations

import argparse
import time

from core_helpers.utils import resolve_technique, technique_dirs, setup_logging


def report_mt(slug: str) -> None:
    from full_analysis import analysis
    from report_helpers import sections_report
    dirs = technique_dirs(slug)
    analysis._aggregate_overall(slug, dirs, setup_logging(slug, "specialised_report"))
    sections_report.run(slug)


def report_other(slug: str) -> None:
    from report_helpers import other_techniques_aggregate, other_techniques_report
    other_techniques_aggregate.aggregate(slug)
    other_techniques_report.run(slug)


def main() -> None:
    p = argparse.ArgumentParser(description="Aggregate and render the sections report.")
    p.add_argument("--technique", "-t", required=True, help="mt / pbt / fuzz (or full slug)")
    slug = resolve_technique(p.parse_args().technique)
    t0 = time.time()
    (report_mt if slug == "metamorphic_testing" else report_other)(slug)
    print(f"Done in {(time.time() - t0) / 60:.1f} min.")


if __name__ == "__main__":
    main()
