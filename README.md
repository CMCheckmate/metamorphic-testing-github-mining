# GitHub Mining — Testing Technique Adoption Study

A pipeline for mining GitHub to measure the real-world adoption of software testing techniques. Designed for comparative research — each technique is defined by a YAML file, and the same five-phase pipeline runs for all of them.

---

## How the new system works

The pipeline is now **technique-agnostic**. Instead of hardcoded Metamorphic Testing constants, every technique-specific setting (search queries, code patterns, report customisation) lives in a YAML file under `techniques/`. You point any phase at a YAML file with `--technique`, and it does the right thing for that technique.

### Technique profiles (`techniques/*.yaml`)

Each file defines:

| Field | Purpose |
|---|---|
| `name`, `short_name` | Display names used in reports and plot titles |
| `color` | Hex colour for this technique's bars/lines in comparative plots |
| `search_phrases` | Words/phrases for GitHub search queries across all surfaces |
| `identifiers` | Code-level tokens (class names, function names) used in code queries |
| `patterns` | Regex patterns used in Phase 3's local file scan |
| `classification_strong` / `classification_weak` | Score thresholds for classification tiers |
| `lemmatization` | NLTK lemmatization config (disable by setting `trigger: ""`) |
| `report_intro` | Opening paragraph used in the technique's individual report |
| `extra_report_sections` | Optional list of additional sections: `"mt_context"`, `"framework_vs_adopter"` |

Provided techniques:

| File | Technique | Focus |
|---|---|---|
| `metamorphic_testing.yaml` | Metamorphic Testing (MT) | Primary study subject; includes MT-context and oracle problem sections |
| `property_based_testing.yaml` | Property-Based Testing (PBT) | Hypothesis, QuickCheck, ScalaCheck, jqwik, proptest, fast-check |
| `fuzzing.yaml` | Fuzzing | libFuzzer, atheris, AFL, Go native fuzz, Jazzer, cargo-fuzz, OSS-Fuzz |
| `mutation_testing.yaml` | Mutation Testing | PIT/pitest, mutmut, Stryker, cargo-mutants, infection |
| `differential_testing.yaml` | Differential Testing | DifferentialTest, TestOracle, csmith, yarpgen, cross-implementation comparison |

---

## Five-phase pipeline

```
Phase 1 — Search     query GitHub API across 5 surfaces → results/<slug>/raw/
Phase 2 — Clone      shallow-clone candidate repos      → repos/<slug>/
Phase 3 — Analyse    scan local files for patterns       → results/<slug>/analysis/
Phase 4 — Plot       generate figures                    → results/<slug>/plots/
Phase 5 — Report     write Markdown report               → results/<slug>/analysis/summary_report.md
```

All outputs for a technique are isolated under `results/<slug>/` and `repos/<slug>/`.

---

## Running the pipeline

### Run all five phases for a single technique

```bash
python main.py --technique techniques/metamorphic_testing.yaml
python main.py --technique techniques/fuzzing.yaml
python main.py --technique techniques/property_based_testing.yaml
python main.py --technique techniques/mutation_testing.yaml
python main.py --technique techniques/differential_testing.yaml
```

### Run specific phases only

```bash
# Phase 1 and 2 only (search + clone)
python main.py --technique techniques/metamorphic_testing.yaml --stages 1 2

# Phases 3–5 (analyse existing clones, then report)
python main.py --technique techniques/metamorphic_testing.yaml --stages 3 4 5

# Regenerate just the report from existing analysis outputs
python main.py --technique techniques/metamorphic_testing.yaml --stages 5

# Regenerate plots and report
python main.py --technique techniques/metamorphic_testing.yaml --stages 4 5 --refresh-plots
```

### Common options

```bash
--stages 1 2 3 4 5          # which phases to run (default: all)
--workers N                  # parallel workers for clone and analyse (default: 4)
--min-stars N                # skip repos with fewer than N stars (Phase 2)
--skip-forks                 # exclude forks (Phase 2)
--lang Python                # only clone repos in a specific language (Phase 2)
--clone-limit N              # cap the number of clones in this run
--append                     # merge new analysis results with existing outputs
--cleanup-clones             # delete each clone after analysis (saves disk)
--format png|pdf|svg         # plot output format (default: png)
--dpi N                      # plot resolution (default: 150)
--top-repos N                # top N repos listed in Q8 of the report (default: 20)
--refresh-plots              # force-regenerate plots in Phase 5
```

