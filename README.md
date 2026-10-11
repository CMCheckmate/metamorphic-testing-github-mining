# GitHub Mining Pipeline

Mines GitHub to study how three software testing techniques are adopted in open-source projects: **metamorphic testing (MT)**, **property-based testing (PBT)** and **fuzz testing (fuzz)**. For each technique it produces a sections report covering:

| Research question | Sections |
|---|---|
| **RQ1:** adoption | S1–S4, A1 |
| **RQ2:** usage and classification | A2–A7 |
| **RQ3:** timeline | T8–T9 |

There are two ways to run it:

| | **Specialised pipeline** (used for our report) | **Full analysis** (optional) |
|---|---|---|
| What | Only the data the sections report needs: shallow clones scanned with `git grep`, plus targeted API look-ups; random samples for PBT/fuzz | Clones every repository with history and scans every file. Produces much more data that the report does not use (commit spans, per-file details, repository classification, `report.md`). |
| Run time | Hours | Days (MT alone took ~5 days for 1.8k repositories) |
| Entry points | the four scripts in the project root | `python -m full_analysis` |

---

## Setup

1. **Python 3.11** and **Git 2.30+** on the PATH. All runs used Windows 11.
2. Install the dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set `GITHUB_TOKEN=...`: a classic personal access token with no scopes. Only steps that call the GitHub API need it.

The API limits are about 30 search requests a minute and 5,000 REST requests an hour. Every step paces itself and can be resumed: rerun the same command after an interruption.

---

## Reproducing the results

