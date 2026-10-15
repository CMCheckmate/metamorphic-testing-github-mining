# GitHub Repository Usage Classification Process

## Overview

This document describes a reusable pipeline for classifying GitHub repositories
identified as **"usage"** repositories by any technique-mining pipeline — i.e.,
repositories that contain technique-phrase matches in source or test code files.
The goal is to produce two enriched output tables:

1. **Usage Classification** — what role the technique plays in the project
   (actual usage, framework/library, research artefact, or other)
2. **Application Domain Classification** — what application domain the project
   belongs to (web, ML, database, etc.)

The pipeline has three phases:

```
Phase 1: 01_consolidate.py  →  batch JSON files
Phase 2: LLM Classification →  results/all_classifications.json
Phase 3: 02_generate_outputs.py  →  CSVs + PNG charts
```

This process can be re-run whenever the underlying mining pipeline produces a
new `usage_repos_for_review.csv`, or extended to a different testing technique
by changing the technique description in the prompt (see Phase 2).

---

## Inputs

The pipeline requires one mandatory input file and two optional enrichment files:

### Mandatory

**`usage_repos_for_review.csv`** — one row per usage repository, with columns:

| Column | Description |
|--------|-------------|
| `repo` | GitHub full name (`owner/name`) |
| `url` | Repository URL |
| `stars` | GitHub star count |
| `language` | GitHub primary language |
| `scan` | Raw scan JSON blob (internal pipeline field) |
| `technique_test_files` | Count of technique-phrase hits in test files |
| `technique_nontest_files` | Count of technique-phrase hits in non-test source files |
| `code_files` | Total code files |
| `sample_technique_files` | Pipe-separated list of up to 5 representative technique-file paths |
| `description` | GitHub repository description |
| `readme_excerpt` | First ~600 characters of README |
| `manual_label` | Human-assigned label (may be empty) |
| `manual_notes` | Human notes (may be empty) |

### Enrichment files (produced by the mining pipeline's clone/scan phase)

These files are outputs of the upstream mining pipeline, which clones every repo
to scan for technique phrases. They are present whenever the mining pipeline has run.

- **`cloned_repo_metadata.json`** — `{ "owner/name": { "topics": [...], "created_at": "...", "description": "...", "stars": N, "language": "..." } }` —
  topic tags, creation date, and GitHub metadata. Typically covers **all** repos in
  the usage CSV. Used to populate `topics` and `created_at` in each batch entry.

- **`repo_readmes.json`** — `{ "owner/name": "<full README text>" }` — extends the
  README excerpt to up to 3,000 characters per repo. Coverage depends on how many
  repos had a README at clone time (e.g. ~30% for MT). Repos without an entry fall
  back to the 600-char `readme_excerpt` in the CSV, or classify from file paths only.

These are merged in Phase 1. If absent, classification proceeds from the CSV alone.

---

## Directory Structure

```
<WORK_DIR>/
├── <TECHNIQUE_DIR>/                         ← Pipeline output (input to this process)
│   ├── sections_report/
│   │   └── usage_repos_for_review.csv       ← Mandatory input
│   └── analysis/
│       ├── repo_readmes.json                ← Optional enrichment
│       └── cloned_repo_metadata.json        ← Optional enrichment
└── classification/                          ← This pipeline's workspace
    ├── 01_consolidate.py                    ← Phase 1: data preparation
    ├── 02_generate_outputs.py               ← Phase 3: CSV + chart generation
    ├── batches/                             ← Batch files for LLM input
    │   ├── manifest.json
    │   └── batch_000.json … batch_NNN.json
    ├── results/
    │   └── all_classifications.json         ← LLM output (Phase 2 result)
    └── outputs/
        ├── usage_classification.csv
        ├── domain_classification.csv
        └── charts/
            ├── usage_distribution.png
            ├── domain_distribution.png
            ├── usage_distribution_filtered.png    ← medium+ confidence only
            └── domain_distribution_filtered.png
```

Set `USAGE_CSV`, `READMES_JSON`, and `METADATA_JSON` at the top of
`01_consolidate.py` to point to wherever these files live for your technique.

---

## Phase 1 — Data Consolidation

**Script:** `01_consolidate.py`
**Input:** `usage_repos_for_review.csv` + optional enrichment JSONs
**Output:** `batches/batch_NNN.json` (one per batch), `batches/manifest.json`

```bash
cd "<WORK_DIR>/classification"
python3 -I 01_consolidate.py
```

This merges per repo:
- Description + 600-char README excerpt from the CSV
- Full README text (up to 3,000 chars) from `repo_readmes.json` where available
- Topics, creation date from `cloned_repo_metadata.json` where available

Tune `BATCH_SIZE` (default: 50) and `README_MAX_CHARS` (default: 3000) at the
top of the script to trade off batch count vs. token cost per agent.

---

## Phase 2 — LLM Classification

