# GitHub Mining — Testing Technique Adoption Study

A five-phase pipeline for mining GitHub to measure the real-world adoption of software testing techniques. Designed for comparative research — each technique is defined by a YAML file, and the same pipeline runs for all of them.

---

## How It Works

The pipeline is **technique-agnostic**. Every technique-specific setting (search queries, patterns, report labels) lives in a YAML file under `techniques/`. Point any phase at a YAML with `--technique` and it handles the rest.

### Technique profiles (`techniques/*.yaml`)

| Field | Purpose |
|---|---|
| `name`, `short_name` | Display names used in reports and plot titles |
| `color` | Hex colour for this technique in comparative plots |
| `search_phrases` | Natural-language phrases for GitHub search |
| `identifiers` | Code-level tokens (class names, decorators) for code search |
| `commit_keywords` | Keywords for matching technique-related commits in git log analysis |
| `domain_hints` | Expected over-represented domains (informational only) |
| `patterns` | Regex patterns for Phase 3 local file scan |
| `classification.strong_threshold` / `classification.weak_threshold` | Score thresholds for classification tiers (for manual review prioritisation) |
| `lemmatization` | NLTK lemmatization config (catches inflected forms in comments/strings) |
| `extra_report_sections` | Optional list: `"mt_context"` (MT oracle problem background) |
| `report_intro` | Opening paragraph in the technique's individual report |

Provided techniques:

| File | Technique | Notes |
|---|---|---|
| `metamorphic_testing.yaml` | Metamorphic Testing (MT) | Primary study subject; MT context section enabled |
| `property_based_testing.yaml` | Property-Based Testing (PBT) | Hypothesis, QuickCheck, ScalaCheck, jqwik, proptest, fast-check |
| `fuzzing.yaml` | Fuzzing | libFuzzer, atheris, AFL, Go native fuzz, Jazzer, cargo-fuzz, OSS-Fuzz |

---

## Five-Phase Pipeline

```
Phase 1 — Search     query GitHub API across 6 surfaces → results/<slug>/raw/
Phase 2 — Clone      shallow-clone candidate repos       → repos/<slug>/
Phase 3 — Analyse    scan local files for patterns       → results/<slug>/analysis/
Phase 4 — Plot       generate figures                    → results/<slug>/plots/
Phase 5 — Report     write Markdown report               → results/<slug>/analysis/summary_report.md
```

All outputs for a technique are isolated under `results/<slug>/` and `repos/<slug>/`.

---

## Running the Pipeline

### Full pipeline for a single technique

```bash
python main.py --technique techniques/metamorphic_testing.yaml
python main.py --technique techniques/fuzzing.yaml
python main.py --technique techniques/property_based_testing.yaml
```

### Run all techniques in a folder (batch mode)

```bash
# Sequential (safe default — avoids API rate limit conflicts during search)
python main.py --all-techniques

# Specify a custom folder
python main.py --all-techniques --techniques-dir techniques/

# Run only specific phases for all techniques
python main.py --all-techniques --stages 3 4 5

# Parallel batch — run 3 techniques concurrently (see parallelism notes below)
python main.py --all-techniques --parallel-techniques 3
```

### Selective phases

```bash
# Search and clone only
python main.py --technique techniques/metamorphic_testing.yaml --stages 1 2

# Analyse existing clones, then plot and report
python main.py --technique techniques/metamorphic_testing.yaml --stages 3 4 5

# Regenerate just the report from existing analysis
python main.py --technique techniques/metamorphic_testing.yaml --stages 5
```

### Common options

```bash
--stages 1 2 3 4 5          which phases to run (default: all)
--workers N                  parallel workers for clone and analyse within each technique (default: 4)
--parallel-techniques N      run N technique pipelines concurrently in batch mode (default: 1)
--min-stars N                skip repos with fewer than N stars (Phase 2)
--skip-forks                 exclude forked repositories (Phase 2)
--lang Python                only clone repos in a specific language (Phase 2)
--clone-limit N              cap number of clones in this run
--append                     merge new analysis results with existing outputs
--cleanup-clones             delete each clone after analysis (saves disk)
--format png|pdf|svg         plot output format (default: png)
--dpi N                      plot resolution (default: 150)
--refresh-plots              force-regenerate plots in Phase 5
```

### Parallelism notes

The pipeline has two levels of parallelism:

**Within a single technique (phases 2 & 3):**
`--workers N` controls how many repos are cloned / analysed in parallel. The bottleneck is disk I/O for cloning and CPU for analysis. 4–8 workers is a good default; go higher if you have fast SSD and many cores.

