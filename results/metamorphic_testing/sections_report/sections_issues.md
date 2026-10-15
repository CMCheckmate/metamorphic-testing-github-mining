# Metamorphic Testing — Issues, Caveats & Verification

_Generated 2026-10-16 09:50. Companion to [sections_report.md](sections_report.md)._

## Actions, decisions and caveats

| # | Section | Type | Note |
| --- | --- | --- | --- |
| 1 | A2 | Action needed | 2 repos failed to clone (connection stalled or timed out) and are excluded. Re-run the shard's command to retry them, then --merge and specialised_report.py. |
| 2 | A3 | Action needed | Manually classify the usage repositories (fill `manual_label` in usage_repos_for_review.csv). |
| 3 | S1 | Caveat | CODE "metamorphic testing": 9,536 raw < 10,419 collected — GitHub's `total_count` is an estimate; raw hits are approximate. |
| 4 | A3 | Caveat | Test files = filename pattern (test_*.py, *_test.go, *Test.java, *.spec.ts…), pytest/JUnit import or `@Test`, or a test/tests/testing/spec/e2e directory in the repo-relative path. Languages without such rules (C/C++, Haskell, plain JS) rely on directories; Rust inline `#[cfg(test)]` modules do not make a source file a test file. |
| 5 | A5 | Caveat | GitHub-wide counts come from repository search `total_count` (approximate) and only count each repository's primary language. |
| 6 | A6 | Caveat | Heuristic keyword matching; verify with the 10 random repos per domain in sections_samples.md. Generic keywords (api, rest, react, query, security…) still match broadly; a README needs ≥3 different keywords of a domain to count. |
| 7 | T8 | Caveat | Creation year of 3 of 1,156 repositories estimated from the GitHub repository ID (IDs are assigned in creation order), interpolated between 29,809 repositories with known creation dates; correct year for 100.0% of 3,000 known repositories checked this way. |
| 8 | T9 | Caveat | Commit search covers default branches only, was date-sliced 2010-01-01 → 2026-09-01, and keeps fork duplicates (same SHA) once. |
| 9 | S1 | Verified / resolved | Results found only by `"@metamorphic"` are excluded (GitHub ignores the '@' and searches the bare word); all-keyword figures are in the S1/S2 section below. |
| 10 | S1 | Verified / resolved | Search truncation: 3 queries hit GitHub's 1,000-result cap (PRS "metamorphic test" 2026-05-30..2026-09-01 (1,000 of 1,913); PRS "metamorphic tests" 2026-05-30..2026-09-01 (1,000 of 1,447); COMMITS "metamorphic tests" 2026-02-24..2026-05-29 (1,000 of 1,036)). They were re-collected in finer time slices (`--fill-capped`): 484 items added; nothing is missing now. |
| 11 | A2 | Verified / resolved | 33 CODE repos found only by "@metamorphic" are not part of the search results (bare-word search). |
| 12 | A7 | Verified / resolved | README + description is less noisy: 12% vs 38% agent/process words among the top 50 (details below). |
| 13 | T9 | Verified / resolved | Commit-search coverage check: 64/148 sampled repos inactive >1 year, 6 archived. |
| 14 | T8/T9 | Verified / resolved | Surge and AI-share verification for 2026: see the T8/T9 section below. |

## Data sources

| Data source | Repos |
| --- | --- |
| Excluded from the search population (found only by "@metamorphic") | 33 |
| CODE-surface repositories found by search | 6,117 |
| No longer available now (deleted / private / disabled) | 146 |
| Current population | 5,971 |
| Analysed on the current snapshot (code_specialised_analysis.py) | 5,969 |
| Included (current snapshot has a technique hit) | 5,879 |
| Clone failed: stalled or timed out (retry by re-running the shard) | 2 |
| Not analysed | 2 |

_Method: see README.md (Reproducing the results)._

## S1/S2 — Results found only by excluded search keywords

_Search results found only by `"@metamorphic"` are left out of every section. Figures with them included, for reference:_

| Surface | Raw hits (all keywords) | Unique results (all keywords) | Distinct repos (all keywords) | Distinct repos (reported) |
| --- | --- | --- | --- | --- |
| CODE | 50,074 | 29,045 | 6,150 | 5,879 |
| REPOS | 1,269 | 476 | 476 | 230 |
| COMMITS | 53,706 | 7,692 | 2,037 | 1,156 |
| PRS | 15,187 | 5,436 | 1,437 | 507 |
| ISSUES | 9,728 | 4,076 | 1,124 | 453 |
| DISCUSSIONS | 149 | 71 | 35 | 8 |

## A7 — Does README + description reduce noise?

| Text used | Top-50 words that are agent/process words | Top-50 words in domain vocabulary | Top 10 words |
| --- | --- | --- | --- |
| Previous: relevant issue/PR/commit text + description + topics | 38.0% | 4.0% | model, state, gate, deterministic, contract, mutation, invariant, boundary, identical, python |
| Now: README + description | 12.0% | 2.0% | model, license, api, install, python, state, system, development, command, architecture |

## T8/T9 — Is the 2026 surge real, and is it AI-driven?

**Concentration.** 3,181 relevant commits in 2026 vs 243 in 2025. Capped at 5 per repo per month: 1,709 vs 216. Without the top 10 repositories: 1,870 vs 198. Distinct repositories: 945 vs 85. Repositories with their first technique-mentioning commit (T8): 937 vs 81. If the surge survives capping and top-10 removal, it is not driven by a few very active repositories.

**AI authorship (lower bound).** 1,888 of 3,181 relevant 2026 commits (59%) carry an AI-agent authorship line, from 470 repositories; in 2025: 39 of 243. Agents that leave no trailer (or users who remove it) are not counted, so the true share is higher. 50 random commits are listed in sections_samples.md for manual confirmation.

**Does commit search cover inactive repositories?** Of 148 sampled COMMITS-surface repositories, 64 had no push since 2025-09-01 (inactive >1 year) and 6 are archived. So commit search is **not** limited to recently active repositories (unlike code search).

**Creation year by surface.** GitHub code search only indexes repositories active (or returned in search results) in the last year, which is why CODE-surface data is not used for the timeline. Share of repositories created in 2026: CODE 56%, REPOS search 27%, COMMITS surface 70%. Commit search has no documented activity restriction, yet its repositories are even more concentrated in 2026 — so the concentration is mainly a genuine surge of new (largely agent-assisted) repositories rather than an artefact of the code-search index.