### Run a single phase directly

Each phase module also works standalone:

```bash
python search.py  --technique techniques/metamorphic_testing.yaml
python clone.py   --technique techniques/metamorphic_testing.yaml --min-stars 5
python analyze.py --technique techniques/metamorphic_testing.yaml --workers 8
python plot.py    --technique techniques/metamorphic_testing.yaml --format pdf
python report.py  --technique techniques/metamorphic_testing.yaml --top-repos 30
```

---

## Generating the comparative report

After running the pipeline for at least two techniques, run:

```bash
python combine.py
```

This auto-discovers completed analyses in `results/*/analysis/repo_scores.json` and writes:

```
results/combined/comparative_report.md   — cross-technique research report
results/combined/plots/                  — comparative figures:
  adoption_rates.png           bar chart: explicit adoption rate per technique
  repo_counts.png              stacked bar: strong/weak/none breakdown
  yearly_trend_comparison.png  multi-line trend by repo creation year
  language_heatmap.png         heatmap: language distribution per technique
  score_distributions.png      box plot: match-score spread among adopters
```

Options:

```bash
python combine.py --format pdf --dpi 300
python combine.py --techniques metamorphic_testing fuzzing   # include only specific slugs
python combine.py --output path/to/my_report.md
```

---

## Output structure

```
results/
  metamorphic_testing/
    raw/
      repos.json                 # repos returned by GitHub search
      code.json                  # code search results
      issues.json
      commits.json
      discussions.json
      summary.json               # per-query hit counts
    cloned/
      manifest.json              # which repos were cloned and their metadata
    analysis/
      findings.json              # per-file pattern matches
      repo_scores.json           # per-repo scores and classification
      summary_report.md          # final Phase 5 report  ← read this
      worker_logs/               # per-worker scan logs for debugging
    plots/                       # all Phase 4 figures

  property_based_testing/        # same structure, isolated from MT
  fuzzing/
  mutation_testing/
  differential_testing/

  combined/
    comparative_report.md        # combine.py output  ← read this
    plots/                       # comparative figures

repos/
  metamorphic_testing/           # shallow clones, one folder per repo
  property_based_testing/
  ...
```

---

## Environment setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with your GitHub token:

```
GITHUB_TOKEN=ghp_...
```

The token must have at minimum `public_repo` scope. Rate limits are handled automatically.

---

## Adding a new technique

1. Create `techniques/my_technique.yaml` — copy an existing YAML as a template.
2. Set `name`, `short_name`, `color`, `search_phrases`, `identifiers`, `patterns`.
3. Run the pipeline:
   ```bash
   python main.py --technique techniques/my_technique.yaml
   ```
4. The new technique's results automatically appear in `combine.py` output.

---

## Individual report sections (Q1–Q8)

Each technique's `summary_report.md` covers:

| Section | Question answered |
|---|---|
| **Glossary** | How search works, pattern table, classification tier definitions |
| **Funnel** | How many repos were found, cloned, analysed, and classified |
| **Q1 Prevalence** | What fraction of repos show explicit adoption? |
| **Q2 Trend** | How has adoption changed over time? |
| **Q3 Language** | Which programming languages dominate? |
| **Q4 Domain** | What application domains use the technique? |
| **Q5 Maturity** | Does adoption correlate with project stars/age? |
| **Q6 Authors** | Is adoption concentrated in few owners? |
| **Q7 Coverage** | How broadly is the technique used within adopting repos? |
| **Q8 Patterns** | Which specific patterns appear most, and what are the top repos? |
| **MT context** | *(MT only)* Oracle problem background, MR taxonomy |
| **Framework vs Adopter** | *(MT + others)* Are pattern matches in test code or framework code? |

---

## Files

```
main.py                      Pipeline orchestrator (--technique required)
search.py                    Phase 1: GitHub search
clone.py                     Phase 2: shallow clone
analyze.py                   Phase 3: local file scan
plot.py                      Phase 4: figure generation
report.py                    Phase 5: Markdown report
combine.py                   Cross-technique comparative report
config.py                    Infrastructure settings + TechniqueProfile class
techniques/
  metamorphic_testing.yaml
  property_based_testing.yaml
  fuzzing.yaml
  mutation_testing.yaml
  differential_testing.yaml
requirements.txt
```
