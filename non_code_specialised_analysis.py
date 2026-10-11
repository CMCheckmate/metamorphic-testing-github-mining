"""
Non-code specialised analysis (data collection that needs no cloning)
======================================================================
Every data-collection step for the sections report other than cloning, selected with flags.
Run the flags in the order listed (several can be given at once; they run in this order).

  --prepare            PBT / fuzz only, local (no API): keep explicit-phrase search results,
                       check every non-code title/body for a technique phrase, draw the ±3% / 95%
                       random samples (CODE scan + A6/A7) -> results/<slug>/filtered/, analysis/*_sample.json
  --metadata           repository metadata (language, creation date, size, description):
                       MT -> every repository found by the search; PBT / fuzz -> both samples
  --readmes            READMEs (A6/A7): MT -> verified non-CODE repositories; PBT / fuzz -> A6/A7 sample
  --lang-baseline      GitHub-wide primary-language counts (A5 normalisation). PBT / fuzz reuse
                       the MT file (the counts do not depend on the technique) and add missing languages
  --commit-coverage    MT only: checks that commit search also returns repositories inactive for over
                       a year (T8/T9 verification; ~150 calls)
  --commit-sampling M  PBT / fuzz only: corrects the COMMITS surface where the search hit GitHub's
                       1,000-result cap. M = estimate | agent | adoption | status (see below)

All steps except --prepare use the GitHub API (GITHUB_TOKEN in .env) and are resumable:
rerun the same command to continue.

Commit sampling (search API, ~24 requests/min on one token):
  --commit-sampling estimate            pilot + time projection per option
  --commit-sampling agent               agent-marked share 2025–2026 (target ±3 percentage points)
  --commit-sampling adoption            repositories per year of their first technique commit
                                        (target ±10% relative; --target 0.2 for ±20%)
  --commit-sampling status              current estimates, no requests
  options: --exhaustive (download everything: exact), --years 2024 2025 2026, --max-hours 3

Examples:
  python non_code_specialised_analysis.py -t mt --metadata --readmes --lang-baseline --commit-coverage
  python non_code_specialised_analysis.py -t pbt --prepare
  python non_code_specialised_analysis.py -t pbt --metadata --readmes --lang-baseline
  python non_code_specialised_analysis.py -t pbt --commit-sampling adoption --exhaustive
  python non_code_specialised_analysis.py -t fuzz --commit-sampling agent
"""

from __future__ import annotations

import argparse

from core_helpers import config as cfg
from core_helpers.utils import resolve_technique, technique_dirs, setup_logging


def main() -> None:
    p = argparse.ArgumentParser(description="Non-code data collection for the sections report (no cloning).",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--technique", "-t", required=True, help="mt / pbt / fuzz (or full slug)")
    p.add_argument("--prepare", action="store_true", help="PBT/fuzz: filter search results and draw the samples (local).")
    p.add_argument("--metadata", action="store_true", help="Repository metadata (MT: all repos; PBT/fuzz: samples).")
    p.add_argument("--readmes", action="store_true", help="READMEs for A6/A7.")
    p.add_argument("--lang-baseline", action="store_true", help="GitHub-wide language counts (A5).")
    p.add_argument("--commit-coverage", action="store_true", help="MT: commit-search coverage check (T8/T9).")
    p.add_argument("--commit-sampling", choices=["estimate", "agent", "adoption", "status"],
                   help="PBT/fuzz: correct the COMMITS surface for GitHub's 1,000-result cap.")
    p.add_argument("--years", type=int, nargs="*", help="commit sampling: limit to these years.")
    p.add_argument("--target", type=float, help="commit sampling: agent ± share (default 0.03); adoption ± relative (default 0.10).")
    p.add_argument("--exhaustive", action="store_true", help="commit sampling: download every window (exact).")
    p.add_argument("--max-hours", type=float, default=0, help="commit sampling: stop after about this many hours.")
    p.add_argument("--pilot", type=int, default=6, help="commit sampling estimate: windows per year in the pilot.")
    a = p.parse_args()
    if not (a.prepare or a.metadata or a.readmes or a.lang_baseline or a.commit_coverage or a.commit_sampling):
        p.error("choose at least one step (see --help)")

    slug = resolve_technique(a.technique)
    mt = slug == "metamorphic_testing"
    dirs, logger = technique_dirs(slug), setup_logging(slug, "non_code_specialised_analysis")
    if mt and (a.prepare or a.commit_sampling):
        p.error("--prepare and --commit-sampling are for PBT / fuzz (MT's search was not capped and uses all repos).")
    if not mt and a.commit_coverage:
        p.error("--commit-coverage is checked once, on MT.")
    needs_api = a.metadata or a.readmes or a.lang_baseline or a.commit_coverage or (a.commit_sampling not in (None, "status"))
    if needs_api and not cfg.GITHUB_TOKEN:
        p.error("GITHUB_TOKEN is not set (.env).")

    from core_helpers import github_fetch as gf
    from core_helpers import technique_data as td
    if a.prepare:
        td.prepare(slug)
    if a.metadata:
        gf.fetch_metadata(slug, logger) if mt else td.fetch_sample_metadata(slug, logger)
    if a.readmes:
        gf.fetch_readmes(dirs, logger) if mt else td.fetch_sample_readmes(slug, logger)
    if a.lang_baseline:
        gf.fetch_lang_baseline(dirs, logger) if mt else td.fetch_lang_baseline(slug, logger)
    if a.commit_coverage:
        gf.fetch_commit_coverage(dirs, logger)
    if a.commit_sampling:
        from core_helpers import commit_sampling as cs
        if a.commit_sampling == "status":
            est = cs.compute_estimates(slug)
            if not est:
                print("Nothing sampled yet. Start with --commit-sampling estimate (or agent / adoption).")
            else:
                for m in ("agent", "adoption"):
                    cs._print(est, m, sorted(est.get(m, {})), 0, 0)
        elif a.commit_sampling == "estimate":
            cs.estimate_time(slug, a.pilot, a.target or 0.03, [0.10, 0.20], a.years)
        else:
            cs.run(a.commit_sampling, slug, a.years, a.target or (0.03 if a.commit_sampling == "agent" else 0.10),
                   a.exhaustive, a.max_hours)
    print(f"Next: python specialised_report.py -t {a.technique}")


if __name__ == "__main__":
    main()