**Across techniques (batch mode):**
`--parallel-techniques N` runs N full technique pipelines concurrently using threads.
- **Phase 1 (search)** shares the GitHub API rate limit (5 000 requests/hour per token). Running 2–3 techniques in parallel is generally safe; more may trigger 429 rate-limit errors. Use `--parallel-techniques 1` (the default) for the safest search.
- **Phases 2–5** are fully independent per technique (separate directories) and safe to parallelise without limit.
- If you want to search sequentially but clone/analyse in parallel, run `--stages 1` with `--parallel-techniques 1` first, then re-run `--stages 2 3 4 5 --parallel-techniques N`.

### Run a single phase directly

```bash
python search.py  --technique techniques/metamorphic_testing.yaml
python clone.py   --technique techniques/metamorphic_testing.yaml --min-stars 5
python analyze.py --technique techniques/metamorphic_testing.yaml --workers 8
python plot.py    --technique techniques/metamorphic_testing.yaml --format pdf
python report.py  --technique techniques/metamorphic_testing.yaml
```

---

## Generating the Comparative Report

After running the pipeline for at least two techniques:

```bash
python combine.py
```

This auto-discovers completed analyses in `results/*/analysis/repo_scores.json` and produces:

```
results/combined/comparative_report.md
results/combined/plots/
```

Options:

```bash
python combine.py --format pdf --dpi 300
python combine.py --techniques metamorphic_testing fuzzing
python combine.py --output path/to/my_report.md
```

---

## What Is Analysed

### Detection methodology

The pipeline detects **deliberate, explicit adoption** of a technique — not implicit patterns. It searches for:

- Explicit use of technique terminology in code (class names, function names, decorators)
- Comments and string literals mentioning technique concepts
- NLTK lemmatization (for MT) to catch inflected forms (e.g. "metamorphically")

**Important:** "Not detected" means the pipeline found no explicit signals in the default branch at the time of cloning. It does **not** mean the repository does not use the technique. Repos using non-standard terminology, alternative library names, or with technique code in non-default branches will not be captured. All detection rates are **lower-bound estimates**.

### Phase 3 analysis — per-repo metrics

**Coverage metrics (Adoption Extent)**
- `total_files_scanned` — total source-like files walked in the repo
- `total_lines_scanned` — total lines across those files
- `technique_files` — number of files with at least one technique signal
- `technique_lines` — number of distinct (file, line) positions with signals
- `technique_file_ratio` — fraction of scanned files with signals (continuous coverage measure)
- `technique_line_density` — fraction of scanned lines with signals
- `score` / `direct_matches` — raw pattern match count (primary continuous adoption measure)

**Keyword intensity (Usage Patterns)**
- `avg_mentions_per_technique_file` — mean pattern matches across all files that contain signals
- `max_mentions_in_file` — highest single-file match count
- `patterns_matched` — list of distinct pattern labels that fired

**Artifact type breakdown (How MT Is Used)**
Each finding is classified by where in the file tree it appears:
- `test_code` — file in a test directory or matching test filename convention
- `source_code` — non-test source file
- `documentation` — `.md`, `.rst`, `.txt`, `.tex`, etc.
- `config` — `.yaml`, `.toml`, `.json`, build files, etc.

`artifact_breakdown` records counts per type for each repo.

**Project type classification (How MT Is Used)**
- `general_usage` — technique signals predominantly in test directories (project *uses* the technique to test its own code)
- `framework` — signals predominantly in source directories (project *provides* technique infrastructure)
- `research_artifact` — repo appears to be a paper replication package or empirical dataset
- `mixed` — signals spread across both test and source
- `documentation_only` / `unknown`

**Domain inference (Application Domain)**
Keyword matching on repo name, description, and GitHub topics against 9 domain categories:
- `machine_learning`, `compiler`, `database`, `scientific`, `bioinformatics`, `security`, `web`, `autonomous_systems`, `testing_infrastructure`

A repo can match multiple domains.

**Git commit analysis (Timeline / Development Process)**
From `git log --no-merges --format=%ae|%ai|%s` on the last 500 commits (configurable via `CLONE_DEPTH`):
- `contributor_count_git` — unique author emails in sampled history
- `total_commits_sampled` — total commits in the sample window
- `technique_commits_count` — commits whose messages match `commit_keywords`
- `technique_commit_ratio` — fraction of sampled commits mentioning the technique
- `first_technique_commit_date` / `last_technique_commit_date` — temporal span of technique activity
- `technique_commit_span_days` — days between first and last technique commit
- `technique_commit_dates` — list of dates of technique commits
- `monthly_total_commits` / `monthly_technique_commits` — monthly aggregates for timeline plots

