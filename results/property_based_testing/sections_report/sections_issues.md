# Property-Based Testing — Issues, Caveats & Verification

_Generated 2026-10-16 09:50. Companion to [sections_report.md](sections_report.md)._

## Actions, decisions and caveats

| # | Section | Type | Note |
| --- | --- | --- | --- |
| 1 | S1 | Decision / assumption | Only explicit technique phrases are counted (team decision); results found only by 9 tool/library/API keywords are excluded. All-keyword figures are in the S1/S2 section below. |
| 2 | S2 | Decision / assumption | CODE repositories cannot all be verified without scanning every one; the CODE row is estimated from the random sample, and the union / overlap use the non-CODE surfaces only. |
| 3 | A3 | Decision / assumption | No manual classification for this technique (team decision); 15 random usage repositories with strong signals are listed in sections_samples.md. |
| 4 | S1 | Caveat | GitHub's 1,000-result cap truncated search slices on CODE, COMMITS, PRS, ISSUES: counts on these surfaces are lower bounds (completeness per surface in S1 and the section below). |
| 5 | S1 | Caveat | Search keywords never run: `"property-based test"`, `"property based testing"`. These two phrase keywords never ran (connection errors during the search) and the search was not repeated. Non-CODE surfaces are unaffected: GitHub ignores the hyphen, so the variants that ran return the same items. On the CODE surface the hyphen/space variants return different counts, so the CODE population is slightly undercounted. |
| 6 | S1 | Caveat | DISCUSSIONS "property-based testing": 248 raw < 255 collected — GitHub's `total_count` is an estimate; raw hits are approximate. |
| 7 | S1 | Caveat | Search truncation: GitHub returns ≤1,000 results per query; queries were split by date/size until each piece had <900 results, but an unsplittable piece is truncated to 1,000. |
| 8 | A2 | Caveat | Estimated population counts = share of sampled repositories whose state is known (hit, no hit or deleted) × the CODE repositories found by search. |
| 9 | A3 | Caveat | Test files = filename pattern (test_*.py, *_test.go, *Test.java, *.spec.ts…), pytest/JUnit import or `@Test`, or a test/tests/testing/spec/e2e directory in the repo-relative path. |
| 10 | A5 | Caveat | GitHub-wide counts come from repository search `total_count` (approximate) and only count each repository's primary language. |
| 11 | A6 | Caveat | Heuristic keyword matching; verify with the 10 random repos per domain in sections_samples.md. Generic keywords (api, rest, react, query, security…) still match broadly; a README needs ≥3 different keywords of a domain to count. |
| 12 | T8 | Caveat | Creation year of 6,234 of 6,710 repositories estimated from the GitHub repository ID (IDs are assigned in creation order), interpolated between 29,809 repositories with known creation dates; correct year for 100.0% of 3,000 known repositories checked this way. 5 could not be dated. |
| 13 | T9 | Caveat | Commit search covers default branches only, was date-sliced 2010-01-01 → 2026-09-01, and keeps fork duplicates (same SHA) once. |
| 14 | T8/T9 | Caveat | Commit search hit the 1,000-result cap in 4 of 14 years (2018, 2019, 2025, 2026). Commit counts, first-commit repo counts and agent shares for these years are lower bounds, and year-to-year changes between capped and uncapped years are not comparable. |
| 15 | T8/T9 | Verified / resolved | Surge and AI-share verification for 2025: see the T8/T9 section below. |

## Data sources

| Data source | Value |
| --- | --- |
| Search keywords kept (explicit phrases) | 6 |
| Search keywords excluded (tool / library / API) | 9 |
| Search keywords never run | 2 |
| CODE population (repos) | 76,846 |
| CODE sample drawn / analysed / unavailable / failed | 1,138 / 1,112 / 26 / 0 |
| Verified non-CODE repos (population) / A6–A7 sample drawn / counted | 16,370 / 1,083 / 1,073 |
| Sample seed | 20261011 |
| Search data prepared | 2026-10-11T03:02:54+00:00 |

_Analysis keywords (`inputs/pbt_analysis_keywords.json`):_

