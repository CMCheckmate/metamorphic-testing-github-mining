"""
Significance tests for the final report (run once; results are copied into main.tex).

All tests are Pearson chi-square tests at the 5% level, Bonferroni-corrected within each group.
1. Languages: is MT repositories' language mix the same as GitHub's? One goodness-of-fit test
   over the 30 languages with a GitHub-wide count (same denominator on both sides), then one
   test per language (that language vs all others, 1 degree of freedom).
2. README vocabulary: is a domain word used by the same share of repositories for MT and for
   PBT (and for MT and fuzzing)? One 2x2 test (technique x word present/absent) per word and pair.
3. Agent share: is the agent-marked share of technique commits the same for MT and PBT?
   One 2x2 test (technique x agent-marked or not) per year.

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


def chi2_2x2(a, b, c, d):
    """Pearson chi-square (1 df) for the table [[a, b], [c, d]]; returns (chi2, p)."""
    n = a + b + c + d
    den = (a + b) * (c + d) * (a + c) * (b + d)
    x = n * (a * d - b * c) ** 2 / den if den else 0.0
    return x, chi2_sf(x, 1)


# ---------------------------------------------------------------- 1. languages
mt = sec("mt")
gh = {l: v for l, v in json.load(open(ROOT / "metamorphic_testing" / "analysis" / "github_language_baseline.json"))["languages"].items() if v}
mt_counts = {r["language"]: r["repos"] for r in mt["a5"]["rows"]}
langs = list(gh)
obs = {l: mt_counts.get(l, 0) for l in langs}
n = sum(obs.values())
G = sum(gh.values())
chi2 = sum((obs[l] - n * gh[l] / G) ** 2 / (n * gh[l] / G) for l in langs)
print("=== 1. Languages (30 languages with a GitHub-wide count)")
print(f"MT repositories in these languages: {n:,}; GitHub repositories: {G:,}")
print(f"Goodness of fit: chi2 = {chi2:,.0f}, df = {len(langs) - 1}, p {fmt_p(chi2_sf(chi2, len(langs) - 1))}")
alpha = 0.05 / len(langs)
print(f"Per language (1 df), Bonferroni alpha = 0.05/{len(langs)} = {alpha:.5f}")
for l in sorted(langs, key=lambda x: -obs[x]):
    e = n * gh[l] / G
    x = (obs[l] - e) ** 2 / e + ((n - obs[l]) - (n - e)) ** 2 / (n - e)
    pv = chi2_sf(x, 1)
    print(f"  {l:18s} obs {obs[l]:5d}  exp {e:8.1f}  lift {obs[l]/e:6.2f}  chi2 {x:9.1f}  p {fmt_p(pv):9s} {'SIG' if pv < alpha else 'ns'}")

# ---------------------------------------------------------------- 2. README vocabulary
print("\n=== 2. README / description domain vocabulary")
A7 = {t: sec(t)["a7"] for t in SLUG}
N = {t: A7[t]["repos"] for t in SLUG}
F = {t: dict(A7[t]["whitelist_freq"]) for t in SLUG}
top = set()
for t in SLUG:
    top |= set(sorted(F[t], key=lambda w: -F[t][w])[:15])
words = sorted(top)
ntests = 2 * len(words)
alpha = 0.05 / ntests
print(f"Repositories: MT {N['mt']}, PBT {N['pbt']}, fuzz {N['fuzz']}")
print(f"{len(words)} words in any top-15; {ntests} 2x2 tests (MT vs PBT, MT vs fuzz); Bonferroni alpha = {alpha:.5f}")
for w in sorted(words, key=lambda x: -F['mt'].get(x, 0)):
    km = F["mt"].get(w, 0)
    out = f"  {w:15s} MT {km / N['mt']:6.1%}"
    for t in ("pbt", "fuzz"):
        k = F[t].get(w, 0)
        x, pv = chi2_2x2(km, N["mt"] - km, k, N[t] - k)
        out += f" | {t} {k / N[t]:6.1%} chi2 {x:6.1f} p {fmt_p(pv):9s} {'SIG' if pv < alpha else 'ns '}"
    print(out)

# ---------------------------------------------------------------- 3. agent share 2025 / 2026
print("\n=== 3. Agent-marked share of technique commits (MT vs PBT), Bonferroni alpha = 0.025")
t9 = mt["t9"]
g = lambda d, y: d.get(str(y), d.get(y, 0))
pbt_est = json.load(open(ROOT / SLUG["pbt"] / "commit_sample" / "estimates.json", encoding="utf-8"))["agent"]
for y in (2025, 2026):
    k1, n1 = g(t9["agent_marked"], y), g(t9["relevant"], y)
    e = pbt_est[str(y)]
    n2 = round(e["relevant_est"]); k2 = round(e["share"] * n2)
    x, pv = chi2_2x2(k1, n1 - k1, k2, n2 - k2)
    print(f"  {y}: MT {k1}/{n1} = {k1/n1:.1%}  vs PBT {k2}/{n2} = {k2/n2:.1%}   chi2 = {x:.1f}, p {fmt_p(pv)}  (PBT exact: {e.get('exact')})")
