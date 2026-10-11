"""
Search (step 1)
===============
GitHub search on six surfaces (code, repositories, commits, pull requests, issues,
discussions) with the keywords in inputs/<prefix>_search_keywords.txt. Queries are split
by date / file size to work around GitHub's 1,000-results-per-query limit.

Output: results/<slug>/search/{code,repos,commits,prs,issues,discussions}.json,
summary.json, search_history.json and results/<slug>/search.log. Resumable: rerun the
same command to continue; --overwrite starts again from scratch.

Usage:
  python search.py -t mt
  python search.py -t pbt --overwrite
"""

from __future__ import annotations

import argparse
import time

from core_helpers import github_search
from core_helpers.utils import resolve_technique, ensure_dirs


def main() -> None:
    p = argparse.ArgumentParser(description="GitHub search on all six surfaces for one technique.")
    p.add_argument("--technique", "-t", required=True, help="mt / pbt / fuzz (or full slug)")
    p.add_argument("--overwrite", action="store_true", help="Reset search history and result files first.")
    a = p.parse_args()
    slug = resolve_technique(a.technique)
    ensure_dirs(slug)
    t0 = time.time()
    github_search.run(slug, overwrite=a.overwrite)
    print(f"Search done in {(time.time() - t0) / 60:.1f} min.")


if __name__ == "__main__":
    main()
