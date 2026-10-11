# GitHub Mining Pipeline

Mines GitHub repositories to study the adoption of three software testing techniques across open-source projects, producing a per-technique academic comparative report.

**Techniques:** Metamorphic Testing (MT) · Fuzz Testing (Fuzzing) · Property-Based Testing (PBT)

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your GitHub token
cp .env.example .env
# edit .env and add GITHUB_TOKEN=ghp_...

# 3. Run the full pipeline for one technique
python main.py --technique mt

# 4. Or run without a token (uses example data)
python generate_example_data.py --technique mt
```

---

## Running with Docker

Docker isolates the pipeline from your host: cloned repos, git operations, and file scanning all run inside the container. Results are written to your local `results/` via a volume mount, so nothing is lost when the container exits.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS) or Docker Engine (Linux)
- A `.env` file with your GitHub token (same as the non-Docker setup)

### Build the image

```bash
docker compose build
```

This only needs to be done once, and again whenever `requirements.txt` or source files change.

### Run the full pipeline

```bash
docker compose run --rm pipeline --technique mt
docker compose run --rm pipeline --technique pbt
docker compose run --rm pipeline --technique fuzz
```

### Run individual phases

```bash
# Search only
docker compose run --rm pipeline --technique mt --phase search

# Analysis only (code + non-code)
docker compose run --rm pipeline --technique mt --phase analysis --workers 4

# Code analysis only, skip metadata fetch
docker compose run --rm pipeline --technique mt --phase analysis --code-only --no-size-stats

# Report only (no network needed — use --network none for extra isolation)
docker compose run --rm --network none pipeline --technique mt --phase report

# Re-aggregate existing results without re-cloning
docker compose run --rm pipeline --technique mt --phase analysis --aggregate-only
```

### Accessing results

Results are written to `./results/` on your host machine (via the volume mount). The report is at:

```
results/metamorphic_testing/report/report.md
results/metamorphic_testing/report/plots/
```

### Resource limits

The default limits in `docker-compose.yml` are `8 GB` RAM and `4` CPUs. Adjust the `deploy.resources.limits` block if your machine has more or less available.

### Security notes

- The container runs as a non-root user (`pipeline`, uid 1000).
- Cloned repos are written inside the container's filesystem (under the mounted `results/` volume). Symlinks in cloned repos cannot escape to your host filesystem.
- The `inputs/` volume is mounted read-only.
- The report phase does not need network access — pass `--network none` to `docker compose run` for that phase.
- Search and analysis phases require outbound HTTPS to `api.github.com`.

---

## Pipeline Architecture

```
Search ──► Analysis ──► Report
  │            │            │
  ▼            ▼            ▼