**Tool:** Claude Code Workflow (multi-agent, parallel batches)
**Input:** `batches/batch_NNN.json` files
**Output:** `results/all_classifications.json`

### How it works

Each batch file is sent to a Claude Sonnet agent with a structured classification
prompt (see below). The agents run in parallel across batches; each agent reads
its batch JSON, classifies every repository, and returns a JSON array of
classification objects. The workflow collects these and merges them into a single
`all_classifications.json`. Phase 3 then consumes that file to produce the final
CSVs and charts.

The classification is **multi-label**: a repository may receive more than one
usage type (e.g. both `research_artifact` and `framework_library`). Domain labels
are also multi-label.

### Classification categories

#### Usage labels

| Label | Description | Key signals |
|-------|-------------|-------------|
| `actual_usage` | Project uses the technique to test its own software | Test files with technique code; README describes testing a real system |
| `framework_library` | Project IS a technique framework / library / tool | README describes an API for writing technique tests; ships as a dependency |
| `research_artifact` | Academic research code — evaluation or replication package | arXiv/DOI link; "empirical study"/"experiment"; conference/journal name |
| `other_usage` | Doesn't fit the above categories | See sub-types below |

#### `other_usage` sub-types

When `other_usage` is `true`, also populate `other_usage_subtype` with one of:

| Sub-type code | Description | Distinguishing signals |
|---------------|-------------|------------------------|
| `other:agent` | **AI-agent configuration / aspirational mention** (~40% of Other) — An AI coding agent (Claude Code, Cursor, Copilot Agent, etc.) has written the technique vocabulary into an agent instruction file or skill definition as a principle to apply, without implementing any actual tests against the software under test. | Technique phrase in `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.cursor/rules`, `skills/`, `agent-guide/` or similar planning docs; repo created 2025–2026; high agent-marked commit share |
| `other:tutorial` | **Tutorial / course / self-learning** (~30% of Other) — An educational or personal-learning repository where the technique is mentioned or partially demonstrated but there is no real software under test. | Description mentions tutorial, course, homework, assignment, exercise, lecture, challenge; trivial toy SUT; "X-Days-Challenge"-style repo name |
| `other:incidental` | **General tool with incidental mention** (~20% of Other) — A general-purpose tool or application where the technique phrase appears in documentation, a README checklist, or a best-practice reference file, without any technique implementation in code. | Technique phrase in a single doc file only (not in code); README lists technique among many others without describing application; checklist / quality-standard file pattern |
| `other:indexed` | **Translated / indexed content** (~10% of Other) — Aggregates, translates, mirrors, or indexes technique resources (papers, links, summaries) without implementing the technique. | Technique phrase in translated excerpts, publication-list `.md` files, or `caches/translations_*` dirs; no software under test |

#### Application Domain labels (multi-label; `dom_no_match` when nothing fits)

| Label | Domain |
|-------|--------|
| `dom_web_api` | REST/HTTP APIs, web services, web applications |
| `dom_database` | Databases, SQL/NoSQL, ORMs, storage engines |
| `dom_security_crypto` | Security, cryptography, vulnerability detection, auth |
| `dom_finance` | Financial systems, trading, DeFi |
| `dom_machine_learning` | ML models, deep learning, NLP, LLM applications |
| `dom_compiler_pl` | Compilers, parsers, type systems, static analysis |
| `dom_scientific_computing` | Physics/chemistry simulation, numerical computing |
| `dom_distributed_systems` | Distributed computing, consensus, microservices |
| `dom_operating_systems` | OS kernels, process/memory management |
| `dom_embedded_iot` | Embedded systems, firmware, microcontrollers, RTOS |
| `dom_bioinformatics` | Genomics, DNA/RNA/protein analysis |
| `dom_autonomous_robotics` | Robotics, self-driving, SLAM |
| `dom_no_match` | No clear application domain |

### Core classification prompt (embeddable)

Replace `[TECHNIQUE]` and `[TECHNIQUE DESCRIPTION]` for a different technique:

```
You are a research assistant classifying GitHub repositories that contain
[TECHNIQUE] references, for a research study on [TECHNIQUE] adoption on GitHub.

[TECHNIQUE DESCRIPTION — 2-3 sentences explaining what the technique is]

STEP 1: Read your batch file (path provided separately).
Each object has: repo, url, stars, language, technique_test_files,
technique_nontest_files, sample_technique_files, description, topics, readme.

STEP 2: For each repo, classify:

USAGE (multi-label — assign all that apply):
- actual_usage: Project uses [TECHNIQUE] to test its own software
- framework_library: Project IS a [TECHNIQUE] tool/library/framework
- research_artifact: Academic research code involving [TECHNIQUE]
- other_usage: Doesn't fit any of the above (describe in other_usage_description
  and set other_usage_subtype to one of: other:agent, other:tutorial,
  other:incidental, other:indexed — see classification scheme)

DOMAIN (multi-label — dom_no_match when nothing fits):
[paste domain list from table above]

Return: {"classifications": [...]} with one entry per repo matching the output
schema below.
```

