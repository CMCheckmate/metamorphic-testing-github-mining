# Fuzz Testing — Issues, Caveats & Verification

_Generated 2026-10-16 09:51. Companion to [sections_report.md](sections_report.md)._

## Actions, decisions and caveats

| # | Section | Type | Note |
| --- | --- | --- | --- |
| 1 | S1 | Decision / assumption | Only explicit technique phrases are counted (team decision); results found only by 26 tool/library/API keywords are excluded. All-keyword figures are in the S1/S2 section below. |
| 2 | S2 | Decision / assumption | CODE repositories cannot all be verified without scanning every one; the CODE row is estimated from the random sample, and the union / overlap use the non-CODE surfaces only. |
| 3 | A3 | Decision / assumption | No manual classification for this technique (team decision); 15 random usage repositories with strong signals are listed in sections_samples.md. |
| 4 | S1 | Caveat | GitHub's 1,000-result cap truncated search slices on CODE, REPOS, COMMITS, PRS, ISSUES: counts on these surfaces are lower bounds (completeness per surface in S1 and the section below). |
| 5 | S1 | Caveat | CODE "fuzz test": 215,040 raw < 240,552 collected — GitHub's `total_count` is an estimate; raw hits are approximate. |
| 6 | S1 | Caveat | Search truncation: GitHub returns ≤1,000 results per query; queries were split by date/size until each piece had <900 results, but an unsplittable piece is truncated to 1,000. |
| 7 | A2 | Caveat | Estimated population counts = share of sampled repositories whose state is known (hit, no hit or deleted) × the CODE repositories found by search. |
| 8 | A3 | Caveat | Test files = filename pattern (test_*.py, *_test.go, *Test.java, *.spec.ts…), pytest/JUnit import or `@Test`, or a test/tests/testing/spec/e2e directory in the repo-relative path. |
| 9 | A5 | Caveat | GitHub-wide counts come from repository search `total_count` (approximate) and only count each repository's primary language. |
| 10 | A6 | Caveat | Heuristic keyword matching; verify with the 10 random repos per domain in sections_samples.md. Generic keywords (api, rest, react, query, security…) still match broadly; a README needs ≥3 different keywords of a domain to count. |
| 11 | T8 | Caveat | Creation year of 13,016 of 13,355 repositories estimated from the GitHub repository ID (IDs are assigned in creation order), interpolated between 29,809 repositories with known creation dates; correct year for 100.0% of 3,000 known repositories checked this way. 12 could not be dated. |
| 12 | T9 | Caveat | Commit search covers default branches only, was date-sliced 2010-01-01 → 2026-09-01, and keeps fork duplicates (same SHA) once. |
| 13 | T8/T9 | Caveat | Commit search hit the 1,000-result cap in 17 of 17 years (2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026). Commit counts, first-commit repo counts and agent shares for these years are lower bounds, and year-to-year changes between capped and uncapped years are not comparable. |
| 14 | T8/T9 | Verified / resolved | Surge and AI-share verification for 2026: see the T8/T9 section below. |

## Data sources

| Data source | Value |
| --- | --- |
| Search keywords kept (explicit phrases) | 16 |
| Search keywords excluded (tool / library / API) | 26 |
| Search keywords never run | 0 |
| CODE population (repos) | 255,740 |
| CODE sample drawn / analysed / unavailable / failed | 1,149 / 1,140 / 9 / 0 |
| Verified non-CODE repos (population) / A6–A7 sample drawn / counted | 55,281 / 1,131 / 1,126 |
| Sample seed | 20261011 |
| Search data prepared | 2026-10-11T03:05:46+00:00 |

_Analysis keywords (`inputs/fuzz_analysis_keywords.json`):_

| Keyword | Regex | Subset of |
| --- | --- | --- |
| fuzz test(ing) | `(?<![A-Za-z0-9])fuzz[\s-]+test(?:ing\|s\|ers?)?(?![A-Za-z0-9])` |  |
| fuzzing | `(?<![A-Za-z0-9])fuzzing(?![A-Za-z0-9])` |  |
| fuzz target | `(?<![A-Za-z0-9])fuzz[\s-]+targets?(?![A-Za-z0-9])` |  |
| fuzz harness | `(?<![A-Za-z0-9])fuzz[\s-]+harness(?:es)?(?![A-Za-z0-9])` |  |
| fuzz corpus | `(?<![A-Za-z0-9])fuzz[\s-]+corp(?:us\|ora\|uses)(?![A-Za-z0-9])` |  |
| coverage-guided fuzzing | `(?<![A-Za-z0-9])coverage[\s-]+guided[\s-]+fuzzing(?![A-Za-z0-9])` | phrase_fuzzing |
| greybox fuzzing | `(?<![A-Za-z0-9])gr[ae]y[\s-]*box[\s-]+fuzzing(?![A-Za-z0-9])` | phrase_fuzzing |
| blackbox fuzzing | `(?<![A-Za-z0-9])black[\s-]*box[\s-]+fuzzing(?![A-Za-z0-9])` | phrase_fuzzing |
| grammar-based fuzzing | `(?<![A-Za-z0-9])grammar[\s-]+based[\s-]+fuzzing(?![A-Za-z0-9])` | phrase_fuzzing |
| structure-aware fuzzing | `(?<![A-Za-z0-9])structure[\s-]+aware[\s-]+fuzzing(?![A-Za-z0-9])` | phrase_fuzzing |
| comment: fuzz test | `(?:#\|//).*(?<![A-Za-z0-9])fuzz[\s-]+test(?:ing\|s\|ers?)?(?![A-Za-z0-9])` | phrase_fuzz_test |

