"""
Phase 5 — Results Report
========================
Writes results/analysis/summary_report.md — the sole results report for the
pipeline.  Reads whatever exists in results/ without re-running earlier phases.

    python report.py
    python report.py --refresh-plots --top-repos 30
    python report.py --format pdf --dpi 300
"""

import argparse
import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from config import RESULTS_DIR

console = Console()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load(path: Path):
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_data(results_dir: Path) -> dict:
    raw      = results_dir / "raw"
    analysis = results_dir / "analysis"
    cloned   = results_dir / "cloned"
    return {
        "summary":     _load(raw      / "summary.json"),
        "repos":       _load(raw      / "repos.json"),
        "code":        _load(raw      / "code.json"),
        "issues":      _load(raw      / "issues.json"),
        "prs":         _load(raw      / "prs.json"),
        "commits":     _load(raw      / "commits.json"),
        "discussions": _load(raw      / "discussions.json"),
        "repo_scores": _load(analysis / "repo_scores.json"),
        "findings":    _load(analysis / "findings.json"),
        "manifest":    _load(cloned   / "manifest.json"),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(v: float) -> str:
    return f"{v:.1f}%"

def _img(plots_rel: str, name: str, fmt: str, caption: str) -> str:
    return f"![{caption}]({plots_rel}/{name}.{fmt})\n*{caption}*\n"

def _tier(t: str) -> str:
    return {"strong_explicit": "Strong", "weak_explicit": "Weak", "none": "None"}.get(t, t)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def sec_funnel(data: dict) -> str:
    # Unique repos found in search
    repo_set: set = set()
    for r in (data["repos"] or []):
        repo_set.add(r.get("repo", "") or r.get("full_name", ""))
    for r in (data["code"] or []):
        repo_set.add(r.get("repo_full_name", ""))
    repo_set.discard("")

    n_cloned = n_error = 0
    if data["manifest"]:
        for v in data["manifest"].get("repos", {}).values():
            if v.get("status") in ("cloned", "refreshed", "skipped_exists"):
                n_cloned += 1
            elif v.get("status") == "error":
                n_error += 1

    scores = data["repo_scores"] or []
    tiers  = Counter(r["classification"] for r in scores)
    n      = sum(tiers.values())
    n_st   = tiers["strong_explicit"]
    n_wk   = tiers["weak_explicit"]
    n_no   = tiers["none"]
    n_ex   = n_st + n_wk
    rate   = n_ex / n * 100 if n else 0

    total_hits = 0
    if data["summary"]:
        total_hits = sum(q.get("hits", 0) for q in data["summary"].get("queries", []))

    return f"""## Pipeline Funnel

| Stage | Count |
|---|---|
| Repos found in search | {len(repo_set):,} |
| Cloned | {n_cloned:,} |
| Clone errors | {n_error:,} |
| Analysed | {n:,} |
| Strong explicit (≥ 3 signals) | {n_st:,} ({_pct(n_st/n*100 if n else 0)}) |
| Weak explicit (1–2 signals) | {n_wk:,} ({_pct(n_wk/n*100 if n else 0)}) |
| **Total explicit** | **{n_ex:,} ({_pct(rate)})** |
| No signal | {n_no:,} ({_pct(n_no/n*100 if n else 0)}) |

| Surface | Raw hits |
|---|---|
| Issues | {len(data['issues'] or []):,} |
| Pull requests | {len(data['prs'] or []):,} |
| Commits | {len(data['commits'] or []):,} |
| Discussions | {len(data['discussions'] or []):,} |
| **All queries total** | **{total_hits:,}** |
"""


def sec_rq21(data: dict, plots_rel: str, fmt: str) -> str:
    scores = data["repo_scores"] or []
    if not scores:
        return ""
    n     = len(scores)
    tiers = Counter(r["classification"] for r in scores)
    n_st  = tiers["strong_explicit"]
    n_wk  = tiers["weak_explicit"]
    n_no  = tiers["none"]
    n_ex  = n_st + n_wk

    return f"""## Q1 — Prevalence

| Classification | Repos | % of analysed |
|---|---|---|
| Strong explicit (≥ 3 signals) | {n_st:,} | {_pct(n_st/n*100)} |
| Weak explicit (1–2 signals) | {n_wk:,} | {_pct(n_wk/n*100)} |
| **Total with MT signal** | **{n_ex:,}** | **{_pct(n_ex/n*100)}** |
| No signal | {n_no:,} | {_pct(n_no/n*100)} |
| Total analysed | {n:,} | — |

{_img(plots_rel, 'classification_dist', fmt, 'Classification tier distribution')}
{_img(plots_rel, 'query_hits', fmt, 'Per-query hit counts across all search surfaces')}
{_img(plots_rel, 'query_overlap', fmt, 'Repos found by N distinct independent search queries')}
"""


def sec_rq22(data: dict, plots_rel: str, fmt: str) -> str:
    scores = data["repo_scores"] or []
    if not scores:
        return ""

    by_year: dict = defaultdict(Counter)
    for r in scores:
        d = r.get("created_at", "")
        if d:
            by_year[int(d[:4])][r["classification"]] += 1

    rows = []
    for y in sorted(by_year):
        if y < 2010:
            continue
        c = by_year[y]
        total = sum(c.values())
        ex    = c["strong_explicit"] + c["weak_explicit"]
        rows.append(f"| {y} | {c['strong_explicit']:,} | {c['weak_explicit']:,} | {ex:,} | {c['none']:,} | {total:,} |")

    if not rows:
        return ""
    return f"""## Q2 — Trend over Time

| Year | Strong | Weak | Total explicit | No signal | Total repos |
|---|---|---|---|---|---|
{"".join(rows)}

{_img(plots_rel, 'yearly_trend', fmt, 'Explicit MT-adopting repos by creation year')}
"""


def sec_rq23(data: dict, plots_rel: str, fmt: str) -> str:
    scores = data["repo_scores"] or []
    if not scores:
        return ""

    total:    Counter = Counter()
    explicit: Counter = Counter()
    strong:   Counter = Counter()
    for r in scores:
        lang = r.get("language") or "Unknown"
        total[lang] += 1
        if r["classification"] in ("strong_explicit", "weak_explicit"):
            explicit[lang] += 1
        if r["classification"] == "strong_explicit":
            strong[lang] += 1

    # Top 15 by explicit count
    top15 = explicit.most_common(15)
    count_rows = "\n".join(
        f"| {lang} | {explicit[lang]:,} | {strong[lang]:,} | {total[lang]:,} | {_pct(explicit[lang]/total[lang]*100)} |"
        for lang, _ in top15
    )

    # Top 10 by adoption rate (min 5 repos)
    rate_rows = "\n".join(
        f"| {lang} | {explicit[lang]:,} | {total[lang]:,} | {_pct(explicit[lang]/total[lang]*100)} |"
        for lang in sorted(
            (l for l in total if total[l] >= 5),
            key=lambda l: explicit[l] / total[l],
            reverse=True,
        )[:10]
    )

    return f"""## Q3 — Language Distribution

**By explicit repo count (top 15):**

| Language | Explicit | Strong | Total in dataset | Adoption rate |
|---|---|---|---|---|
{count_rows}

**By adoption rate (languages with ≥ 5 repos):**

| Language | Explicit | Total | Rate |
|---|---|---|---|
{rate_rows}

{_img(plots_rel, 'language_dist', fmt, 'Top 15 languages by explicit MT repo count')}
"""


def sec_rq24(plots_rel: str, fmt: str) -> str:
    return f"""## Q4 — Domain Analysis

{_img(plots_rel, 'domain_heatmap', fmt, 'Language × classification tier heatmap (top 12 languages)')}
"""


def sec_rq25(data: dict, plots_rel: str, fmt: str) -> str:
    scores = data["repo_scores"] or []
    if not scores:
        return ""

    by_tier: dict = defaultdict(list)
    for r in scores:
        by_tier[r["classification"]].append(r.get("stars", 0))

    def _row(tier: str, label: str) -> str:
        s = sorted(by_tier.get(tier, []))
        if not s:
            return f"| {label} | — | — | — | — | — |"
        n = len(s)
        return (f"| {label} | {n:,} | {statistics.median(s):.0f} | {statistics.mean(s):.0f} "
                f"| {max(s):,} | {_pct(sum(1 for x in s if x >= 100)/n*100)} "
                f"| {_pct(sum(1 for x in s if x >= 1000)/n*100)} |")

    return f"""## Q5 — Project Maturity

| Tier | Repos | Median ★ | Mean ★ | Max ★ | ≥ 100 ★ | ≥ 1,000 ★ |
|---|---|---|---|---|---|---|
{_row("strong_explicit", "Strong explicit")}
{_row("weak_explicit",   "Weak explicit")}
{_row("none",            "No signal")}

{_img(plots_rel, 'stars_vs_score', fmt, 'Repository star count vs explicit MT hit count')}
"""


def sec_rq26(data: dict, plots_rel: str, fmt: str) -> str:
    scores = data["repo_scores"] or []
    if not scores:
        return ""

    explicit = [r for r in scores if r["classification"] in ("strong_explicit", "weak_explicit")]
    if not explicit:
        return ""

    orgs  = Counter(r["repo"].split("/")[0] for r in explicit)
    top   = orgs.most_common(20)
    total = sum(orgs.values())

    org_rows = "\n".join(
        f"| {i+1} | `{org}` | {cnt:,} | {_pct(cnt/total*100)} |"
        for i, (org, cnt) in enumerate(top)
    )
    top5_pct  = sum(v for _, v in top[:5])  / total * 100 if total else 0
    top10_pct = sum(v for _, v in top[:10]) / total * 100 if total else 0
    n_single  = sum(1 for v in orgs.values() if v == 1)

    return f"""## Q6 — Author Concentration

| | Value |
|---|---|
| Unique owners | {len(orgs):,} |
| Top 5 owners account for | {_pct(top5_pct)} |
| Top 10 owners account for | {_pct(top10_pct)} |
| Owners with a single MT repo | {n_single:,} ({_pct(n_single/len(orgs)*100 if orgs else 0)}) |

| Rank | Owner | Explicit repos | % of total |
|---|---|---|---|
{org_rows}

{_img(plots_rel, 'author_dist', fmt, 'Top 20 owners by explicit MT repo count')}
"""


def sec_rq27(data: dict, plots_rel: str, fmt: str) -> str:
    scores   = data["repo_scores"] or []
    findings = data["findings"] or []
    if not scores or not findings:
        return ""

    explicit_repos = {r["repo"] for r in scores
                      if r["classification"] in ("strong_explicit", "weak_explicit")}
    files: dict = defaultdict(set)
    for f in findings:
        repo = f.get("repo", "")
        if repo in explicit_repos:
            files[repo].add(f.get("file", ""))

    if not files:
        return ""

    counts = sorted(files[r] for r in files)  # sets, sorted by len below
    cnt    = [len(s) for s in files.values()]
    n      = len(cnt)

    # Bin distribution
    bins   = [(1,1), (2,2), (3,5), (6,10), (11,20), (21, 10**9)]
    labels = ["1", "2", "3–5", "6–10", "11–20", ">20"]
    bin_rows = "\n".join(
        f"| {lbl} | {sum(1 for c in cnt if lo <= c <= hi):,} | {_pct(sum(1 for c in cnt if lo <= c <= hi)/n*100)} |"
        for lbl, (lo, hi) in zip(labels, bins)
    )

    return f"""## Q7 — Coverage within Repository

| | Value |
|---|---|
| Explicit repos with file-level data | {n:,} |
| Median files with MT signals | {statistics.median(cnt):.0f} |
| Mean files with MT signals | {statistics.mean(cnt):.1f} |
| Max files with MT signals | {max(cnt):,} |
| Single-file adoption | {sum(1 for c in cnt if c == 1):,} ({_pct(sum(1 for c in cnt if c == 1)/n*100)}) |
| Multi-file adoption | {sum(1 for c in cnt if c > 1):,} ({_pct(sum(1 for c in cnt if c > 1)/n*100)}) |

**Files-with-signal distribution:**

| Files per repo | Repos | % |
|---|---|---|
{bin_rows}

{_img(plots_rel, 'coverage_depth', fmt, 'Files with explicit MT signals per repo, by tier')}
"""


def sec_rq28(data: dict, plots_rel: str, fmt: str, top_n: int) -> str:
    scores   = data["repo_scores"] or []
    findings = data["findings"] or []
    if not scores:
        return ""

    # Count how many matches each pattern label has across all findings
    matches_per_pattern: Counter = Counter(finding["label"] for finding in findings)

    # Count how many repos matched each pattern (from repo_scores.patterns_matched,
    # which stores human-readable labels directly)
    repos_per_pattern: Counter = Counter()
    for repo_score in scores:
        for pattern_label in repo_score.get("patterns_matched", []):
            repos_per_pattern[pattern_label] += 1

    pat_rows = "\n".join(
        f"| {pattern_label} | {repos_per_pattern[pattern_label]:,} | {matches_per_pattern[pattern_label]:,} |"
        for pattern_label, _ in repos_per_pattern.most_common()
    )

    # Top repos by match count then stars
    strong_repos = sorted(
        [repo_score for repo_score in scores if repo_score["classification"] == "strong_explicit"],
        key=lambda repo_score: (repo_score.get("score", 0), repo_score.get("stars", 0)),
        reverse=True,
    )[:top_n]
    repo_rows = "\n".join(
        f"| [{repo_score['repo']}](https://github.com/{repo_score['repo']}) "
        f"| {_tier(repo_score['classification'])} "
        f"| {repo_score.get('score', 0)} "
        f"| {repo_score.get('direct_matches', 0):,} "
        f"| {repo_score.get('files_with_matches', 0):,} "
        f"| {repo_score.get('language') or '—'} "
        f"| {repo_score.get('stars', 0):,} |"
        for repo_score in strong_repos
    )

    return f"""## Q8 — MR Structure & Pattern Analysis

**Pattern frequency ({len(findings):,} total matches across all repos):**

| Pattern matched | Repos | Total matches |
|---|---|---|
{pat_rows}

{_img(plots_rel, 'pattern_freq', fmt, 'Pattern match frequency across repos')}

**Top strong-adoption repos for qualitative inspection (top {top_n}):**

| Repository | Tier | Score | Matches | MT files | Language | Stars |
|---|---|---|---|---|---|---|
{repo_rows}
"""


def sec_all_repos(data: dict) -> str:
    scores = data["repo_scores"] or []
    if not scores:
        return ""

    sorted_repos = sorted(scores, key=lambda r: (r.get("score", 0), r.get("stars", 0)), reverse=True)
    rows = "\n".join(
        f"| [{r['repo']}](https://github.com/{r['repo']}) "
        f"| `{r['classification']}` "
        f"| {r.get('score', 0)} "
        f"| {r.get('direct_matches', 0):,} "
        f"| {r.get('files_with_matches', 0):,} "
        f"| {r.get('language') or '—'} "
        f"| {r.get('stars', 0):,} "
        f"| {(r.get('created_at') or '')[:4] or '—'} "
        f"| {'; '.join(r.get('patterns_matched', [])) or '—'} |"
        for r in sorted_repos
    )

    return f"""## All Repositories ({len(sorted_repos):,})

| Repository | Class | Score | Matches | MT files | Language | Stars | Year | Patterns matched |
|---|---|---|---|---|---|---|---|---|
{rows}
"""


def sec_query_stats(data: dict) -> str:
    summary = data["summary"]
    if not summary:
        return ""
    queries = summary.get("queries", [])
    if not queries:
        return ""

    rows = "\n".join(
        f"| {q.get('type','').upper()} | {q.get('query','')} | {q.get('label','')} | {q.get('hits',0):,} |"
        for q in sorted(queries, key=lambda q: q.get("hits", 0), reverse=True)
    )
    total = sum(q.get("hits", 0) for q in queries)

    return f"""## Search Query Statistics ({len(queries)} queries · {total:,} total hits)

| Surface | Query | Label | Hits |
|---|---|---|---|
{rows}
"""


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

_GLOSSARY = """\
## How to read this report

**Metamorphic testing (MT)** — a testing technique where a *metamorphic relation* (a rule
about how outputs should change when inputs change in a predictable way) is defined and then
verified against the software under test.

**Metamorphic relation (MR)** — the specific rule linking related inputs and outputs,
e.g. "rotating an image 360° must return the original image."

**Metamorphic group** — a set of test inputs that are all related to each other through
the same metamorphic relation.

---

**How repositories are found (search phase)**

The pipeline queries GitHub across five surfaces — repository names/descriptions, source code
files, issues, pull requests, commit messages, and GitHub Discussions — using a set of search
terms derived from MT terminology.  Every candidate that could plausibly be relevant is
collected; false positives are filtered out in the analysis phase.

---

**How repositories are classified (analysis phase)**

Each cloned repository is scanned for *patterns* — regular expressions that look for evidence
of MT adoption in source files.  A **pattern** is a specific kind of signal, for example:

| Pattern | What it looks for |
|---|---|
| Class name: MetamorphicTest | A class named `MetamorphicTest` (or similar) in source code |
| Class name: MetamorphicRelation | A class named `MetamorphicRelation` in source code |
| Identifier: metamorphic_relation | A variable or function named `metamorphic_relation` |
| Identifier: metamorphic_test | A variable or function named `metamorphic_test` |
| Decorator: @metamorphic | The `@metamorphic` decorator used in MT frameworks |
| String: "metamorphic test/testing/tests" | An MT phrase used as a string literal |
| String: "metamorphic relation/relationship" | An MR phrase used as a string literal |
| String: "metamorphic group/groups" | An MG phrase used as a string literal |
| Comment: metamorphic test/testing/tests | A code comment mentioning MT |
| Comment: metamorphic relation/relationship | A code comment mentioning an MR |
| Comment: metamorphic group/groups | A code comment mentioning an MG |

Each time a pattern matches a line in a file, that is called a **match** (also shown as
"direct match" in tables).  A single file can produce multiple matches from different patterns.

**Patterns matched** in tables and JSON output lists which of the patterns above fired for
that repository, so the evidence is immediately readable without needing to look up codes.

---

**Classification tiers**

| Tier | Criteria | Meaning |
|---|---|---|
| **strong_explicit** | 3 or more matches | Multiple distinct MT signals found — high confidence of genuine adoption |
| **weak_explicit** | 1 or 2 matches | At least one direct signal — possible adoption, worth checking manually |
| **none** | 0 matches | No MT evidence found in the source code |

**Score** = total number of matches found in the repository (raw count, no weighting).
Higher score = more evidence of MT adoption.

---
"""


def build_report(data: dict, plots_rel: str, fmt: str, top_n: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    parts = [
        f"# MT GitHub Mining — Results Report\n\n*Generated: {ts}*\n\n---\n",
        _GLOSSARY,
        sec_funnel(data),
        "---\n",
        sec_rq21(data, plots_rel, fmt),
        "---\n",
        sec_rq22(data, plots_rel, fmt),
        "---\n",
        sec_rq23(data, plots_rel, fmt),
        "---\n",
        sec_rq24(plots_rel, fmt),
        "---\n",
        sec_rq25(data, plots_rel, fmt),
        "---\n",
        sec_rq26(data, plots_rel, fmt),
        "---\n",
        sec_rq27(data, plots_rel, fmt),
        "---\n",
        sec_rq28(data, plots_rel, fmt, top_n),
        "---\n",
        sec_all_repos(data),
        "---\n",
        sec_query_stats(data),
    ]
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run(
    results_dir:   Path,
    out_path:      Path,
    plots_dir:     Path,
    refresh_plots: bool,
    top_n:         int,
    fmt:           str,
    dpi:           int,
) -> None:
    console.rule("[bold blue]Phase 5: Results Report[/]")

    data    = load_data(results_dir)
    missing = [k for k, v in data.items() if v is None]
    if missing:
        console.print(f"  [yellow]Not found (sections skipped):[/] {', '.join(missing)}")
    if not data["repo_scores"]:
        console.print("[red]repo_scores.json missing — run Phase 3 first.[/]")
        return

    # Ensure plots exist
    plots_dir.mkdir(parents=True, exist_ok=True)
    has_plots = any(plots_dir.iterdir()) if plots_dir.exists() else False
    if refresh_plots or not has_plots:
        console.print("  Regenerating plots…")
        import plot as plot_phase
        plot_phase.run(plots_dir, fmt, dpi)
    else:
        console.print(f"  [dim]Using existing plots (--refresh-plots to regenerate)[/]")

    # Relative path from report directory to plots directory
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plots_rel = os.path.relpath(plots_dir.resolve(), out_path.parent.resolve())
    plots_rel = plots_rel.replace("\\", "/")

    report = build_report(data, plots_rel, fmt, top_n)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    console.print(f"[bold green]Saved:[/] {out_path}")


def main() -> None:
    default_out   = RESULTS_DIR / "analysis" / "summary_report.md"
    default_plots = RESULTS_DIR / "plots"

    parser = argparse.ArgumentParser(
        prog="python report.py",
        description="Phase 5: results report from existing pipeline outputs.",
    )
    parser.add_argument("--output",        type=Path, default=default_out)
    parser.add_argument("--plots-dir",     type=Path, default=default_plots)
    parser.add_argument("--refresh-plots", action="store_true")
    parser.add_argument("--top-repos",     type=int,  default=20, metavar="N")
    parser.add_argument("--format",        choices=["png", "pdf", "svg"], default="png")
    parser.add_argument("--dpi",           type=int,  default=150)
    args = parser.parse_args()

    run(
        results_dir   = RESULTS_DIR,
        out_path      = args.output,
        plots_dir     = args.plots_dir,
        refresh_plots = args.refresh_plots,
        top_n         = args.top_repos,
        fmt           = args.format,
        dpi           = args.dpi,
    )


if __name__ == "__main__":
    main()