### Output JSON schema

```json
{
  "repo": "owner/name",
  "actual_usage": true,
  "framework_library": false,
  "research_artifact": false,
  "other_usage": false,
  "other_usage_subtype": "",
  "usage_confidence": "high",
  "usage_reasoning": "README describes REST API testing with metamorphic relations...",
  "other_usage_description": "",
  "dom_web_api": true,
  "dom_database": false,
  "dom_security_crypto": false,
  "dom_finance": false,
  "dom_machine_learning": false,
  "dom_compiler_pl": false,
  "dom_scientific_computing": false,
  "dom_distributed_systems": false,
  "dom_operating_systems": false,
  "dom_embedded_iot": false,
  "dom_bioinformatics": false,
  "dom_autonomous_robotics": false,
  "dom_no_match": false,
  "domain_confidence": "high",
  "domain_reasoning": "Project is a REST API testing tool."
}
```

`other_usage_subtype` should be one of `other:agent`, `other:tutorial`,
`other:incidental`, `other:indexed`, or empty string when `other_usage` is false.

### Repeating the workflow

1. Re-run `01_consolidate.py` to produce fresh batch files.
2. Invoke the Workflow tool with the parallel-batch script (adjust `TECHNIQUE`,
   `TECHNIQUE_DESC`, and `BATCHES_DIR` at the top of the script):

```
Use the Workflow tool with the script below to classify [N] usage repos in
parallel batches.
(paste workflow script)
```

Or save the script to a `.js` file and invoke with `Workflow({scriptPath: "..."})`.

---

## Phase 3 — Output Generation

**Script:** `02_generate_outputs.py`
**Input:** `results/all_classifications.json`
**Output:** Two CSVs + four PNG charts in `outputs/`

```bash
cd "<WORK_DIR>/classification"
python3 -I 02_generate_outputs.py
```

The script:
- Merges LLM classifications with original metadata (url, stars, language)
- Sorts both tables by most labels matched → then by confidence (high > medium > low)
- Writes `outputs/usage_classification.csv` and `outputs/domain_classification.csv`
- Generates full-population charts and medium+confidence-filtered charts

### Output columns — `usage_classification.csv`

`repo`, `url`, `stars`, `language`, `actual_usage`, `framework_library`,
`research_artifact`, `other_usage`, `other_usage_subtype`, `other_usage_description`,
`usage_confidence`, `usage_reasoning`

### Output columns — `domain_classification.csv`

`repo`, `url`, `stars`, `language`, `dom_web_api`, `dom_database`,
`dom_security_crypto`, `dom_finance`, `dom_machine_learning`, `dom_compiler_pl`,
`dom_scientific_computing`, `dom_distributed_systems`, `dom_operating_systems`,
`dom_embedded_iot`, `dom_bioinformatics`, `dom_autonomous_robotics`, `dom_no_match`,
`domain_confidence`, `domain_reasoning`

---

## Quality and Validation Notes

- **Confidence calibration:** `high` = clear textual evidence from README/description.
  `medium` = inferred from context, file names, or topics. `low` = only repo name
  and file paths available.
- **Multi-label overlap:** 30–40% of repos may carry multiple usage labels (e.g. a
  research framework). This is meaningful signal, not noise.
- **`dom_no_match` is not a failure:** Many repos are general-purpose or AI tools with
  no specific application domain. That is itself a finding.
- **Low-confidence repos:** ~5–10% of repos have no description and no README. These
  are typically labelled `other_usage` with `low` confidence. They can be reviewed
  manually or queued for GitHub API re-fetch.
- **Revalidation:** For high-stakes claims (e.g. "X% are research artefacts"),
  manually verify a stratified random sample of ~30 repos (10 per confidence tier).
- **`other:agent` note:** Presence of `CLAUDE.md` / `AGENTS.md` alone is not
  sufficient. Only assign `other:agent` if the technique vocabulary appears
  **within** an agent instruction or skill file — not just anywhere in the repo.

---

## Adapting to a New Technique

To run the same pipeline for a different technique (e.g. property-based testing
or fuzz testing):

1. Set `USAGE_CSV` in `01_consolidate.py` to the new technique's
   `usage_repos_for_review.csv`.
2. Adjust `BATCH_SIZE` and `README_MAX_CHARS` as needed (fuzz testing has a
   smaller usage set; PBT's ~72k CODE repos should be sampled first).
3. Replace `[TECHNIQUE]` and the technique description in the classification
   prompt above.
4. Optionally add technique-specific domain signals (e.g. "fuzzer", "QuickCheck",
   "Hypothesis") to guide the LLM on domain keywords.
5. The output schema, scripts, and folder structure remain unchanged.