_Method: see README.md (Reproducing the results)._

## S1/T9 — Search completeness (GitHub's 1,000-result cap)

_From search.log, kept keywords only. A slice is capped when GitHub reported more results than the 1,000 it returns. GitHub's total also counts fork copies of the same commit/PR and, for commit search, loose matches of the words, so 'retrieved %' understates completeness. The last column is the share of the items returned by capped slices whose title/body contains a technique phrase: close to 100% means the cap cut off relevant results._

| Surface | Slices | Capped | GitHub total | Retrieved | Retrieved % | Capped slices: relevant items |
| --- | --- | --- | --- | --- | --- | --- |
| CODE | 2,977 | 76 | 1,816,401 | 1,678,220 | 92.4% | n/a |
| REPOS | 37 | 2 | 15,481 | 15,053 | 97.2% | 63.1% of 2,000 |
| COMMITS | 380 | 268 | 19,417,653 | 308,482 | 1.6% | 88.0% of 40,061 |
| PRS | 159 | 74 | 978,270 | 117,947 | 12.1% | 73.2% of 73,992 |
| ISSUES | 135 | 32 | 153,087 | 93,826 | 61.3% | 75.8% of 31,982 |
| DISCUSSIONS | 22 | 0 | 3,558 | 3,558 | 100.0% | — |

## S1/S2 — Results found only by excluded search keywords

_Excluded (tool / library / API keywords (explicit phrases only)): `"-fsanitize=fuzzer"`, `"ClusterFuzz"`, `"FUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION"`, `"FuzzedDataProvider"`, `"FuzzerSecurityIssueCritical"`, `"FuzzerSecurityIssueMedium"`, `"HF_ITER"`, `"LLVMFuzzerInitialize"`, `"LLVMFuzzerTestOneInput"`, `"OSS-Fuzz"`, `"__AFL_FUZZ_INIT"`, `"__AFL_FUZZ_TESTCASE_BUF"`, `"__AFL_LOOP"`, `"afl-clang-fast"`, `"afl-fuzz"`, `"atheris"`, `"boofuzz"`, `"cargo-fuzz"`, `"com.code_intelligence.jazzer"`, `"fuzzerTestOneInput"`, `"go-fuzz-build"`, `"honggfuzz"`, `"libfuzzer"`, `"libfuzzer-sys"`, `"syzkaller"`, `"testing.F"`. Results found only by these keywords are left out of every section. Figures with them included, for reference:_

| Surface | Raw hits (all keywords) | Unique results (all keywords) | Unique results (reported) | Distinct repos (all keywords) | Distinct repos (reported) |
| --- | --- | --- | --- | --- | --- |
| CODE | 3,477,582 | 2,808,761 | 1,490,528 | 344,255 | 255,740 |
| REPOS | 31,710 | 27,558 | 7,050 | 27,558 | 7,050 |
| COMMITS | 54,237,479 | 64,496 | 31,901 | 20,379 | 13,355 |
| PRS | 1,456,504 | 138,975 | 58,100 | 53,426 | 29,251 |
| ISSUES | 195,692 | 75,272 | 38,450 | 19,599 | 12,519 |
| DISCUSSIONS | 4,046 | 2,245 | 1,231 | 968 | 561 |

## T8/T9 — Is the 2026 surge real, and is it AI-driven?

**Concentration.** 10,810 relevant commits in 2026 vs 4,770 in 2025. Capped at 5 per repo per month: 9,425 vs 4,421. Without the top 10 repositories: 10,472 vs 4,486. Distinct repositories: 5,886 vs 2,313. Repositories with their first technique-mentioning commit (T8): 5,617 vs 2,006. If the surge survives capping and top-10 removal, it is not driven by a few very active repositories.

**AI authorship (lower bound).** 1,867 of 10,810 relevant 2026 commits (17%) carry an AI-agent authorship line, from 1,105 repositories; in 2025: 267 of 4,770. Agents that leave no trailer (or users who remove it) are not counted, so the true share is higher. 50 random commits are listed in sections_samples.md for manual confirmation.

**Timeline completeness.** Commit-search slices were capped in: 2010 (7.7% retrieved), 2011 (3.5% retrieved), 2012 (1.5% retrieved), 2013 (1.4% retrieved), 2014 (1.5% retrieved), 2015 (1.5% retrieved), 2016 (1.0% retrieved), 2017 (1.1% retrieved), 2018 (1.1% retrieved), 2019 (0.9% retrieved), 2020 (1.5% retrieved), 2021 (1.8% retrieved), 2022 (2.2% retrieved), 2023 (1.2% retrieved), 2024 (3.6% retrieved), 2025 (5.6% retrieved), 2026 (3.4% retrieved). 88% of the commits returned by capped slices contain a technique phrase, so relevant commits beyond the first 1,000 per slice were lost. A surge or decline in a capped year cannot be read from these counts.
