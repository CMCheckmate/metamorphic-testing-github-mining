# MT GitHub Miner

A three-phase pipeline for mining real-world adoption of **metamorphic testing (MT)** across open-source GitHub repositories.

Designed to complement the [metamorphic-testing interactive module](../metamorphic-testing/), providing empirical data on how MT is actually used in practice.

---

## What this project does

| Phase | Script | Input | Output |
| --- | --- | --- | --- |
| **1 — Search** | `search.py` | GitHub REST + GraphQL APIs | `results/raw/*.json` (6 files) |
| **2 — Clone** | `clone.py` | `results/raw/*.json` | `repos/<owner>/<name>/` + manifest |
| **3 — Analyse** | `analyze.py` | Cloned repos | `results/analysis/` findings + report |

### Phase 1 — Search (5 surfaces)

| Surface | Endpoint | What it searches | Rate limit |
| --- | --- | --- | --- |
| **Repositories** | `/search/repositories` | Repo name, description, topics, README | 30 req/min |
| **Code files** | `/search/code` | All files on the default branch | **9 req/min** (separate bucket) |
| **Issues** | `/search/issues?is:issue` | Issue title + body + comments | 30 req/min |
| **Pull Requests** | `/search/issues?is:pr` | PR title + body + review comments | 30 req/min |
| **Commits** | `/search/commits` | Commit messages (default branch) | 30 req/min |
| **Discussions** | GraphQL `search(type: DISCUSSION)` | Discussion title + body | 5,000 pts/hr |

