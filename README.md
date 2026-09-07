# GitHub Mining — Testing Technique Adoption Study

A five-phase pipeline for mining GitHub to measure the real-world adoption of software testing techniques. Designed for comparative research — each technique is defined by a YAML profile, and the same pipeline processes all of them identically.

---

## Design Philosophy

The pipeline is **technique-agnostic**. Every technique-specific setting (search queries, local scan patterns, commit keywords, domain hints) lives in a YAML file under `techniques/`. Pointing any phase at a different YAML file is all it takes to study a new technique; no code changes are needed.

Infrastructure concerns (rate limiting, clone parameters, file-scan filters, output paths) are centralized in `config.py` and apply equally to every technique.

Each technique's outputs are fully **isolated** under `results/<slug>/` and `repos/<slug>/`, so techniques can be run, updated, or re-run independently.

---

## Five-Phase Pipeline

```
Phase 1 — Search    query GitHub API across up to 5 surfaces  →  results/<slug>/raw/
Phase 2 — Clone     filter candidates, shallow-clone repos    →  repos/<slug>/
Phase 3 — Analyse   scan local files for technique signals    →  results/<slug>/analysis/
Phase 4 — Plot      generate publication-quality figures      →  results/<slug>/plots/
Phase 5 — Report    compile Markdown results report           →  results/<slug>/analysis/summary_report.md
```

---

## Technique Profiles (`techniques/*.yaml`)

Each YAML file fully describes one technique. The three provided profiles cover the primary study subject and two comparison techniques:

| File | Technique | Notes |
|---|---|---|
| `metamorphic_testing.yaml` | Metamorphic Testing (MT) | Primary subject; NLTK lemmatization enabled |
| `property_based_testing.yaml` | Property-Based Testing (PBT) | Hypothesis, QuickCheck, ScalaCheck, jqwik, proptest, fast-check |
| `fuzzing.yaml` | Fuzz Testing | libFuzzer, AFL/AFL++, honggfuzz, cargo-fuzz, Go testing.F, Jazzer, atheris, boofuzz, OSS-Fuzz |

### YAML field reference

| Field | Purpose |
|---|---|
| `name`, `short_name`, `slug` | Display name, abbreviation, and directory-name slug |
| `color` | Hex colour for this technique in plots |
| `search_phrases` | Natural-language phrases for GitHub full-text search (all surfaces) |
| `identifiers` | Code-level tokens (class names, decorators, macros) searched **on the code surface only** — prevents false positives on issues/commits/discussions |
| `extra_queries` | Verbatim query objects (`query`, `label`, `kind`) added to specific surface lists — e.g. topic-tag queries, language-qualified code queries |
| `patterns` | Regex patterns for Phase 3 local file scan (see below) |
| `commit_keywords` | Keywords for identifying technique-related commits in `git log` analysis; falls back to `search_phrases` if absent |
| `domain_keywords` | Per-technique domain→keywords mapping merged into the global domain inference (overrides defaults for that technique) |
| `lemmatization` | NLTK lemmatization config: `trigger` activates the second pass; `concept_lemmas` maps base lemmas to concept labels |

### Pattern fields

Each entry in `patterns:` supports:

| Field | Required | Purpose |
|---|---|---|
| `id` | yes | Unique snake_case identifier |
| `label` | yes | Human-readable description shown in reports |
| `regex` | yes | Python regex string (YAML backslashes must be doubled) |
| `flags` | no | `"IGNORECASE"` or `"MULTILINE"` |
| `scope` | no | `"line"` (default) or `"block"` — see below |

**`scope: block`** enables region-based technique-code estimation. For patterns marked as structural entry points (class definitions, function decorators, macro invocations), Phase 3 expands the matched line to the full enclosing block:

- **Python / indent-based**: block spans from the `def`/`class` line to the first non-blank line that dedents back to base indent.
- **C-like / brace-based**: block spans forward tracking `{}`  brace balance until it returns to zero.
- **Fallback**: single matched line.

The line counts from block-scope matches contribute to `technique_region_lines`, which drives the region-based `technique_line_density` density metric.

---

## Phase 1 — Search (`search.py`)

