"""
Analyse the manual validation of the LLM usage classification.

Inputs (this folder): rater_KQ.csv, rater_MRG.csv (filled), consensus.csv (filled after
reconciliation, same columns as a rater sheet), sample_key.csv (LLM labels).
Prints, per label:
  * inter-rater agreement BEFORE reconciliation: % agreement and Cohen's kappa
  * LLM precision against the consensus: correct / 10 among repos the LLM gave that label
    (drawn_for == label), with a 95% Clopper-Pearson interval
  * LLM agreement with the consensus on all 40 repos (kappa), as a secondary figure
Run:  python -I analyse_validation.py
"""
import csv
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELS = ["actual_usage", "framework_library", "research_artifact", "other_usage"]


def load(name):
    return {int(r["id"]): r for r in csv.DictReader(open(HERE / name, encoding="utf-8"))}


def yes(v):
    v = str(v).strip().lower()
    if v not in {"0", "1", "y", "n", "yes", "no", "true", "false"}:
        raise ValueError(f"unfilled or invalid cell: {v!r}")
    return v in {"1", "y", "yes", "true"}


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


def _cdf(k, n, p):
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def _root(f, target, increasing):
    """p in [0, 1] with f(p) = target, by bisection (f monotone in p)."""
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if (f(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k, n, a=0.05):
    """Exact (Clopper-Pearson) 95% interval for k successes in n trials."""
    # lower: P(X >= k | p) = a/2 ; upper: P(X <= k | p) = a/2
    lo = _root(lambda p: 1 - _cdf(k - 1, n, p), a / 2, increasing=True) if k > 0 else 0.0
    hi = _root(lambda p: _cdf(k, n, p), a / 2, increasing=False) if k < n else 1.0
    return lo, hi


kq, mrg, key = load("rater_KQ.csv"), load("rater_MRG.csv"), load("sample_key.csv")
cons = load("consensus.csv") if (HERE / "consensus.csv").exists() else None
ids = sorted(key)

# Inter-rater section: skip if KQ sheet is unfilled (single-rater mode)
_kq_filled = all(str(kq[i]["actual_usage"]).strip() in {"0","1"} for i in ids)
if _kq_filled:
    print("Inter-rater agreement (before reconciliation), n =", len(ids))
    for lab in LABELS:
        po, k = kappa([yes(kq[i][lab]) for i in ids], [yes(mrg[i][lab]) for i in ids])
        print(f"  {lab:18s} agreement {po:6.1%}  kappa {k:5.2f}")
    po, k = kappa([yes(kq[i]["not_mt_false_positive"]) for i in ids], [yes(mrg[i]["not_mt_false_positive"]) for i in ids])
    print(f"  {'not_mt (false pos.)':18s} agreement {po:6.1%}  kappa {k:5.2f}")
else:
    print("Inter-rater agreement: skipped (rater_KQ.csv not yet filled — single-rater mode)")

if cons is None:
    raise SystemExit("\nconsensus.csv not found: reconcile the two sheets first.")

print("\nLLM precision per label against the consensus (10 repos drawn per label)")
for lab in LABELS:
    drawn = [i for i in ids if key[i]["drawn_for"] == lab]
    k = sum(yes(cons[i][lab]) for i in drawn)
    lo, hi = clopper_pearson(k, len(drawn))
    print(f"  {lab:18s} {k}/{len(drawn)} correct  ({k/len(drawn):.0%}, 95% CI {lo:.0%}-{hi:.0%})")

print("\nLLM vs consensus on all sampled repos (secondary)")
for lab in LABELS:
    po, k = kappa([yes(key[i][lab]) for i in ids], [yes(cons[i][lab]) for i in ids])
    print(f"  {lab:18s} agreement {po:6.1%}  kappa {k:5.2f}")
fp = [cons[i]["repo"] for i in ids if yes(cons[i]["not_mt_false_positive"])]
print(f"\nNot MT at all (keyword false positives): {len(fp)} of {len(ids)}", fp)
