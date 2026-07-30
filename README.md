# MT GitHub Miner

A four-phase pipeline for mining explicit adoption of **metamorphic testing (MT)** across open-source GitHub repositories. Designed to complement the [metamorphic-testing interactive module](../metamorphic-testing/) and to provide empirical, behavioural evidence of MT adoption at scale.

---

## Quick start

```bash
cd metamorphic-testing-github-mining
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set GITHUB_TOKEN=ghp_...

# Run the full pipeline
python main.py

# Or run specific phases
python main.py --stages 1 2        # search then clone
python main.py --stages 3 4        # analyse and plot existing clones
python main.py --stages 5          # results report from existing data (no re-run needed)
python main.py --stages 4 5        # regenerate plots then report
python main.py --help              # full parameter reference
```

---

## Pipeline overview

| Phase | Script | Input | Output |
|---|---|---|---|
| **1 — Search** | `search.py` | GitHub REST + GraphQL APIs | `results/raw/*.json` |
| **2 — Clone** | `clone.py` | `results/raw/*.json` | `repos/<owner>/<name>/` + manifest |
| **3 — Analyse** | `analyze.py` | Cloned repos | `results/analysis/` findings + scores |
| **4 — Plot** | `plot.py` | `results/raw/` + `results/analysis/` | `results/plots/*.png` |
| **5 — Report** | `report.py` | `results/` (any existing data) | `results/reports/results_report.md` |

All five phases are orchestrated by `main.py`. Each phase can also be run standalone via its own script. **Phase 5 can be run at any time without re-running earlier phases** — it reads whatever data exists on disk.

---

## Phase 1 — Search

Queries GitHub across five search surfaces using the REST and GraphQL APIs.

| Surface | Endpoint | What it searches | Rate limit |
|---|---|---|---|
| **Repositories** | `/search/repositories` | Name, description, topics, README | 30 req/min |
| **Code files** | `/search/code` | All files on the default branch | **9 req/min** (separate bucket) |
| **Issues** | `/search/issues?is:issue` | Title + body + comments | 30 req/min |
| **Pull Requests** | `/search/issues?is:pr` | Title + body + review comments | 30 req/min |
| **Commits** | `/search/commits` | Commit messages (default branch) | 30 req/min |
| **Discussions** | GraphQL `search(type: DISCUSSION)` | Discussion title + body | 5,000 pts/hr |