results/    code_repos   report.md
search/     .json        plots/
```

### Phase 1 — Search

Queries GitHub across **six surfaces** for each keyword in the technique's search keyword file.

| Surface | GitHub endpoint |
|---------|----------------|
| code | `/search/code` |
| repos | `/search/repositories` |
| issues | `/search/issues` (type:issue) |
| prs | `/search/issues` (type:pr) |
| commits | `/search/commits` |
| discussions | GraphQL `search()` |

- Results are saved to `results/<slug>/search/` — one JSON file per surface.
- Progress is tracked in `search_history.json`. Interrupted runs resume from the last completed keyword.
- Code search applies adaptive date-range slicing to work around GitHub's 1 000-result cap.
- `--overwrite` resets history and result files to start fresh.

### Phase 2 — Analysis

Two sub-phases run in parallel:

**Code analysis** (`code_analysis.py`)
- Reads `results/<slug>/search/code.json` — the Code search surface only.
- Clones repos in batches (up to `CLONE_BATCH_MAX_BYTES` / `CLONE_BATCH_MAX_REPOS` per batch).
- Scans every file with compiled regexes from the analysis keyword JSON.
- Classifies each file as `test_code | source_code | docs | config | other`.
- Mines full git commit history via PyDriller (or `git log` fallback) for RQ3 timeline data.
- Classifies each repo as `research_artifact | framework | actual_usage | unclassified`.
- Writes results to `results/<slug>/analysis/code_repos.json` as each repo finishes.
- `code_history.json` tracks done/failed repos — never re-clones.
- Clones are deleted after each batch to reclaim disk.

**Non-code analysis** (`non_code_analysis.py`)
- Reads all non-code surface JSON files (repos, commits, prs, issues, discussions).
- Applies analysis keywords to title + body text.
- Extracts domain signals and word frequencies for the word cloud.
- Writes to `results/<slug>/analysis/noncode_results.json`.
- `noncode_history.json` tracks processed item IDs — resume-safe.
- At the end of the run, fetches `cloned_repo_metadata.json` for all repos across all surfaces via a parallelised GitHub API fetch (4 workers, ~320 req/min). This file is required by code analysis for batch-size gating; run non-code analysis before (or in parallel with) code analysis.

After both sub-phases finish, `analysis.py` aggregates everything into `overall.json`. The report phase reads only `overall.json` — it performs no calculations.

- `--restart` resets all analysis history and result files before running.
- `--code-only` / `--noncode-only` run only one sub-phase.
- `--workers N` sets the number of parallel worker processes for file scanning (default: 4).
- `--aggregate-only` skips cloning and scanning entirely — reads whatever is already in `code_repos.json` and `noncode_results.json` and re-aggregates into `overall.json`. Useful after manually editing result files or after a keyword change that only affects aggregation. Cannot be combined with `--restart`, `--code-only`, or `--noncode-only`.
- `--no-size-stats` skips the `cloned_repo_metadata.json` fetch entirely (non-code analysis) and allows code analysis to proceed without the file. Size statistics will be unavailable in the report. Use this flag when you want to run code analysis without first completing a non-code run.

### Phase 3 — Report

Reads `overall.json`, `code_repos.json`, and `noncode_results.json`.
Writes `results/<slug>/report/report.md` and all plots to `results/<slug>/report/plots/`.

The report covers:
- **RQ1** — Adoption extent: repo discovery, density, contributor stats
- **RQ2** — Usage patterns: keyword hits, classification, languages, domain word cloud
- **RQ3** — Timeline: creation dates, commit activity, technique commits over time

---

## File Structure

```
metamorphic-testing-github-mining/
├── main.py                     CLI entry point
├── config.py                   Tuneable constants
├── utils.py                    Shared utilities (API, logging, JSON, path safety)
├── search.py                   Phase 1 — GitHub search
├── code_analysis.py            Phase 2a — Clone + scan + classify repos
├── non_code_analysis.py        Phase 2b — Analyse non-code surface results
├── analysis.py                 Phase 2 orchestrator + aggregation → overall.json
├── report.py                   Phase 3 — report.md + plots
├── generate_example_data.py    Generate dummy data (no GitHub token needed)
│
├── inputs/                     Technique keyword files
│   ├── shared_analysis_keywords.json  (general_test keywords shared by all techniques)
│   ├── domain_keywords.json           (ACM CCS 2012 domain taxonomy — edit to tune domain detection)
│   ├── mt_search_keywords.txt
│   ├── mt_analysis_keywords.json
│   ├── pbt_search_keywords.txt
│   ├── pbt_analysis_keywords.json
│   ├── fuzz_search_keywords.txt
│   └── fuzz_analysis_keywords.json
│
├── example_results/            example outputs from generate_example_data.py (committed)
├── results/                    (git-ignored) real pipeline outputs
│   ├── metamorphic_testing/
│   │   ├── search/             code.json  repos.json  issues.json  prs.json
│   │   │                       commits.json  discussions.json
│   │   │                       summary.json  search_history.json
│   │   ├── cloned/             temporary clones (deleted after each batch)
│   │   ├── analysis/           code_repos.json  code_history.json
│   │   │                       noncode_results.json  noncode_history.json
│   │   │                       cloned_repo_metadata.json
│   │   │                       overall.json
│   │   └── report/             report.md  plots/
│   ├── fuzz_testing/           (same structure)
│   └── property_based_testing/ (same structure)
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env                        GITHUB_TOKEN (git-ignored)
└── .env.example
```

---

## CLI Reference

```
python main.py --technique TECHNIQUE [--phase PHASE] [options]
```

| Argument | Description |
|----------|-------------|
| `--technique mt\|fuzz\|pbt` | Technique to run (also accepts full slug) |
| `--phase search\|analysis\|report` | Phase to run; omit to run all three in sequence |
| `--overwrite` | (search) Reset history and result files |
| `--restart` | (analysis) Reset all analysis data and history |
| `--code-only` | (analysis) Code sub-phase only |
| `--noncode-only` | (analysis) Non-code sub-phase only |
| `--workers N` | Worker processes for parallel file scanning (default: 4) |
| `--aggregate-only` | (analysis) Skip clone/scan; re-aggregate existing data into `overall.json` |
| `--no-size-stats` | (analysis) Skip `cloned_repo_metadata.json` fetch; allow code analysis to run without it |

**Examples:**

```bash
python main.py --technique mt --phase search
python main.py --technique mt --phase search --overwrite
python main.py --technique pbt --phase analysis --code-only
python main.py --technique fuzz --phase analysis --restart
python main.py --technique mt --phase analysis --aggregate-only
python main.py --technique mt --phase analysis --code-only --no-size-stats
python main.py --technique mt --phase report
python main.py --technique mt                     # all phases
```

---

## Input Files

### Search keyword files (`inputs/*_search_keywords.txt`)

Plain text, one query per line. Each line is passed verbatim to the GitHub search API.

Rules:
- Wrap exact phrases in double quotes: `"metamorphic test"`
- Include all inflected forms explicitly — GitHub does not auto-match variants
- Code-only constructs go in the analysis keyword JSON, not here
- Lines starting with `#` are comments

### Analysis keyword files (`inputs/*_analysis_keywords.json`)

JSON array of keyword objects, each with:

| Field | Description |
|-------|-------------|
| `id` | Unique identifier string |
| `label` | Human-readable name shown in the report |
| `category` | `general_test` \| `specific_technique` |
| `regex` | Python regex pattern |
| `flags` | Optional: `IGNORECASE`, `MULTILINE` |
| `apply_to` | (`general_test` filename/content entries) `filename` \| `content` |
| `language` | (content entries) scope to detected language |

**Categories:**

- **`general_test`** — broad test terms and test-file-detection patterns counted as a baseline (e.g. `\btest\b`, `test_*.py`). Defined in `shared_analysis_keywords.json` and merged with every technique's keyword list. Filename-pattern and import/annotation entries that label a file as `test_code` also live here; only unambiguous toolchain-enforced conventions are accepted (e.g. `*Test.java`, `import pytest`). No directory checks.
- **`specific_technique`** — technique-specific patterns; the primary adoption metric.

---

## File Category Classification

Every scanned file is assigned exactly one category:

| Priority | Category | Rule |
|----------|----------|------|
| 1 (highest) | `test_code` | Any `test_file_detection` keyword fires |
| 2 | `source_code` | Code extension (`.py`, `.java`, `.go`, ...) |
| 3 | `docs` | Doc extension (`.md`, `.rst`, `.txt`, ...) |
| 4 | `config` | Config extension (`.yaml`, `.toml`, `.json`, ...) |
| 5 | `other` | Everything else |

No directory name checks. Extension + content only.

---

## Repo Classification

An ordered decision tree; a repo can satisfy multiple categories:

1. **`research_artifact`** — DOI/arXiv/ACM/IEEE links in README, conference/journal names, `data/` + `rq*/` directories, `.ipynb` or `.R` files, replication package indicators.
2. **`framework`** — ≥50% of technique hits in `source_code` files, or technique library in runtime (non-dev) dependencies.
3. **`actual_usage`** — ≥80% of technique hits in `test_code` files, or technique library in dev/test dependencies.
4. **`unclassified`** — no signal fires with sufficient confidence; flagged for manual review.

---

## Results Files

| File | Contents |
|------|----------|
| `search/<surface>.json` | Array of result records from that GitHub surface |
| `search/summary.json` | Per-surface: `api_hit_count`, `unique_results`, per-keyword breakdown |
| `search/search_history.json` | `{keyword: "done"}` — resume state |
| `analysis/code_repos.json` | Array of per-repo analysis results (scan stats, commits, classification) |
| `analysis/code_history.json` | `{repo_name: "done"\|"failed"\|"cloned"}` — resume state |
| `analysis/noncode_results.json` | Array of per-item non-code analysis results |
| `analysis/noncode_history.json` | Array of processed `surface:id` strings |
| `analysis/cloned_repo_metadata.json` | Per-repo metadata fetched from GitHub API: `size_kb`, `stars`, `language`, `created_at`, `description`, `topics`. Created at the end of non-code analysis; used by code analysis for batch-size gating and by the report for size statistics. |
| `analysis/overall.json` | All aggregated stats — the report's sole data source |
| `report/report.md` | Generated Markdown report |
| `report/plots/` | Generated plot images |

---

## Configuration

All constants are in `config.py`. Notable settings:

| Constant | Default | Description |
|----------|---------|-------------|
| `CLONE_BATCH_MAX_BYTES` | 5 GB | Max total clone size per batch |
| `CLONE_BATCH_MAX_REPOS` | 20 | Max repos per clone batch |
| `CLONE_DEPTH` | 100 | Shallow clone depth (0 = full history) |
| `ANALYSIS_WORKERS` | 4 | Parallel worker processes for file scanning |
| `MAX_FILE_SIZE_BYTES` | 5 MB | Files larger than this are skipped |
| `GITHUB_API_PER_PAGE` | 100 | Results per API page |
| `RATE_LIMIT_PAUSE` | 2.5 s | Base pause between standard API requests |
| `CODE_SEARCH_PAUSE` | 7.0 s | Pause between code search requests |
| `RETRY_ATTEMPTS` | 5 | API retry attempts with exponential backoff |
| `SLICE_THRESHOLD` | 900 | Results count above which date-range slicing kicks in |

Secrets (`GITHUB_TOKEN`) go in `.env` (never committed).

---

## Development

### Testing without a GitHub token

```bash
python generate_example_data.py --technique mt    # one technique
python generate_example_data.py --technique all   # all three
```

This generates realistic dummy data for every search and analysis file, then runs the report phase. Output goes to `example_results/` (committed, not git-ignored) so it never overwrites real pipeline data in `results/`.

### Dependencies

```bash
pip install -r requirements.txt
pip install pydriller   # optional — for full commit history mining
                        # falls back to git log subprocess if not installed
```

### Resuming interrupted runs

All phases are resumable. Re-run the same command — completed work is skipped automatically via history files. Use `--overwrite` (search) or `--restart` (analysis) to start from scratch.

---

## Research Questions

| RQ | Focus |
|----|-------|
| **RQ1** | Adoption extent — repos found, file/line density, contributor stats |
| **RQ2** | Usage patterns — keyword hits, classification, languages, domains |
| **RQ3** | Timeline — creation dates, commit activity over time, commit span |