| Keyword | Regex | Subset of |
| --- | --- | --- |
| property-based test(ing) | `(?<![A-Za-z0-9])property[\s-]+based[\s-]+test(?:ing\|s\|ers?)?(?![A-Za-z0-9])` |  |
| string literal: property-based test | `"[Pp]roperty[\s-]+[Bb]ased[\s-]+[Tt]est(?:ing\|s\|ers?)?"` | phrase_pbt |
| comment: property-based test | `(?:#\|//).*(?<![A-Za-z0-9])property[\s-]+based[\s-]+test(?:ing\|s\|ers?)?(?![A-Za-z0-9])` | phrase_pbt |

_Method: see README.md (Reproducing the results)._

## S1/T9 — Search completeness (GitHub's 1,000-result cap)

_From search.log, kept keywords only. A slice is capped when GitHub reported more results than the 1,000 it returns. GitHub's total also counts fork copies of the same commit/PR and, for commit search, loose matches of the words, so 'retrieved %' understates completeness. The last column is the share of the items returned by capped slices whose title/body contains a technique phrase: close to 100% means the cap cut off relevant results._

| Surface | Slices | Capped | GitHub total | Retrieved | Retrieved % | Capped slices: relevant items |
| --- | --- | --- | --- | --- | --- | --- |
| CODE | 814 | 2 | 493,057 | 486,220 | 98.6% | n/a |
| REPOS | 10 | 0 | 4,686 | 4,686 | 100.0% | — |
| COMMITS | 112 | 29 | 230,034 | 76,638 | 33.3% | 99.1% of 17,676 |
| PRS | 78 | 35 | 167,202 | 62,034 | 37.1% | 59.3% of 35,000 |
| ISSUES | 35 | 9 | 40,170 | 24,163 | 60.2% | 85.3% of 8,976 |
| DISCUSSIONS | 4 | 0 | 1,063 | 1,063 | 100.0% | — |

## S1/S2 — Results found only by excluded search keywords

_Excluded (tool / library / API keywords (explicit phrases only)): `"PropEr"`, `"fast-check"`, `"import hypothesis"`, `"import net.jqwik"`, `"import org.scalacheck"`, `"leanovate/gopter"`, `"open FsCheck"`, `"use proptest"`, `"using FsCheck"`. Results found only by these keywords are left out of every section. Figures with them included, for reference:_

| Surface | Raw hits (all keywords) | Unique results (all keywords) | Unique results (reported) | Distinct repos (all keywords) | Distinct repos (reported) |
| --- | --- | --- | --- | --- | --- |
| CODE | 1,056,252 | 979,183 | 277,801 | 477,112 | 76,846 |
| REPOS | 5,368 | 1,836 | 1,205 | 1,836 | 1,205 |
| COMMITS | 522,918 | 25,675 | 10,706 | 13,476 | 6,710 |
| PRS | 769,696 | 73,541 | 15,207 | 31,985 | 6,555 |
| ISSUES | 166,548 | 57,392 | 7,119 | 31,372 | 4,373 |
| DISCUSSIONS | 4,230 | 3,523 | 280 | 2,148 | 140 |

## T8/T9 — Is the 2025 surge real, and is it AI-driven?

**Concentration.** 2,438 relevant commits in 2025 vs 834 in 2024. Capped at 5 per repo per month: 2,239 vs 810. Without the top 10 repositories: 2,311 vs 821. Distinct repositories: 1,475 vs 561. Repositories with their first technique-mentioning commit (T8): 1,431 vs 529. If the surge survives capping and top-10 removal, it is not driven by a few very active repositories.

**AI authorship (lower bound).** 350 of 2,438 relevant 2025 commits (14%) carry an AI-agent authorship line, from 216 repositories; in 2024: 0 of 834. Agents that leave no trailer (or users who remove it) are not counted, so the true share is higher. 50 random commits are listed in sections_samples.md for manual confirmation.

**Timeline completeness.** Commit-search slices were capped in: 2018 (62.9% retrieved), 2019 (54.3% retrieved), 2025 (46.3% retrieved), 2026 (8.5% retrieved). 99% of the commits returned by capped slices contain a technique phrase, so relevant commits beyond the first 1,000 per slice were lost. A surge or decline in a capped year cannot be read from these counts.