Queries GitHub across up to five surfaces for each search phrase and identifier:

| Surface | API endpoint | Rate limit (authenticated) |
|---|---|---|
| Repositories | `/search/repositories` | 30 req/min |
| Code files | `/search/code` | 9 req/min (separate bucket) |
| Issues & PRs | `/search/issues` | 30 req/min |
| Commit messages | `/search/commits` | 30 req/min |
| Discussions | GraphQL `search()` | 5 000 pts/hr |

**Search vocabulary routing** — `identifiers` go to the code surface only (too many false positives on issues/commits for generic token names). `search_phrases` go to all surfaces.

**Adaptive date-range slicing** — any query returning more than `SLICE_THRESHOLD` results (default 900) is automatically split into date-range sub-queries and recursed up to `SLICE_MAX_DEPTH` levels, with each slice narrowed until it fits under GitHub's 1 000-result hard cap. This gives complete coverage rather than a truncated first-1 000 sample.

**Outputs** (`results/<slug>/raw/`):

| File | Contents |
|---|---|
| `repos.json` | Deduplicated repository records (name, stars, language, topics, description, creation date) |
| `code.json` | Code file match records |
| `issues.json` / `prs.json` | Issue and PR records |
| `commits.json` | Commit records |
| `discussions.json` | Discussion records |
| `summary.json` | Per-query hit counts + per-surface total counts + timestamp |

The `summary.json` top-level fields (`repos`, `code_files`, `issues`, `prs`, `commits`, `discussions`) drive the surface breakdown chart in Phase 4.

---

## Phase 2 — Clone (`clone.py`)

Reads `repos.json` (and optionally `code.json`) from Phase 1, deduplicates, applies optional filters (`--min-stars`, `--skip-forks`, `--lang`), then shallow-clones each qualifying repo.

- Repos larger than `MAX_REPO_SIZE_KB` (750 MB) are skipped and logged in Appendix D of the report.
- `CLONE_DEPTH=100` fetches the last 100 commits — sufficient for ≥93% of repos in the study and adequate for all commit history metrics. Set to `0` for full history.
- Already-cloned repos are skipped unless `--refresh` is passed.
- A clone manifest (`results/<slug>/cloned/manifest.json`) records every repo's clone status, local path, and metadata for Phase 3.

---

## Phase 3 — Analyse (`analyze.py`)

Walks every cloned repo and collects adoption signals. Runs in a `ProcessPoolExecutor` for per-repo parallelism (one worker process per CPU core by default).

### File scanning

For each file that passes extension filters (`SKIP_EXTENSIONS`, `SKIP_DIRS`):

1. File extension is mapped to a language name via `_EXT_TO_LANGUAGE` (44 mappings). This drives the **language distribution** metric from actual scanned files rather than the GitHub API language field.
2. Regex patterns from the technique's YAML are applied. For `scope: block` patterns, `_block_line_span()` estimates the enclosing block extent.
3. An NLTK lemmatization second pass (if `lemmatization.trigger` is set) scans comment and string literal tokens for inflected forms of technique concepts.
4. The top-level `README*` file is read separately (up to 40 KB) to augment domain inference.

### Per-repo metrics

**Coverage (Adoption Extent)**

| Metric | Description |
|---|---|
| `score` / `direct_matches` | Raw pattern match count — primary adoption measure |
| `technique_files` | Files containing at least one signal |
| `technique_lines` | Distinct `(file, line)` positions with a signal (raw matched lines) |
| `technique_region_lines` | Estimated technique-code lines including block extents from `scope: block` patterns |
| `technique_file_ratio` | `technique_files / total_files_scanned` |
| `technique_line_density` | `technique_region_lines / total_lines_scanned` — region-based density |
| `avg_mentions_per_technique_file` | Mean matches per file that has any signal |
| `max_mentions_in_file` | Maximum single-file match count |
| `patterns_matched` | List of distinct pattern labels that fired |

**Language breakdown**

`language_breakdown` records the count of scanned files per language for each repo, derived entirely from file extensions. Used for the language distribution chart and report table.

**Artifact type classification**

Each finding is classified by file-tree location:

