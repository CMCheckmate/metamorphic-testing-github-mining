"""
Significance tests for the final report (run once; results are copied into main.tex).

1. Languages: are MT repositories' primary languages distributed like GitHub's?
   Chi-square goodness-of-fit and per-language exact binomial tests, restricted to the
   30 languages for which a GitHub-wide count was fetched (both sides use the same
   denominator, so repositories without a language do not distort the comparison).
2. README vocabulary: does the share of repositories using a domain word differ between
   MT (all 1,948 verified non-code repositories, a census) and the PBT / fuzzing random
   samples? Exact binomial test of each comparator sample against MT's population share.
3. Agent share 2025: MT (39 of 243 relevant commits) vs PBT (exact recount) - two-proportion
   z-test, treating the commits of each year as realisations of an underlying process.

Multiple tests are Bonferroni-corrected within each family. Run:  python -I significance_tests.py
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "results"
SLUG = {"mt": "metamorphic_testing", "pbt": "property_based_testing", "fuzz": "fuzz_testing"}


def sec(t):
    return json.load(open(ROOT / SLUG[t] / "analysis" / "overall.json", encoding="utf-8"))["sections"]


def binom_two_sided(k, n, p):
    """Exact two-sided binomial p-value (sum of outcomes no more likely than k)."""
    def lpmf(i):
        return math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * math.log(p) + (n - i) * math.log1p(-p)
    lk = lpmf(k)
    tot = 0.0
    for i in range(n + 1):
        li = lpmf(i)
        if li <= lk + 1e-9:
            tot += math.exp(li)
    return min(1.0, tot)


def chi2_sf(x, df):
    """Survival function of the chi-square distribution (regularised upper gamma)."""
    a, z = df / 2.0, x / 2.0
    if z == 0:
        return 1.0
    if z < a + 1:                                    # series for the lower gamma
        term = s = 1.0 / a
        k = a
        while True:
            k += 1
            term *= z / k
            s += term
            if term < s * 1e-15:
                break
        return max(0.0, 1.0 - math.exp(-z + a * math.log(z) - math.lgamma(a)) * s)
    b, c, d = z + 1 - a, 1e300, 1.0 / (z + 1 - a)    # continued fraction for the upper gamma
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1) < 1e-15:
            break
    return math.exp(-z + a * math.log(z) - math.lgamma(a)) * h


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def fmt_p(p):
    return "< 0.001" if p < 0.001 else f"= {p:.3f}"


# ---------------------------------------------------------------- 1. languages
mt = sec("mt")
base = mt["a5"]["baseline"] if isinstance(mt["a5"].get("baseline"), dict) else None
gh = json.load(open(ROOT / "metamorphic_testing" / "analysis" / "github_language_baseline.json"))["languages"]
rows = mt["a5"]["rows"]
mt_counts = {r["language"]: r["repos"] for r in rows} if isinstance(rows, list) else {k: v for k, v in rows.items()}
langs = [l for l in gh if l in mt_counts or True]
obs = {l: mt_counts.get(l, 0) for l in langs}
n = sum(obs.values())
G = sum(gh[l] for l in langs)
chi2 = sum((obs[l] - n * gh[l] / G) ** 2 / (n * gh[l] / G) for l in langs)
df = len(langs) - 1
print("=== 1. Languages (30 languages with a GitHub-wide count)")
print(f"MT repositories in these languages: {n:,}; GitHub repositories: {G:,}")
print(f"Chi-square goodness of fit: chi2 = {chi2:,.0f}, df = {df}, p {fmt_p(chi2_sf(chi2, df))}")
alpha = 0.05 / len(langs)
print(f"Per-language exact binomial tests, Bonferroni alpha = 0.05/{len(langs)} = {alpha:.5f}")
for l in sorted(langs, key=lambda x: -obs[x]):
    p0 = gh[l] / G
    pv = binom_two_sided(obs[l], n, p0)
    exp = n * p0
    print(f"  {l:18s} obs {obs[l]:5d}  exp {exp:8.1f}  ratio {obs[l]/exp:6.2f}  p {fmt_p(pv):9s} {'SIG' if pv < alpha else 'ns'}")

# ---------------------------------------------------------------- 2. README vocabulary
print("\n=== 2. README / description domain vocabulary")
A7 = {t: sec(t)["a7"] for t in SLUG}
N = {t: A7[t]["repos"] for t in SLUG}
F = {t: dict(A7[t]["whitelist_freq"]) if isinstance(A7[t]["whitelist_freq"], dict)
     else {w: c for w, c in A7[t]["whitelist_freq"]} for t in SLUG}
top = set()
for t in SLUG:
    top |= set(sorted(F[t], key=lambda w: -F[t][w])[:15])
words = sorted(top)
ntests = 2 * len(words)
alpha = 0.05 / ntests
print(f"Repositories: MT {N['mt']} (census), PBT {N['pbt']} (sample), fuzz {N['fuzz']} (sample)")
print(f"{len(words)} words in any top-15; {ntests} tests; Bonferroni alpha = {alpha:.5f}")
for w in sorted(words, key=lambda x: -F['mt'].get(x, 0)):
    pm = F["mt"].get(w, 0) / N["mt"]
    out = f"  {w:15s} MT {pm:6.1%}"
    for t in ("pbt", "fuzz"):
        k = F[t].get(w, 0)
        pv = binom_two_sided(k, N[t], pm) if 0 < pm < 1 else float("nan")
        out += f" | {t} {k/N[t]:6.1%} p {fmt_p(pv):9s} {'SIG' if pv < alpha else 'ns '}"
    print(out)

# ---------------------------------------------------------------- 3. agent share 2025 / 2026
print("\n=== 3. Agent-marked share of technique commits")
t9 = mt["t9"]
g = lambda d, y: d.get(str(y), d.get(y, 0))
pbt_est = json.load(open(ROOT / SLUG["pbt"] / "commit_sample" / "estimates.json", encoding="utf-8"))["agent"]
for y in (2025, 2026):
    k1, n1 = g(t9["agent_marked"], y), g(t9["relevant"], y)
    e = pbt_est[str(y)]
    n2 = round(e["relevant_est"]); k2 = round(e["share"] * n2)
    p1, p2 = k1 / n1, k2 / n2
    pp = (k1 + k2) / (n1 + n2)
    z = (p1 - p2) / math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    pv = 2 * norm_sf(abs(z))
    print(f"  {y}: MT {k1}/{n1} = {p1:.1%}  vs PBT {k2}/{n2} = {p2:.1%}   z = {z:.2f}, p {fmt_p(pv)}  (PBT exact: {e.get('exact')})")