**What is NOT covered:** Wiki pages, non-default branches, repository-level settings/CI files (covered by code search if they're text files), private repositories.

### Phase 2 — Clone

Reads and merges the six raw result files, deduplicates repositories, filters by optional criteria (language/stars/forks), and shallow-clones each repo.

### Phase 3 — Analyse

Scans every source file in every cloned repo for **explicit** MT markers (library imports, class names, decorators, string literals) and **implicit** structural patterns (heuristics in test files). Produces a scored classification per repo.

---

## The 1,000-result hard cap and how we work around it

**GitHub's hard limit:** Every search query returns at most 1,000 results across 10 pages. The API reports `total_count` (e.g. 4,200) but simply refuses to serve results beyond position 1,000 — there is no pagination trick that bypasses this.

**Adaptive date-range slicing (the documented workaround):**

When `total_count > 900`, `search.py` automatically bisects the query's date window and runs two sub-queries on the halves, recursing until each slice is under the threshold:

```text
"metamorphic testing" created:2010..2026   → total=3,200  → slice
  created:2010..2018   → total=900   → done (within threshold)
  created:2019..2026   → total=2,300  → slice again
    created:2019..2022 → total=950   → slice again
      created:2019..2020 → total=400 → done
      created:2021..2022 → total=550 → done
    created:2023..2026 → total=1,350 → slice again
      ...
```

Each leaf query retrieves its full ≤1,000 results normally. The results are merged and deduplicated. This gives complete coverage for any query regardless of total result count.

For most MT queries this never triggers at all — MT is niche enough that most individual queries return well under 900 results.

**Disable slicing** with `--no-slice` if you want a fast run and don't need completeness.

---

## Rate limits in detail

### Search API buckets

GitHub has **two separate rate-limit buckets** for search:

| Bucket | Endpoints | Authenticated | Unauthenticated |
| --- | --- | --- | --- |
| Standard search | `/search/repositories`, `/search/issues`, `/search/commits` | **30 req/min** | 10 req/min |
| Code search | `/search/code` | **9 req/min** | Not available |

These are independent — running code searches does not consume your standard search quota and vice versa.

### Secondary rate limits

Beyond the per-minute search limits, GitHub also enforces:

- Max **900 points/minute** across all REST requests (GET = 1 pt, POST/PATCH = 5 pts)
- Max **100 concurrent requests**
- Max **90 seconds CPU time per 60 seconds real time**
- Violations return HTTP 429 or 403 with a `Retry-After` header — the scripts handle this automatically.

### GraphQL rate limits

- **5,000 points/hour** (standard users), 10,000 for GitHub Enterprise Cloud
- **2,000 points/minute** secondary cap
- Each non-mutation `search()` query costs 1 point
- Results come back 100 per page; no 1,000-result cap (GraphQL paginates fully via cursors)

### Script-configured delays

| Delay constant | Value | Applied to |
| --- | --- | --- |
| `STANDARD_SEARCH_DELAY` | 2.2s | repos, issues, commits |
| `CODE_SEARCH_DELAY` | 7.0s | code search |
| `GRAPHQL_DELAY` | 1.5s | discussions |

---

## Throughput calculations

### Assumptions

- MT is niche: most queries return < 500 results (no slicing needed)
- ~3 queries per surface need slicing → ~2 extra sub-queries each
- Average pages per final query: ~4

### Phase 1 — Search timings

| Surface | Queries | Avg sub-queries (slicing) | API calls | Delay per call | Time |
| --- | --- | --- | --- | --- | --- |
| Repos (4 queries) | 4 | 1.0× | ~16 reqs | 2.2s | ~35s |
| Code (16 queries) | 16 | 1.3× avg (some slice) | ~85 reqs | 7.0s | ~10 min |
| Issues (5 queries) | 5 | 1.0× | ~20 reqs | 2.2s | ~44s |
| PRs (2 queries) | 2 | 1.0× | ~8 reqs | 2.2s | ~18s |
| Commits (4 queries) | 4 | 1.0× | ~16 reqs | 2.2s | ~35s |
| Discussions (3 queries) | 3 | n/a (cursor-based) | ~9 reqs | 1.5s | ~14s |
| **Phase 1 total** | | | **~154 reqs** | — | **~14 min** |

**Note:** Code search dominates due to the 7s/req limit. If you run `--no-slice` and only the most targeted code queries, Phase 1 drops to ~5 minutes.

### Phase 2 — Clone timings

| Scenario | Repos | Per-repo time | Total |
| --- | --- | --- | --- |
| Conservative | 100 repos | 2–4s | ~5–7 min |
| Typical | 250 repos | 2–4s | ~10–17 min |
| Full coverage | 500 repos | 2–4s | ~20–33 min |

### Phase 3 — Analyse timings (local, no network)

| Repos | Avg files/repo | Total files | Time |
| --- | --- | --- | --- |
| 250 repos | ~200 files | ~50,000 files | ~3–5 min |

### Full pipeline (typical, 250 repos)

| Phase | Time |
| --- | --- |
| Phase 1 — Search | ~14 min |
| Phase 2 — Clone 250 repos | ~15 min |
| Phase 3 — Analyse | ~4 min |
| **Total** | **~33 min** |

### Expected result counts

| Surface | Expected total in GitHub | Retrieved (with slicing) |
| --- | --- | --- |
| Repos matching "metamorphic testing" | ~400–700 | ~400–700 (all) |
| Code files with `MetamorphicTest` | ~100–400 | ~100–400 (all) |
| Code files with `"metamorphic testing"` | ~500–3,000 | ~500–3,000 (sliced) |
| Code files with `def mr_` (Python) | ~5,000–50,000 | **noisy** — narrow with `language:Python` |
| Issues mentioning "metamorphic testing" | ~200–800 | ~200–800 (all) |
| PRs mentioning "metamorphic testing" | ~50–200 | ~50–200 (all) |
| Commits | ~100–500 | ~100–500 (all) |
| Discussions | ~10–100 | all (cursor-based, no 1k cap) |
| **Unique repos across all surfaces** | — | **~300–800 repos** |

---

## Credentials & APIs

### GitHub Personal Access Token

| Limit | Unauthenticated | Authenticated |
| --- | --- | --- |
| Standard search | 10 req/min | **30 req/min** |
| Code search | Not available | **9 req/min** |
| GraphQL | Not available | **5,000 pts/hr** |

**How to create one:**

1. Go to <https://github.com/settings/tokens> → **Generate new token (classic)**
2. Name: `mt-github-miner`, Expiration: 90 days
3. Scopes: `public_repo` only (read-only, no write permissions needed)
4. Copy the token — shown only once

```bash
cp .env.example .env
# Edit .env: set GITHUB_TOKEN=ghp_...
```

> `.env` is in `.gitignore` and will never be committed.

---

## Setup

```bash
cd github-mining
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set GITHUB_TOKEN
```

---

## Workflow

### Step 1 — Search

```bash
# Run all surfaces (repos + code + issues + commits + discussions)
python search.py

# Individual surfaces
python search.py --repo
python search.py --code
python search.py --issues
python search.py --commits
python search.py --discussions

# Fast mode: no date-range slicing (misses results beyond 1k per query)
python search.py --no-slice

# Combine: issues only, no slicing, max 5 pages per query
python search.py --issues --no-slice --max-pages 5
```

**Output:** `results/raw/repos.json`, `code.json`, `issues.json`, `prs.json`, `commits.json`, `discussions.json`, `summary.json`

---

### Step 2 — Clone

```bash
# Clone all candidates from all search result files
python clone.py

# Filter options
python clone.py --lang Python --min-stars 5 --skip-forks --limit 100

# Re-clone (refresh) repos already on disk
python clone.py --refresh

# Batch cloning: skip the first N filtered repos, clone the next chunk only
python clone.py --offset 0 --limit 50
python clone.py --offset 50 --limit 50
```

**Output:** `repos/<owner>/<name>/` + `results/cloned/manifest.json`

---

### Step 3 — Analyse

```bash
# Analyse all cloned repos (explicit + implicit patterns)
python analyze.py

# High-confidence only (faster, no implicit heuristics)
python analyze.py --only explicit

# Single repo
python analyze.py --repo owner/reponame

# Only show repos with score >= 5
python analyze.py --min-score 5

# Batch mode: append to existing outputs and delete each cloned repo after analysis
python analyze.py --append --cleanup-clones
```

**Output:** `results/analysis/findings.json`, `repo_scores.json`, `summary_report.md`

---

## Data flow for downstream analysis

```text
GitHub APIs
   │
   ▼
results/raw/repos.json        ← repository metadata
results/raw/code.json         ← code-file match records
results/raw/issues.json       ← issue records
results/raw/prs.json          ← pull request records
results/raw/commits.json      ← commit records
results/raw/discussions.json  ← discussion records
results/raw/summary.json      ← per-query hit counts
   │
   ▼  (clone.py)
repos/<owner>/<name>/         ← shallow-cloned source trees
results/cloned/manifest.json  ← clone status + metadata
   │
   ▼  (analyze.py)
results/analysis/findings.json    ← per-file pattern hits
results/analysis/repo_scores.json ← per-repo scores + classification
results/analysis/summary_report.md
```

All files are plain JSON — load directly into pandas for analysis:

```python
import pandas as pd, json

scores = pd.DataFrame(json.load(open("results/analysis/repo_scores.json")))
# Explicit MT adopters only
explicit = scores[scores["classification"].isin(["strong_explicit","weak_explicit"])]
print(explicit.sort_values("score", ascending=False)[["full_name","stars","language","score"]])
```

---

## Project structure

```text
github-mining/
├── search.py          # Phase 1: GitHub API search → results/raw/
├── clone.py           # Phase 2: shallow-clone repos → repos/
├── analyze.py         # Phase 3: local pattern scan → results/analysis/
├── config.py          # All queries, patterns, delays, paths, slicing settings
├── requirements.txt
├── .env.example       # Copy to .env and add GITHUB_TOKEN
├── .gitignore
└── results/           # (gitignored data, directory structure tracked)
    ├── raw/
    ├── cloned/
    └── analysis/
```

---

## Notes on search surfaces

**Code search does not return snippets.** The API only returns the matching file's path and SHA — not which line matched. Actual line-level matches are discovered in Phase 3 after cloning.

**Discussions have no result cap.** GraphQL cursor-based pagination retrieves all results — there is no 1,000-result wall for discussions.

**Implicit patterns are heuristics.** `transform(input)` before an assertion could be MT or just test setup. The implicit results are a shortlist for manual inspection. Use `--only explicit` for high-confidence findings.