| Type | Criteria |
|---|---|
| `test_code` | File in a test directory or matching test filename convention (`test_*`, `*_test.*`, `*_spec.*`) |
| `source_code` | Non-test source file with a recognized source extension |
| `documentation` | `.md`, `.rst`, `.txt`, `.tex`, `.html`, `.pdf`, etc. |
| `config` | `.yaml`, `.toml`, `.ini`, `.json`, `.gradle`, `.lock`, etc. |
| `other` | Everything else |

**Project type classification**

| Type | Signal |
|---|---|
| `general_usage` | Signals predominantly in test dirs — technique used in the project's own testing |
| `framework` | Signals predominantly in source dirs — project provides technique infrastructure |
| `research_artifact` | Name/description matches paper markers (`paper`, `evaluation`, `artifact`, `replication`) |
| `mixed` | Signals spread across both test and source |
| `documentation_only` / `unknown` | Weak or unclear signals |

**Domain inference**

Keywords are matched against repo name + description + GitHub topics + **README text** (first 4 KB). A repo can match multiple domains.

`domain_text_sample` (description + README intro, ≤2 KB) is stored per repo and used to generate the domain word cloud in Phase 4.

Default domain categories (overridable per-technique via `domain_keywords`):

`machine_learning` · `compiler` · `database` · `scientific` · `bioinformatics` · `security` · `web` · `autonomous_systems` · `testing_infrastructure` · `networking` · `systems`

**Git commit analysis**

From `git log --no-merges --format=%ae|%ai|%s` (last `CLONE_DEPTH` commits):

| Metric | Description |
|---|---|
| `contributor_count_git` | Unique author emails in sampled history |
| `total_commits_sampled` | Total commits in the sample window |
| `technique_commits_count` | Commits whose messages match `commit_keywords` |
| `technique_commit_ratio` | Fraction of sampled commits mentioning the technique |
| `first_technique_commit_date` / `last_technique_commit_date` | Temporal span of technique activity |
| `technique_commit_span_days` | Days between first and last technique commit |
| `technique_commit_dates` | Dates of all technique commits (for timeline plots) |
| `monthly_total_commits` / `monthly_technique_commits` | Monthly aggregates |

---

## Phase 4 — Plot (`plot.py`)

Generates all figures for a technique. Figures apply only to detected repositories (score > 0) unless otherwise noted. Requires `matplotlib`, `seaborn`, `pandas`, `numpy`, and optionally `wordcloud`.

**Outlier handling** — `_split_outliers(values)` uses the Tukey fence (Q3 + 1.5×IQR) to separate the main distribution from extreme outliers. Applied to `coverage_depth`, `keyword_density`, and both panels of `technique_ratios`. Outliers are excluded from the histogram body and annotated as "+N outliers (up to X)" so no data is lost.

### Figures generated

| Filename | What it shows |
|---|---|
| `detection_count_hist.png` | Rank plot: detection counts sorted descending with mean/median lines |
| `yearly_trend.png` | Repo creation year — total vs detected |
| `technique_ratios.png` | Two-panel: share of code that is technique code (line density); share of files using the technique (file ratio) |
| `contributor_dist.png` | Histogram: unique git contributors per detected repo |
| `project_metadata.png` | Three-panel boxplot: stars, repo age, file count — detected vs not-detected |
| `project_type_dist.png` | Bar: project role distribution (general usage / framework / research artifact / mixed) |
| `coverage_depth.png` | Histogram: files-with-signals per detected repo (outliers annotated) |
| `keyword_density.png` | Histogram: avg pattern matches per technique-containing file (outliers annotated) |
| `language_dist.png` | Bar: top 15 languages by detected repo count (from scanned file extensions) |
| `artifact_breakdown.png` | Horizontal stacked bar: signal matches by artifact type |
| `extension_breakdown.png` | Horizontal bar: top 15 file extensions by signal match count |
| `domain_dist.png` | Horizontal bar: inferred application domain frequencies |
| `domain_wordcloud.png` | Word cloud from domain text samples of detected repos (`wordcloud` required) |
| `domain_activity_over_time.png` | Multi-line: detected repos by domain and creation year (top 6 domains) |
| `pattern_freq.png` | Horizontal bar: pattern match frequency (top 20 patterns) |
| `commit_timeline.png` | Line: technique commits per year across all detected repos |
| `commit_first_year.png` | Histogram: year of first technique commit |
| `commit_last_year.png` | Histogram: year of last technique commit |
| `commit_span.png` | Histogram: years from first to last technique commit |
| `commit_ratio_dist.png` | Histogram: technique commit ratio distribution |
| `project_life_year.png` | Line: technique commits by year of repository life (year 1 = first year after creation) |
| `surface_breakdown.png` | Bar: total search results per surface from `summary.json` counts (Code / Repo / Commit / Issue / PR / Discussion) |
| `query_hits.png` | Horizontal bar: raw API hit counts per individual query |

