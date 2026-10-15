# Manual validation of the LLM usage classification (MT)

**Who:** Ky Khon Quach (KQ) and Ming Ray Goy (MRG), independently, then together.
**What:** 40 MT usage repositories, 10 drawn at random from each label the LLM assigned
(`actual_usage`, `framework_library`, `research_artifact`, `other_usage`). Seed 20261015,
drawn by `make_validation_sample.py`. Sample by confidence: 12 high, 13 medium, 15 low.
**Time:** about 3–5 min per repository, so roughly 2.5–3.5 h each, plus about 1 h together.

| File | Who opens it | When |
|---|---|---|
| `rater_KQ.csv` | KQ only | Step 2 |
| `rater_MRG.csv` | MRG only | Step 2 |
| `consensus.csv` | both | Step 3 (create it) |
| `sample_key.csv` (the LLM's labels) | both | **only after** Step 3 is finished |

Do not open `sample_key.csv`, `outputs/usage_classification.csv` or
`results/all_classifications.json` before Step 3. Seeing the LLM's answer first would bias
the ratings and invalidate the comparison.

---

## Step 0: Before you start (15 min, together)

1. Both read the label definitions and decision rules below. Do not change them after
   Step 1. If a rule turns out to be unclear, write the case in `evidence` and resolve it
   in Step 3. Do not edit the rules mid-way.
2. **Calibration (not part of the sample).** Pick 3 usage repositories that are *not* in
   the sample (any rows from `usage_repos_for_review.csv`). Label them separately, then
   compare and discuss. This aligns how you read the rules. Do not record these 3 anywhere.

## Step 1: Label definitions (multi-label: mark every label that applies)

A repository is judged on what it **is and does now** (current default branch), from the
README, description, the technique files and the test folder.

| Column | 1 (yes) when… | Key evidence to look for |
|---|---|---|
| `not_mt_false_positive` | "metamorphic" here does not refer to metamorphic testing at all (e.g. an app named *Metamorphic*, geology, malware, "metamorphic constants"). **If 1, set all four labels to 0** and skip to the next repository. | Read the matched line in the technique file |
| `actual_usage` | The repository contains **executable** metamorphic tests (source → follow-up input → relation check) that exercise **this repository's own software**. | A test file that calls the repo's own code twice (or more) and asserts a relation between outputs |
| `framework_library` | The repository **is** a reusable MT tool, library or framework meant for others to use: an API for writing MRs, an MR generator, an MT test runner. | README presents an API or CLI for MT; MT code in non-test source; package manifest (setup.py, package.json, Cargo.toml, pom.xml) |
| `research_artifact` | Academic research code: a replication package, paper prototype, experiment or benchmark harness. | DOI or arXiv link, paper or venue name, "replication package", "RQ1/RQ2" folders, university authors |
| `other_usage` | MT appears but none of the above holds. Also fill `other_subtype` with one of: `agent` (MT only in an AI-agent instruction or skill file such as CLAUDE.md, AGENTS.md, .cursor/rules or skills/), `tutorial` (course, homework, self-learning or toy example with no real software under test), `incidental` (MT only mentioned in docs or checklists of a general tool), `indexed` (paper lists, translations, link collections). | Where exactly the MT vocabulary sits |

**Decision rules (apply in this order):**
1. Open the technique files first (`sample_technique_files` column), not just the README.
   The LLM never saw code, so this is where you add the most value.
2. A test that only *mentions* MT in a comment or name but checks a single output against a
   fixed expected value is **not** `actual_usage` (mark `other_usage`/`incidental` unless
   another label applies). Record this in `evidence`.
3. A research tool that is also released as a usable package gets **both**
   `research_artifact` and `framework_library`. A research prototype that only runs the
   paper's experiments gets `research_artifact` only.
4. A framework's own unit tests of its MT API do **not** make it `actual_usage`. `actual_usage`
   requires MT applied to software whose purpose is not MT itself.
5. A tutorial that tests a toy function is `other_usage`/`tutorial`, not `actual_usage`.
6. If the repository is gone or private, set `evidence` to `unavailable` and leave the labels
   empty. It is replaced in Step 3 (see below).
7. Time-box: if after about 5 minutes you still cannot decide, choose the best-supported
   labels, set `confidence` to `low`, and explain why in `evidence`.

## Step 2: Rate independently (each person alone)

For every row of **your own** sheet (`rater_KQ.csv` or `rater_MRG.csv`):

1. Open `url`. Read the description and README (top section and any "Testing" section).
2. Open each path in `sample_technique_files` and read the lines around the MT vocabulary.
   Then glance at the test folder.
3. Fill the columns:
   - `not_mt_false_positive`, `actual_usage`, `framework_library`, `research_artifact`,
     `other_usage`: **1 or 0 in every cell** (no blanks; the analysis script rejects blanks)
   - `other_subtype`: `agent` / `tutorial` / `incidental` / `indexed`, only if `other_usage` = 1
   - `evidence`: one line with the file path or README phrase that decided it, e.g.
     `tests/test_mr.py: asserts sort(x)==sort(shuffle(x)) on repo's own sort()`
   - `confidence`: `high` / `medium` / `low` (your own confidence)
   - `minutes`: time spent
   - `date_viewed`: YYYY-MM-DD
4. Do not discuss repositories with each other until both sheets are complete.
5. When both are done, freeze them: do not edit `rater_KQ.csv` or `rater_MRG.csv` again.
   They are the data for inter-rater agreement.

## Step 3: Reconcile (together, about 1 h)

1. Copy `rater_KQ.csv` to `consensus.csv`.
2. Go through every row. Where the two sheets differ on any label, discuss using both
   `evidence` notes and the repository, agree on the final value, and write it into
   `consensus.csv`. Append `| resolved: <reason>` to `evidence` for every changed cell.
3. If you cannot agree, the stricter reading wins: e.g. `actual_usage` = 0 when it is
   unclear that the test exercises the repository's own code. Note it in `evidence`.
4. If a repository was unavailable, draw a replacement: the next repository in a seeded
   shuffle of the same label's pool. Ask Claude to add it, or add it by hand and note it.
   Both of you then rate it independently before reconciling.
5. Only now open `sample_key.csv`.

## Step 4: Compute the results

```bash
python -I analyse_validation.py
```

It prints:
- **Inter-rater agreement** (from the frozen sheets, before reconciliation): % agreement
  and Cohen's κ per label. κ ≥ 0.61 is conventionally "substantial" agreement.
- **LLM precision per label**: of the 10 repositories the LLM gave label X, how many the
  consensus also labels X, with an exact 95% (Clopper–Pearson) interval. For reference,
  10/10 gives [69%, 100%], 9/10 gives [56%, 100%] and 8/10 gives [44%, 98%].
- LLM–consensus κ on all 40 repositories (secondary), and the list of keyword false positives.

## Step 5: What to report (and what not to)

Report:
- The design: a stratified random sample of 10 repositories per LLM label (40 in total,
  seed 20261015), rated blind and independently by two authors against written rules,
  then reconciled.
- κ per label between the two raters.
- LLM precision per label with its 95% interval.
- How many sampled repositories were not MT at all.
- In the results, present the LLM's label counts for all 1,677 repositories as
  **LLM-estimated** shares, qualified by the measured precision. If a label's precision
  is low (e.g. below about 70%), say so next to its count and do not build a claim on it.

Do **not** report:
- Recall or an overall accuracy. The sample is drawn per *predicted* label, so it supports
  precision only. It cannot tell you how many repositories the LLM missed for a label.
- A precision for the `other_usage` sub-types. Ten repositories split over four
  sub-types is too few; describe the sub-types qualitatively instead.
