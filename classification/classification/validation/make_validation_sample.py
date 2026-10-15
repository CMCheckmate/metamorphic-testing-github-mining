"""
Draw the manual-validation sample for the LLM usage classification.

Design: for each of the 4 usage labels, a simple random sample of 10 repositories that the
LLM assigned that label (seed 20261015). Sampling is without replacement across labels: a
repository drawn for one label is not drawn again, but every sampled repository is rated
on all four labels. Raters see no LLM output (blind); the LLM labels are in a separate key.

Outputs (in this folder):
  sample_key.csv          LLM labels for the sampled repos (do NOT open before rating)
  rater_KQ.csv            blank rating sheet for Ky Khon Quach
  rater_MRG.csv           blank rating sheet for Ming Ray Goy
Run once:  python -I make_validation_sample.py
"""
import csv
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SEED = 20261015
PER_LABEL = 10
LABELS = ["actual_usage", "framework_library", "research_artifact", "other_usage"]

llm = {r["repo"]: r for r in json.load(open(ROOT / "results" / "all_classifications.json", encoding="utf-8"))}
review_csv = ROOT.parents[1] / "results" / "metamorphic_testing" / "sections_report" / "usage_repos_for_review.csv"
info = {r["repo"]: r for r in csv.DictReader(open(review_csv, encoding="utf-8"))}

rnd = random.Random(SEED)
taken, rows = set(), []
for lab in LABELS:
    pool = sorted(r for r, c in llm.items() if c.get(lab) and r not in taken)
    pick = rnd.sample(pool, PER_LABEL)
    taken.update(pick)
    rows += [(lab, r) for r in pick]
rnd.shuffle(rows)                                   # raters see no grouping by label

key_cols = ["id", "repo", "drawn_for"] + LABELS + ["usage_confidence", "usage_reasoning"]
with open(HERE / "sample_key.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(key_cols)
    for i, (lab, r) in enumerate(rows, 1):
        c = llm[r]
        w.writerow([i, r, lab] + [int(bool(c.get(l))) for l in LABELS] + [c.get("usage_confidence"), c.get("usage_reasoning")])

sheet_cols = ["id", "repo", "url", "technique_test_files", "technique_nontest_files", "sample_technique_files",
              "not_mt_false_positive", "actual_usage", "framework_library", "research_artifact", "other_usage",
              "other_subtype", "evidence", "confidence", "minutes", "date_viewed"]
for who in ("KQ", "MRG"):
    with open(HERE / f"rater_{who}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(sheet_cols)
        for i, (_, r) in enumerate(rows, 1):
            m = info.get(r, {})
            w.writerow([i, r, m.get("url", f"https://github.com/{r}"), m.get("technique_test_files", ""),
                        m.get("technique_nontest_files", ""), m.get("sample_technique_files", "")] + [""] * 10)
print(f"{len(rows)} repositories sampled (seed {SEED}); wrote sample_key.csv, rater_KQ.csv, rater_MRG.csv")