---

## Phase 5 — Report (`report.py`)

Compiles `summary_report.md` from Phase 1, 3, and 4 outputs. Sections:

| Section | Contents |
|---|---|
| **Pipeline Summary** | Funnel table (candidates → cloned → analysed → detected); search surface table with results-per-surface counts; query hit counts |
| **Adoption Overview** | Detection rate and count distribution; project metadata (stars, age, files) detected vs not-detected; contributor activity |
| **Usage Patterns** | Project role classification; Detection Distribution (code vs non-code, technique coverage ratios, spread across files, histogram bins); language distribution; artifact type breakdown; file extension breakdown; application domain (with word cloud) |
| **Timeline** | Repo creation year trend; commit activity; first/last commit year; commit span and ratio; technique commits by year of repository life |
| **Top Detected Repositories** | Top-N detected repos by detection count |
| **Pattern Activity** | Per-pattern match counts across all repos |
| **Appendix A** | All not-detected repositories (sorted by stars) |
| **Appendix B** | Per-query API hit counts and per-label repo counts |
| **Appendix C** | Pattern reference table from the YAML |
| **Appendix D** | Clone errors and size-skipped repos |

---

## Running the Pipeline

### Environment setup

```bash
pip install -r requirements.txt
```

Create a `.env` file:

```
GITHUB_TOKEN=ghp_...
```

The token needs at minimum `public_repo` scope. Rate limits are handled automatically with per-endpoint delays and adaptive date-range slicing for high-volume queries.

### Full pipeline for one technique

```bash
python main.py --technique techniques/metamorphic_testing.yaml
python main.py --technique techniques/fuzzing.yaml
python main.py --technique techniques/property_based_testing.yaml
```

### Selective phases

```bash
# Search and clone only
python main.py --technique techniques/metamorphic_testing.yaml --stages 1 2

# Analyse existing clones, then plot and report
python main.py --technique techniques/metamorphic_testing.yaml --stages 3 4 5

# Regenerate just the report from existing analysis
python main.py --technique techniques/metamorphic_testing.yaml --stages 5

# Regenerate plots and report
python main.py --technique techniques/metamorphic_testing.yaml --stages 4 5
```

### Batch mode (all techniques)

```bash
# Run all YAMLs in techniques/ sequentially (safe default)
python main.py --all-techniques

# Run only analysis + report phases for all techniques
python main.py --all-techniques --stages 3 4 5

# Run 3 technique pipelines concurrently (phases 2–5 safe; phase 1 shares API limit)
python main.py --all-techniques --parallel-techniques 3
```

### Run phases directly

```bash
python search.py  --technique techniques/metamorphic_testing.yaml
python clone.py   --technique techniques/metamorphic_testing.yaml --min-stars 5 --workers 8
python analyze.py --technique techniques/metamorphic_testing.yaml --workers 8
python plot.py    --technique techniques/metamorphic_testing.yaml --format pdf --dpi 300
python report.py  --technique techniques/metamorphic_testing.yaml --refresh-plots
```

### Common options reference