Run the steps in order for each technique. `-t` takes `mt`, `pbt` or `fuzz`. GitHub changes over time, so collecting the data again gives somewhat different numbers. To reproduce the reported figures exactly, run only step 5 on the archived data (see [Data to archive](#data-to-archive)).

### Metamorphic testing

| # | Command | What it does | Time |
|---|---|---|---|
| 1 | `python search.py -t mt` | GitHub search on 6 surfaces → `results/metamorphic_testing/search/` | hours (API) |
| 2 | `python non_code_specialised_analysis.py -t mt --metadata` | Metadata (language, creation date, size) of every repository found | ~3 h (API) |
| 3 | `python code_specialised_analysis.py -t mt`, then `python code_specialised_analysis.py -t mt --merge "results/metamorphic_testing/specialised/*.jsonl"` | Clone and scan the current snapshot of every CODE-surface repository | ~2–5 s per repository |
| 4 | `python non_code_specialised_analysis.py -t mt --readmes --lang-baseline --commit-coverage` | READMEs (A6/A7), GitHub-wide language counts (A5), commit-search coverage check (T8/T9) | ~1 h (API) |
| 5 | `python specialised_report.py -t mt` | Aggregate and render the report | local, ~2 min |

### Property-based testing and fuzz testing

Replace `pbt` with `fuzz` for fuzz testing.

| # | Command | What it does | Time |
|---|---|---|---|
| 1 | `python search.py -t pbt` | GitHub search | hours (API) |
| 2 | `python non_code_specialised_analysis.py -t pbt --prepare` | Keeps explicit-phrase results only, checks titles/bodies, draws the ±3% / 95% random samples | local, 1–3 min |
| 3 | `python code_specialised_analysis.py -t pbt`, then `--merge "results/property_based_testing/specialised/*.jsonl"` | Clone and scan the CODE sample (~1,150 repositories) | ~1–2 h |
| 4 | `python non_code_specialised_analysis.py -t pbt --metadata --readmes --lang-baseline` | Sample metadata and READMEs (A5–A7), language counts | ~40 min (API) |
| 4b | PBT: `python non_code_specialised_analysis.py -t pbt --commit-sampling adoption --exhaustive` | Recounts the commit-search ranges that hit GitHub's 1,000-result cap: exact per-year first-commit counts and agent shares | ~30 min (API) |
| 4b | fuzz: `--commit-sampling agent`, then `--commit-sampling adoption --years 2024 2025 2026 --target 0.2` | Same, estimated by random time-window sampling with 95% confidence intervals. `--commit-sampling estimate` prints time projections per option. | ~15 min + ~2 h (API) |
| 5 | `python specialised_report.py -t pbt` | Aggregate and render the report | local, seconds |

### Splitting the scan across several PCs

Step 3 can be divided between machines with no coordination; every PC computes the same split. Each PC runs its own shard with the same `--weights`:

```bash
python code_specialised_analysis.py -t mt --weights 50,40,10 --shard 1
```

- **Before starting (optional):** `--benchmark 30` scans 30 repositories and projects the total time.
- **Packaging:** `--make-package` builds a zip with the code and input data for the other PCs.
- **Afterwards:** copy every `shard*.jsonl` into one `specialised/` folder and run `--merge`.
- **Retries:** timed-out repositories are retried automatically when the same command is run again.

### Outputs

`results/<technique>/sections_report/`:

| File | Contents |
|---|---|
| `sections_report.md` + `plots/` | The tables and plots used in the report |
| `sections_issues.md` | Caveats, decisions and data sources |
| `sections_samples.md` | Repository and commit lists for manual checking |
| `sections_excluded.md` | Every search result treated as not found, with the reason |
| `usage_repos_for_review.csv` | MT only |

### Method decisions

- **Verified results only.** A result counts only if it is verified:
  - **non-CODE item:** a technique keyword appears in its title or body;
  - **CODE repository:** its current snapshot has a technique hit.

  Everything else is treated as not found and listed in `sections_excluded.md`.
- **Excluded search keywords** (`inputs/comparison_keywords.json`):
  - **MT:** `"@metamorphic"`, because GitHub ignores the `@` and searches the bare word;
  - **PBT/fuzz:** every tool, library and API keyword, keeping explicit technique phrases only.
- **Technique regexes:** `inputs/<mt|pbt|fuzz>_analysis_keywords.json`.
- **Samples (PBT/fuzz):** seeded, sized with Cochran's formula with finite-population correction (±3% at 95% confidence), plus 8% extra to cover deleted repositories.
- **Seeds:** 20261010 (scan order, report samples) and 20261011 (PBT/fuzz samples, commit sampling).
- **Search window:** 2010-01-01 to 2026-09-01 (`core_helpers/config.py`).
- **T8:** "first commit mentioning the technique" means a commit message, not necessarily code.
- **Commit-search cap (PBT/fuzz):** GitHub returns at most 1,000 results per query, and the original search split queries only down to ~95-day ranges. Step 4b re-collects the capped ranges with finer time windows.

### Data to archive

`results/` is git-ignored. For exact reproduction, archive:

| Path | Size | Notes |
|---|---|---|
| `results/*/search/` + `search.log` | MT 160 MB, PBT 1.9 GB, fuzz 5.0 GB | Cannot be re-collected identically. The log is needed for the completeness figures. |
| `results/*/analysis/` | 8–70 MB each | Metadata, samples, merged scans, `overall.json` |
| `results/*/specialised/` | 1–30 MB each | Raw scan records of the snapshots at the time |
| `results/*/commit_sample/` | ~12 MB | Downloaded commit windows |
| `results/*/filtered/` | 40–150 MB | Rebuilt by `--prepare`; optional |
| `results/*/sections_report/` | ~3–5 MB each | The reported results |

---

## Project layout

```
search.py                          step 1: GitHub search
code_specialised_analysis.py       clone + scan (CODE surface); sharding, --merge, --make-package
non_code_specialised_analysis.py   everything else collected for the report (flags, see --help)
specialised_report.py              aggregate + render the sections report

core_helpers/      settings and data collection
  config.py          paths, search window, rate limits, file-type lists
  utils.py           GitHub requests, logging, JSON, keyword loading
  github_search.py   search implementation
  github_fetch.py    API look-ups (metadata, READMEs, language baseline, commit coverage)
  technique_data.py  PBT/fuzz filtering and sampling (--prepare) and sample look-ups
  commit_sampling.py commit-search cap correction (--commit-sampling)
  keyword_matcher.py technique regex matching (code and text)
report_helpers/    computes and renders the reports
  sections_aggregate.py, data_repair.py           every number in the report
  sections_report.py                              MT renderer
  other_techniques_aggregate.py, other_techniques_report.py   PBT/fuzz
full_analysis/     the original clone-everything pipeline (python -m full_analysis);
                   parts are imported by the specialised pipeline (file-type rules, helpers)
inputs/            search keywords, technique regexes, domain taxonomy, excluded keywords
                   (archive/: earlier PBT/fuzz library-based regexes)
example_results/   dummy data for the full analysis report (python -m full_analysis.generate_example_data)
results/           all data and reports (git-ignored)
```

### Input files

- **`inputs/<technique>_search_keywords.txt`:** one GitHub query per line. Use double quotes for exact phrases and list inflected forms explicitly. Lines starting with `#` are comments.
- **`inputs/<technique>_analysis_keywords.json`:** technique regexes (`category: specific_technique`). Optional fields:
  - `flags`;
  - `split_first` / `split_second`: catch a phrase wrapped over two lines;
  - `subset_of`: a comment or string variant counted under its parent keyword, excluded from totals.
- **`inputs/shared_analysis_keywords.json`:** test-file detection rules (`apply_to: filename | content`) shared by all techniques.
- **`inputs/domain_keywords.json`:** application-domain taxonomy (A6).
- **`inputs/comparison_keywords.json`:** search keywords whose results are excluded, and PBT search keywords that never ran.

---

## Docker (optional)

The image contains the whole project. Run any script with the same arguments as without Docker. Data is written to `./results/` on the host, `inputs/` is mounted read-only, and the token comes from `.env`.

```bash
docker compose build
docker compose run --rm pipeline search.py -t mt
docker compose run --rm pipeline code_specialised_analysis.py -t mt
docker compose run --rm pipeline non_code_specialised_analysis.py -t mt --metadata --readmes
docker compose run --rm --network none pipeline specialised_report.py -t mt
docker compose run --rm pipeline -m full_analysis -t mt --phase analysis
```

- **User:** the container runs as a non-root user with all capabilities dropped.
- **Resources:** limited to 8 GB RAM and 4 CPUs; adjust `deploy.resources.limits` in `docker-compose.yml`.
- **Rebuild:** run `docker compose build` again after changing the code.

---

## Full analysis (optional)

```bash
python -m full_analysis -t mt --phase search      # same search as search.py
python -m full_analysis -t mt --phase analysis    # clone everything + non-code analysis (days)
python -m full_analysis -t mt --phase report      # results/<technique>/report/report.md
python -m full_analysis.generate_example_data -t mt   # dummy data, no token needed → example_results/
```

- **Analysis options:** `--code-only`, `--noncode-only`, `--restart`, `--workers N`, `--aggregate-only`, `--no-size-stats`.
- **Not needed for the sections report:** the specialised pipeline re-scans every CODE repository itself.