---

## Individual Report Sections

Each technique's `summary_report.md` contains:

| Section | What it shows |
|---|---|
| **How to Read** | Glossary, pattern table, classification tier definitions, heuristic limitation caveat |
| **Pipeline Funnel** | Repos found → cloned → analysed → detected, plus raw search API hit counts per surface |
| **Adoption Prevalence** | Detection rates, detection count distribution (histogram + CDF), code vs non-code mention breakdown, file coverage ratio, line density |
| **Project Scale** | Stars distribution, owner concentration, git contributor count |
| **Project Classification** | Project type (general usage / framework / research artifact / mixed), artifact type breakdown, files-with-signal distribution, keyword density |
| **Usage Patterns** | Language distribution, inferred domain distribution, pattern frequency, top detected repositories |
| **Temporal Analysis** | Repo creation year trend, aggregate technique commit timeline, commit ratio distribution, commit span |
| **Appendix A — All Repositories** | Complete table of all analysed repos with score, project type, language, stars |
| **Appendix B — Query Statistics** | Per-query API hit counts and distinct repo match counts |
| **MT Context** | *(MT only)* Oracle problem background, MT vs other approaches, metamorphic relation taxonomy |

---

## Comparative Report Sections

`results/combined/comparative_report.md` covers:

| Section | What it shows |
|---|---|
| **Overview** | Detection rates and detection count statistics per technique |
| **Adoption Overview** | Bar charts of detection rates; artifact type breakdown; technique coverage ratios; contributor counts |
| **Usage Patterns** | Project role; signal location in test infrastructure; language, artifact, extension, and domain breakdowns |
| **Timeline** | Multi-line trend by repo creation year; commit span and commit ratio distributions |
| **Conclusions** | Findings, limitations, future work |

---

## Output Structure

```
results/
  metamorphic_testing/
    raw/
      repos.json              repos returned by GitHub search (with description, topics)
      code.json               code search results
      issues.json
      commits.json
      discussions.json
      summary.json            per-query hit counts
    cloned/
      manifest.json           clone manifest (includes description, topics, local path)
    analysis/
      findings.json           per-file pattern matches (with artifact_type)
      repo_scores.json        per-repo scores + all derived metrics
      summary_report.md       Phase 5 report
      worker_logs/            per-worker scan logs (for debugging)
    plots/                    all Phase 4 figures

  property_based_testing/     same structure, isolated from MT
  fuzzing/

  combined/
    comparative_report.md     combine.py output
    plots/                    comparative figures

repos/
  metamorphic_testing/        clones (depth=500 by default)
  property_based_testing/
  ...
```

---

## Environment Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file:

```
GITHUB_TOKEN=ghp_...
```

The token needs at minimum `public_repo` scope. Rate limits are handled automatically with delays and adaptive date-range slicing.

---

## Configuration

Key settings in `config.py`:

| Setting | Default | Purpose |
|---|---|---|
| `CLONE_DEPTH` | `500` | Number of most-recent commits fetched per repo. Set to `0` for full history (slow). |
| `MAX_REPO_SIZE_KB` | `750000` | Repos larger than this are skipped in Phase 2 |
| `SLICE_THRESHOLD` | `900` | GitHub query result count that triggers date-range slicing |
| `DOC_EXTENSIONS` | see code | Extensions classified as documentation in artifact type analysis |
| `CONFIG_EXTENSIONS` | see code | Extensions classified as config/build files |
| `DOMAIN_KEYWORDS` | see code | Keyword sets for domain inference (9 categories) |

---

## Adding a New Technique

1. Create `techniques/my_technique.yaml` — copy an existing YAML as a template.
2. Set `name`, `short_name`, `color`, `search_phrases`, `identifiers`, `commit_keywords`, `patterns`.
3. Run the pipeline:
   ```bash
   python main.py --technique techniques/my_technique.yaml
   ```
4. Results appear in `results/my_technique/` and are automatically included in `combine.py` output.

---

## Interpretation Notes

- **Detection rates are lower bounds** — terminology-matching misses repos using the technique without standard vocabulary.
- **"Not detected" ≠ "does not use the technique"** — non-default branches, different terminology, vendored dependencies all cause false negatives.
- **Raw detection counts, not tiers, are the primary metric** — the strong/weak tiers exist only to prioritise manual inspection.
- **Cross-technique rate comparisons require care** — different query breadths affect the denominator. Rates within a technique's own dataset are the correct unit of comparison.
- **Commit history is sampled** — with `CLONE_DEPTH=500`, only the 500 most-recent commits are analysed. Projects with long histories have incomplete commit timelines.