| Option | Default | Phase | Description |
|---|---|---|---|
| `--stages N…` | 1 2 3 4 5 | — | Phases to run |
| `--workers N` | 4 | 2, 3 | Parallel clone / analysis workers (per-repo) |
| `--parallel-techniques N` | 1 | all | Concurrent technique pipelines in batch mode |
| `--surfaces …` | all 5 | 1 | GitHub search surfaces to query |
| `--no-slice` | off | 1 | Disable adaptive date-range slicing |
| `--max-pages N` | 10 | 1 | Pages per query / slice |
| `--min-stars N` | 0 | 2 | Skip repos below this star count |
| `--skip-forks` | off | 2 | Exclude forked repos |
| `--lang LANG` | any | 2 | Clone only repos of a given language |
| `--clone-limit N` | unlimited | 2 | Cap clones per run |
| `--clone-source` | both | 2 | Pull candidates from `repos`, `code`, or `both` |
| `--refresh` | off | 2 | Re-clone already-cloned repos |
| `--min-score N` | 0 | 3 | Exclude repos with score < N from outputs |
| `--append` | off | 3 | Merge into existing analysis outputs |
| `--cleanup-clones` | off | 3 | Delete clones after analysis |
| `--format png\|pdf\|svg` | png | 4, 5 | Plot output format |
| `--dpi N` | 150 | 4, 5 | Plot resolution |
| `--refresh-plots` | off | 5 | Force-regenerate plots |
| `--top-repos N` | 20 | 5 | Rows in top-repos report table |

### Parallelism

**Within a technique (phases 2 & 3):** `--workers N` controls per-repo concurrency. Bottleneck is disk I/O for cloning and CPU for analysis; 4–8 workers is typical.

**Across techniques:** `--parallel-techniques N` runs N full pipelines concurrently.
- Phase 1 (search) shares the 5 000 req/hr GitHub API budget. 2–3 concurrent techniques is safe; more may cause 429 errors.
- Phases 2–5 are fully independent per-technique and safe to parallelise freely.
- Recommended: run `--stages 1 --parallel-techniques 1` first, then `--stages 2 3 4 5 --parallel-techniques N`.

---

## Configuration (`config.py`)

Infrastructure settings shared by all phases. Technique-specific settings belong in the YAML.

| Setting | Default | Description |
|---|---|---|
| `CLONE_DEPTH` | `100` | Most-recent commits fetched per repo. Covers full history for ≥93% of repos in the study. Set to `0` for full history. |
| `MAX_REPO_SIZE_KB` | `750_000` | 750 MB — repos above this threshold are skipped in Phase 2 and listed in Appendix D |
| `SLICE_THRESHOLD` | `900` | Query result count that triggers adaptive date-range slicing in Phase 1 |
| `SLICE_MAX_DEPTH` | `6` | Maximum recursion depth for date-range slicing |
| `STANDARD_SEARCH_DELAY` | `2.2 s` | Inter-request delay for repo/issue/commit/PR search |
| `CODE_SEARCH_DELAY` | `7.0 s` | Inter-request delay for code search (separate, stricter rate limit) |
| `SKIP_EXTENSIONS` | *(50+ types)* | Binary, media, archive, model, font, and database extensions excluded from Phase 3 scanning |
| `DOC_EXTENSIONS` | see code | Extensions classified as documentation in artifact type analysis |
| `CONFIG_EXTENSIONS` | see code | Extensions classified as config/build files |
| `DOMAIN_KEYWORDS` | *(11 categories)* | Global keyword sets for domain inference; per-technique `domain_keywords` in the YAML overrides/extends these |
| `RESULTS_DIR` | `./results` | Output root (overridable via `RESULTS_DIR` env var) |
| `REPOS_DIR` | `./repos` | Clone root (overridable via `REPOS_DIR` env var) |

---

## Pipeline Timing Log

Each phase's elapsed time is appended to `results/<slug>/pipeline.log` as a JSONL record:

```json
{"phase": 3, "name": "Analyse", "elapsed": 142.7, "ts": "2026-09-07T10:23:01Z"}
```

---

## Output Structure