**Search strategy:** All queries use specific MT phrases (`"metamorphic testing"`, `"metamorphic relation"`, etc.) — no standalone `"metamorphic"` term. A bare `"metamorphic"` query is too general (matches geology, malware, etc.) and, since every specific MT phrase contains "metamorphic", it would subsume all specific queries and waste the 1,000-result cap on non-MT hits. Filtering for relevance happens downstream in Phases 2 and 3. Searches target only explicit MT terminology; we do not search for specific library names whose names do not contain "metamorphic" (see [Search design principle](#search-design-principle) below).

**What is NOT covered:** Wiki pages, non-default branches, private repositories.

### The 1,000-result cap and adaptive slicing

GitHub returns at most 1,000 results per query. When `total_count > 900`, `search.py` bisects the date window and recurses until each slice is under the threshold, giving full coverage. Disable with `--no-slice` for a faster partial run.

```text
"metamorphic testing" created:2010..2026  → 3,200 total → slice
  created:2010..2018  → 900  → done
  created:2019..2026  → 2,300 → slice
    created:2019..2022 → 950  → slice
      ...
```

---

## Phase 2 — Clone

Reads and merges the six raw result files, deduplicates, applies optional filters (language, minimum stars, fork exclusion), and shallow-clones each qualifying repo.

```bash
python main.py --stages 2 --min-stars 5 --skip-forks --workers 8
```

Parallel cloning with `--workers N` gives roughly linear speedup on I/O-bound network clones.

---

## Phase 3 — Analyse

Scans every file in every cloned repo for **explicit** MT adoption signals. Implicit pattern analysis (structural heuristics) is out of scope for this study; the analysis targets only direct terminology.

### Explicit patterns

| Category | Examples |
|---|---|
| Import patterns | `import metamorphic`, `from metamorphic` (any module whose name contains "metamorphic") |
| Class / decorator names | `MetamorphicTest*`, `MetamorphicRelation*`, `@metamorphic` |
| String literals | `"metamorphic testing"`, `"metamorphic relation"` (with plural variants) |
| Inline comments | `# metamorphic testing …`, `// metamorphic relation …` |
| Lemmatised comments | Morphological variants (e.g. *metamorphically*) matched against NLTK-lemmatised comment tokens |

### Classification tiers

| Tier | Criterion | Meaning |
|---|---|---|
| `strong_explicit` | ≥ 3 explicit hits | Multiple unambiguous MT signals across the repo |
| `weak_explicit` | 1–2 explicit hits | At least one direct signal; adoption may be exploratory |
| `none` | 0 explicit hits | Keyword appeared in README/commit/issue only; no MT in source code |

Score = explicit hits × 3, capped at 100 (used for ranking within tiers).

### Parallel analysis

```bash
python main.py --stages 3 --workers 8 --cleanup-clones
```

`--workers N` analyses N repos concurrently (ThreadPoolExecutor). `--cleanup-clones` deletes each repo after analysis to reclaim disk space.

---

## Phase 4 — Plot

Reads Phase 1 and Phase 3 outputs and produces eight publication-quality figures.

| File | Description |
|---|---|
| `query_hits.png` | Per-query hit counts across all search surfaces |
| `classification_dist.png` | Classification tier distribution |
| `yearly_trend.png` | Explicit MT-adopting repos by creation year |
| `language_dist.png` | Top languages among explicit MT repos |
| `stars_vs_score.png` | Repository popularity vs explicit hit count |
| `pattern_freq.png` | Frequency of each explicit pattern across findings |
| `domain_heatmap.png` | Language × classification tier heatmap |
| `query_overlap.png` | Repos found by N distinct search queries |

```bash
python main.py --stages 4 --format pdf --dpi 300
```

---

## Phase 5 — Report

Reads whatever results exist on disk and generates a Markdown report at
`results/reports/results_report.md` that directly answers each mining sub-question (RQ2.1–RQ2.8):

| Section | Sub-question answered |
|---|---|
| Funnel Summary | Total pipeline yield at each stage |
| RQ2.1 | What proportion of repos with MT mentions contain explicit MT in source code? |
| RQ2.2 | Is explicit MT adoption growing, plateauing, or declining year-on-year? |
| RQ2.3 | Which programming languages are most associated with explicit MT adoption? |
| RQ2.4 | Are MT-adopting repos concentrated in specific domains? |
| RQ2.5 | Are adopters production projects (high stars) or research prototypes? |
| RQ2.6 | Are specific organisations/authors responsible for most adoption? |
| RQ2.7 | How deeply does MT penetrate an adopting repository (files affected)? |
| RQ2.8 | What MT patterns appear most often? Top repos for qualitative inspection. |

Each section includes the relevant plot(s) embedded at the point where they support the narrative.
Two plots added specifically for this report:

- **`author_dist.png`** (RQ2.6) — top organisations/users by explicit MT repo count
- **`coverage_depth.png`** (RQ2.7) — distribution of files-with-MT-signals per repo, by tier

```bash
python main.py --stages 5                         # report from existing results
python main.py --stages 5 --refresh-plots         # also regenerate all plots first
python main.py --stages 5 --top-repos 30          # include top 30 repos in RQ2.8 table
python report.py                                  # run standalone
```

---

## Search design principle

**We search by terminology, not by library name.**

MT libraries often have names that do not contain the word "metamorphic" (e.g. a library called `gemtest` or `mrtest`). Searching for `import gemtest` would be a form of *implicit* search: it relies on out-of-band knowledge that the library name maps to MT, is impossible to generalise to libraries we do not know about, and conflates knowledge of library names with evidence of explicit MT adoption.

The correct approach: any well-documented MT library will mention "metamorphic testing" or "metamorphic relation" in its README, docstrings, or comments. Phase 3's string and comment patterns catch these mentions regardless of what the library is named. If a codebase uses an MT library but never mentions "metamorphic" anywhere in its own code or documentation, it does not exhibit explicit, intentional adoption of MT by our operational definition.

**Consequence for CODE_QUERIES:** Code search queries use only identifiers that directly contain "metamorphic" (e.g. `MetamorphicTest`, `metamorphic_relation`, `@metamorphic`, string literals). No library-specific package names are searched.

---

## Rate limits

| Bucket | Authenticated | Delay used |
|---|---|---|
| `/search/repositories`, `/search/issues`, `/search/commits` | 30 req/min | 2.2 s |
| `/search/code` | 9 req/min | 7.0 s |
| GraphQL discussions | 5,000 pts/hr | 1.5 s |

Violations return HTTP 429 / 403 with `Retry-After` — handled automatically with up to 4 retries.

---

## Throughput estimates

### Phase 1 (full run, all surfaces, slicing enabled)

| Surface | Queries | Estimated time |
|---|---|---|
| Repositories | 7 | ~2 min |
| Code files | 13 | ~16 min |
| Issues + PRs | 14 | ~4 min |
| Commits | 6 | ~2 min |
| Discussions | 6 | ~2 min |
| **Total** | **46** | **~26 min** |

Code search dominates due to its 7 s/request rate limit. Phase 1 with `--no-slice` and only the code surface drops to ~2 min.

### Phase 2 (with `--workers 4`)

~250 repos cloned in 5–10 min (vs ~15 min sequential).

### Phase 3 (with `--workers 4`)

~250 repos × ~200 files analysed in ~2 min (vs ~5 min sequential).

### Full pipeline (typical, 250 repos, 4 workers)

| Phase | Time |
|---|---|
| 1 — Search | ~28 min |
| 2 — Clone (parallel) | ~7 min |
| 3 — Analyse (parallel) | ~2 min |
| 4 — Plot | < 1 min |
| **Total** | **~38 min** |

---

## GitHub Personal Access Token

| Feature | Without token | With token |
|---|---|---|
| Standard search | 10 req/min | **30 req/min** |
| Code search | ❌ not available | **9 req/min** |
| GraphQL | ❌ not available | **5,000 pts/hr** |

**Create a token:**
1. <https://github.com/settings/tokens> → **Generate new token (classic)**
2. Name: `mt-github-miner` | Scopes: `public_repo` only
3. Copy the token (shown once only)

```bash
cp .env.example .env
# Edit .env: GITHUB_TOKEN=ghp_...
```

`.env` is listed in `.gitignore` and will not be committed.

---

## Project structure

```text
metamorphic-testing-github-mining/
├── main.py            # Pipeline orchestrator — run all phases from here
├── search.py          # Phase 1: GitHub API search → results/raw/
├── clone.py           # Phase 2: filter + shallow-clone → repos/
├── analyze.py         # Phase 3: local pattern scan → results/analysis/
├── plot.py            # Phase 4: visualisations → results/plots/
├── report.py          # Phase 5: results report → results/reports/
├── config.py          # Queries, patterns, delays, paths, slicing settings
├── requirements.txt
├── .env.example
├── .gitignore
└── results/           # gitignored; directory structure tracked
    ├── raw/
    ├── cloned/
    ├── analysis/
    ├── plots/
    └── reports/
```

---

## Data flow

```text
GitHub APIs
   │
   ▼  search.py
results/raw/repos.json        ← repository metadata
results/raw/code.json         ← code-file matches
results/raw/issues.json       ← issue records
results/raw/prs.json          ← pull request records
results/raw/commits.json      ← commit records
results/raw/discussions.json  ← discussion records
results/raw/summary.json      ← per-query hit counts
   │
   ▼  clone.py
repos/<owner>/<name>/          ← shallow-cloned source trees
results/cloned/manifest.json   ← clone status + metadata
   │
   ▼  analyze.py
results/analysis/findings.json     ← per-file pattern hits
results/analysis/repo_scores.json  ← per-repo scores + classification
results/analysis/summary_report.md
   │
   ▼  plot.py
results/plots/*.png            ← 10 publication-quality figures
   │
   ▼  report.py  (reads any/all of the above that exist)
results/reports/results_report.md  ← comprehensive results report (RQ2.1–RQ2.8)
```

Load into pandas for analysis:

```python
import pandas as pd, json

scores = pd.DataFrame(json.load(open("results/analysis/repo_scores.json")))
explicit = scores[scores["classification"].isin(["strong_explicit", "weak_explicit"])]
print(explicit.sort_values("score", ascending=False)[["full_name", "stars", "language", "score"]])
```