```
results/
  metamorphic_testing/
    raw/
      repos.json          repository search results (name, stars, language, topics, dates)
      code.json           code file match records
      issues.json
      prs.json
      commits.json
      discussions.json
      summary.json        per-query hit counts + per-surface totals + timestamp
    cloned/
      manifest.json       clone status, local path, and metadata for every candidate
    analysis/
      findings.json       per-file pattern matches (repo, file, line, label, artifact_type)
      repo_scores.json    per-repo scores + all derived metrics + domain_text_sample
      summary_report.md   Phase 5 report
      worker_logs/        per-worker file-scan logs (for debugging slow repos)
    plots/                all Phase 4 figures (PNG by default)
    pipeline.log          JSONL per-phase timing records

  fuzzing/                same structure, fully independent
  property_based_testing/ same structure, fully independent

repos/
  metamorphic_testing/    cloned repos (CLONE_DEPTH=100)
  fuzzing/
  property_based_testing/
```

---

## Detection Methodology

The pipeline detects **deliberate, explicit adoption** — not implicit patterns. It searches for:

- Technique-specific class names, function decorators, and macro invocations (via YAML `patterns`)
- Comments and string literals containing technique phrases
- NLTK lemmatization (for MT) to catch inflected forms in natural-language text
- Technique-tagged commit messages (for temporal analysis)

**Lower-bound estimates** — "Not detected" means no explicit signal was found in the default branch at clone time. It does **not** mean the technique is absent. Repos using non-standard terminology, alternative library names, vendored copies of technique code, or technique work on non-default branches will produce false negatives. All adoption rates are conservative lower bounds.

**Cross-technique rate comparisons require care** — different query volumes and vocabularies affect the denominator. Rates *within* a technique's dataset are the correct unit of comparison.

---

## Adding a New Technique

1. Copy an existing YAML as a template:
   ```bash
   cp techniques/metamorphic_testing.yaml techniques/my_technique.yaml
   ```

2. Edit the required fields:
   - `name`, `short_name`, `slug`, `color`
   - `search_phrases` — natural-language phrases for all surfaces
   - `identifiers` — specific code tokens for code-surface search (avoid generic single words)
   - `patterns` — regex patterns for local scanning; add `scope: block` to structural patterns (class/function/macro definitions)
   - `commit_keywords` — commit message keywords for temporal analysis
   - `domain_keywords` — optional domain→keywords map for improved domain inference

3. Run the pipeline:
   ```bash
   python main.py --technique techniques/my_technique.yaml
   ```

4. Results appear in `results/my_technique/` and `repos/my_technique/`.

---

## Generating Example Reports

`generate_example.py` produces synthetic example reports using real plot and report code — useful for previewing layout changes without running the full pipeline:

```bash
python generate_example.py
# Outputs to: example_reports/{technique}/analysis/summary_report.md
#             example_reports/{technique}/plots/*.png
```

---

## Dependencies

```
requests, python-dotenv       — Phase 1 (HTTP + env)
GitPython                     — Phase 2 (cloning)
nltk                          — Phase 3 (lemmatization)
pandas, numpy                 — Phase 4 (data manipulation)
matplotlib, seaborn           — Phase 4 (plotting)
wordcloud                     — Phase 4 (domain word cloud, optional — degrades gracefully)
rich                          — CLI progress bars and console output
pyyaml                        — technique YAML loading
```

Install everything:
```bash
pip install -r requirements.txt
```

---

## Interpretation Notes

- **Detection rates are lower bounds** — terminology-matching misses repos using the technique without standard vocabulary.
- **"Not detected" ≠ "does not use the technique"** — non-default branches, different terminology, vendored dependencies, and proprietary code all cause false negatives.
- **`score` / `direct_matches` is the primary metric** — a continuous count, not a binary flag.
- **`technique_line_density` uses region-based line counts** — `scope: block` patterns contribute their full enclosing block, so this is a structural coverage estimate, not just a raw match count.
- **Language distribution is from scanned files, not GitHub API** — the `language_breakdown` field counts files per language found during Phase 3, giving a multi-language view rather than the API's single primary-language field.
- **Commit history is sampled** — `CLONE_DEPTH=100` gives complete history for the vast majority of repos. The ~7% of repos with deeper histories have their early commit activity truncated.
- **Domain inference uses README text** — the top-level README (up to 40 KB) is read alongside name/description/topics for richer domain matching, and the first 2 KB contributes to the word cloud corpus.
