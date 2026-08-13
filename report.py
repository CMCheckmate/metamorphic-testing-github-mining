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
# Helpers for surface-origin analysis
# ---------------------------------------------------------------------------

_SURFACE_LABEL: dict[str, str] = {
    "repo":       "Repo description / README",
    "code":       "Code search (live source files)",
    "commit":     "Commit messages",
    "issue":      "Issues",
    "pr":         "Pull requests",
    "discussion": "Discussions (GraphQL)",
}

_SURFACE_PRIORITY = {"code": 0, "repo": 1, "commit": 2, "issue": 3, "pr": 4, "discussion": 5}


def _surface_of(query_label: str) -> str:
    """Map a found_by_queries label to its search surface (new-format labels only)."""
    for prefix in ("code", "commit", "issue", "pr", "repo"):
        if query_label.startswith(prefix + "_"):
            return prefix
    return "discussion"


def _build_raw_to_surface(summary: dict | None) -> dict[str, str]:
    """Map raw query string → surface type from summary.json.
    Used to interpret old-format found_by_queries entries (raw strings, not labels).
    When the same raw string appears on multiple surfaces, highest-priority wins.
    """
    out: dict[str, str] = {}
    for q in (summary or {}).get("queries", []):
        raw     = q.get("query", "")
        surface = q.get("type", "discussion")
        if raw not in out or _SURFACE_PRIORITY.get(surface, 99) < _SURFACE_PRIORITY.get(out.get(raw, "discussion"), 99):
            out[raw] = surface
    return out


def _build_raw_to_label(summary: dict | None) -> dict[str, str]:
    """Map raw query string → label from summary.json (for old-format found_by_queries)."""
    out: dict[str, str] = {}
    for q in (summary or {}).get("queries", []):
        raw     = q.get("query", "")
        label   = q.get("label", raw)
        surface = q.get("type", "discussion")
        if raw not in out or _SURFACE_PRIORITY.get(surface, 99) < _SURFACE_PRIORITY.get(
            _SURFACE_PRIORITY.get(_surface_of(out.get(raw, "")), 99), 99
        ):
            out[raw] = label
    return out


def _entry_surface(entry: str, raw_to_surface: dict[str, str]) -> str:
    """Determine the surface for a found_by_queries entry (label or raw string)."""
    s = _surface_of(entry)
    if s != "discussion":
        return s
    return raw_to_surface.get(entry, "discussion")


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

    n_cloned = n_error = n_skipped_size = 0
    if data["manifest"]:
        for v in data["manifest"].get("repos", {}).values():
            if v.get("status") in ("cloned", "refreshed", "skipped_exists"):
                n_cloned += 1
            elif v.get("status") == "error":
                n_error += 1
            elif v.get("status") == "skipped_size":
                n_skipped_size += 1

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

    skipped_size_row = f"| Skipped — too large (> {750_000 // 1000} MB) | {n_skipped_size:,} |\n" if n_skipped_size else ""

    return f"""## Pipeline Funnel

| Stage | Count |
|---|---|
| Repos found in search | {len(repo_set):,} |
| Cloned | {n_cloned:,} |
| Clone errors | {n_error:,} |
{skipped_size_row}| Analysed | {n:,} |
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

    # --- Surface-origin breakdown for "none" repos ---
    raw_to_surface = _build_raw_to_surface(data.get("summary"))
    none_scores = [r for r in scores if r["classification"] == "none"]
    none_surface_block = ""
    if none_scores:
        surface_counter: Counter = Counter()
        code_and_none: list[str] = []
        for r in none_scores:
            surfaces = {_entry_surface(q, raw_to_surface) for q in r.get("found_by_queries", [])}
            for s in surfaces:
                surface_counter[s] += 1
            if "code" in surfaces:
                code_and_none.append(r["repo"])

        none_surface_rows = "\n".join(
            f"| {_SURFACE_LABEL.get(s, s)} | {cnt:,} | {_pct(cnt / n_no * 100)} |"
            for s, cnt in sorted(surface_counter.items(), key=lambda x: -x[1])
        )

        code_note = ""
        if code_and_none:
            code_list = "\n".join(
                f"  - [{repo}](https://github.com/{repo})"
                for repo in sorted(code_and_none)[:20]
            )
            extra = f" (showing first 20)" if len(code_and_none) > 20 else ""
            code_note = (
                f"\n> **{len(code_and_none)} no-signal repo(s) were also found by Phase 1 code search{extra}.**"
                f" GitHub's live-file index found an MT identifier in those repos, but Phase 3's"
                f" local scan found nothing. Likely causes: the match was in a vendored dependency,"
                f" a compiled artifact, a non-default branch, or a file added/deleted between"
                f" search and clone. These are worth a manual look:\n{code_list}\n"
            )

        none_surface_block = f"""
### Why are {n_no:,} repos classified as "No signal"?

These repos were returned by GitHub's search API for MT-related terms, but Phase 3's local file scan found no MT patterns in their source code. The table below shows *which search surface* surfaced each repo — a repo in the "Commit messages" row was discovered because a commit message mentioned MT, not because the code contains it.

| Found via | Repos | % of no-signal |
|---|---|---|
{none_surface_rows}

*A repo can appear in more than one row if it was found by multiple surfaces.*

The most common explanation is that MT was mentioned in a discussion or commit context ("added metamorphic testing to the backlog") without ever being implemented in source code. The search phase is intentionally broad to avoid missing genuine adopters; Phase 3 is the filter that confirms actual code-level adoption.
{code_note}"""

    return f"""## Q1 — Prevalence

| Classification | Repos | % of analysed |
|---|---|---|
| Strong explicit (≥ 3 signals) | {n_st:,} | {_pct(n_st/n*100)} |
| Weak explicit (1–2 signals) | {n_wk:,} | {_pct(n_wk/n*100)} |
| **Total with MT signal** | **{n_ex:,}** | **{_pct(n_ex/n*100)}** |
| No signal | {n_no:,} | {_pct(n_no/n*100)} |
| Total analysed | {n:,} | — |

{_img(plots_rel, 'classification_dist', fmt, 'Classification tier distribution')}
{_img(plots_rel, 'query_repos', fmt, 'Distinct repos matched per search query, coloured by surface')}

> **Reading the repos-per-query chart:** Each bar shows how many distinct repositories in the final analysed set were matched by that specific query. Bars are coloured by search surface. This answers "which query terms are actually finding repos?" — a query with many API hits but few matched repos may be broad on GitHub but maps to repos already captured by other queries.

{_img(plots_rel, 'query_hits', fmt, 'Raw API hit counts per query (before deduplication)')}
{_img(plots_rel, 'query_overlap', fmt, 'Repos found by N distinct independent search queries')}

> **Reading the query overlap chart:** Each bar shows how many repositories were found by exactly N distinct search queries. A repo at x=1 was surfaced by only a single query term on a single search surface; a repo at x=5 appeared independently in five different queries (e.g. a repository search for `"metamorphic testing"`, a code search for `MetamorphicRelation`, a commit search for `"metamorphic relation"`, and so on). The chart answers: *how redundantly is each repo captured by the search strategy?* Repos at higher x values are more robustly discovered — their MT-related content is broad enough to be picked up across multiple independent query terms and surfaces, making them less likely to be missed if any single query were removed. Most repos are expected to cluster at low x values since most genuine MT repos will mention only a subset of all MT terminology.
{none_surface_block}
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
    return """## Q4 — Domain Analysis

Automated domain classification (e.g. web development, scientific computing, systems software) is not feasible from repository metadata alone — it requires semantic understanding of the repository's purpose that goes beyond language and name.

**Proxy:** Programming language is the strongest available signal. Language choice correlates closely with domain:

| Language | Typical domain |
|---|---|
| Python | Data science, scientific computing, ML |
| Java / Kotlin | Enterprise software, Android |
| JavaScript / TypeScript | Web development |
| C / C++ | Systems, embedded, high-performance computing |
| Go | Cloud infrastructure, DevOps tooling |
| Rust | Systems, WebAssembly, performance-critical software |

See **Q3** for the full language distribution across MT-adopting repos. A language × tier heatmap was previously included here but removed — it duplicated Q3 without adding interpretable domain information.

For a more precise domain breakdown, manual inspection or LLM-based classification of repo descriptions and README files would be required.
"""


def sec_rq25(data: dict, plots_rel: str, fmt: str) -> str:
    scores = data["repo_scores"] or []
    if not scores:
        return ""

    current_year = datetime.now(timezone.utc).year
    n_total = len(scores)

    buckets = [
        ("0",         lambda s: s == 0),
        ("1–10",      lambda s: 1 <= s <= 10),
        ("11–100",    lambda s: 11 <= s <= 100),
        ("101–1,000", lambda s: 101 <= s <= 1_000),
        ("> 1,000",   lambda s: s > 1_000),
    ]

    rows = []
    for label, pred in buckets:
        bucket = [r for r in scores if pred(r.get("stars", 0))]
        if not bucket:
            continue
        n_b  = len(bucket)
        n_ex = sum(1 for r in bucket if r["classification"] in ("strong_explicit", "weak_explicit"))
        maturity = []
        for r in bucket:
            created = (r.get("created_at") or "")[:4]
            if created.isdigit():
                age = max(1, current_year - int(created))
                maturity.append(r.get("stars", 0) / age)
        med_mat = f"{statistics.median(maturity):.1f}" if maturity else "—"
        rows.append(
            f"| {label} | {n_b:,} | {_pct(n_b / n_total * 100)} "
            f"| {n_ex:,} | {_pct(n_ex / n_b * 100)} | {med_mat} |"
        )

    return f"""## Q5 — Project Maturity

Star count as a proxy for production relevance and community uptake.
**★/yr** = stars ÷ repo age in years — normalises for newer projects that haven't had time to accumulate stars.

| Stars | Repos | % of total | With MT signal | % with MT signal | Median ★/yr |
|---|---|---|---|---|---|
{"".join(rows)}

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

    commit_hits = len(data.get("commits") or []) if data else 0
    commit_note = (
        f"\n> **Note:** Only {len(orgs):,} unique owners account for all explicit MT repos, "
        f"yet the commit search surface returned {commit_hits:,} raw hits. "
        f"This discrepancy suggests that many commit messages mention MT terminology "
        f"(referencing papers, tools, or planned work) without the corresponding source code "
        f"containing explicit MT patterns — i.e. discussion of MT in commit history does not "
        f"imply implementation. It may also indicate that a small group of active MT researchers "
        f"commits frequently across multiple repos."
    ) if commit_hits > len(orgs) * 5 else ""

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
{commit_note}

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


# ---------------------------------------------------------------------------
# Framework vs Adopter classification
# ---------------------------------------------------------------------------

_TEST_DIR_PARTS = frozenset({
    "test", "tests", "spec", "specs", "testing", "__tests__",
    "e2e", "integration", "unit", "unittest", "functionaltest",
    "systemtest", "acceptancetest", "testcases", "testcase",
})


def _is_test_file(filepath: str) -> bool:
    """Heuristic: true if this file path looks like a test file."""
    parts = filepath.replace("\\", "/").lower().split("/")
    if any(p in _TEST_DIR_PARTS for p in parts[:-1]):
        return True
    fname = parts[-1]
    return (
        fname.startswith("test_") or
        fname.endswith("_test.py") or fname.endswith("_test.java") or
        fname.endswith("_test.go") or fname.endswith("_test.rb") or
        fname.endswith("_test.js") or fname.endswith("_test.ts") or
        fname.endswith("test.py") or fname.endswith("test.java") or
        fname.endswith("test.go") or
        fname.endswith("spec.rb") or fname.endswith("spec.js") or
        fname.endswith("spec.ts") or fname.endswith("_spec.py") or
        fname.endswith("tests.py")
    )


def _repo_role(repo_name: str, findings: list[dict]) -> str:
    """Classify a repo as 'framework', 'adopter', or 'mixed'.

    Logic: look at WHERE in the file tree MT patterns appear.
    - Mostly in test dirs/files  → the repo USES MT to test its own code (adopter).
    - Mostly in non-test src     → the repo DEFINES MT infrastructure (framework/library).
    - Roughly equal split        → mixed / unclear.
    """
    repo_findings = [f for f in findings if f.get("repo") == repo_name]
    if not repo_findings:
        return "unknown"
    test_hits    = sum(1 for f in repo_findings if _is_test_file(f.get("file", "")))
    non_test_hits = len(repo_findings) - test_hits
    total = len(repo_findings)
    ratio = test_hits / total
    if ratio >= 0.65:
        return "adopter"
    if ratio <= 0.35:
        return "framework"
    return "mixed"


def sec_framework_vs_adopter(data: dict) -> str:
    scores   = data["repo_scores"] or []
    findings = data["findings"] or []
    if not scores or not findings:
        return ""

    explicit = [r for r in scores if r["classification"] in ("strong_explicit", "weak_explicit")]
    if not explicit:
        return ""

    roles       = {r["repo"]: _repo_role(r["repo"], findings) for r in explicit}
    role_counts = Counter(roles.values())
    n_ex        = len(explicit)

    summary_rows = "\n".join(
        f"| {role.capitalize()} | {role_counts[role]:,} | {_pct(role_counts[role] / n_ex * 100)} |"
        for role in ("adopter", "framework", "mixed", "unknown")
        if role_counts[role]
    )

    def _table(role: str) -> str:
        repos = sorted(
            [r for r in explicit if roles.get(r["repo"]) == role],
            key=lambda r: (r.get("score", 0), r.get("stars", 0)),
            reverse=True,
        )
        if not repos:
            return ""
        rows = "\n".join(
            f"| [{r['repo']}](https://github.com/{r['repo']}) "
            f"| {_tier(r['classification'])} "
            f"| {r.get('score', 0)} "
            f"| {r.get('language') or '—'} "
            f"| {r.get('stars', 0):,} |"
            for r in repos
        )
        return rows

    adopter_table   = _table("adopter")
    framework_table = _table("framework")
    mixed_table     = _table("mixed")

    adopter_section = f"""
**Adopters ({role_counts['adopter']:,})** — MT patterns found primarily in test directories/files. These repos use MT to test their own application code.

| Repository | Tier | Score | Language | Stars |
|---|---|---|---|---|
{adopter_table}
""" if adopter_table else ""

    framework_section = f"""
**Frameworks / Libraries ({role_counts['framework']:,})** — MT patterns found primarily in non-test source files. These repos define MT infrastructure that others can use.

| Repository | Tier | Score | Language | Stars |
|---|---|---|---|---|
{framework_table}
""" if framework_table else ""

    mixed_section = f"""
**Mixed / Unclear ({role_counts.get('mixed', 0) + role_counts.get('unknown', 0):,})** — MT patterns spread across both test and source files, or no findings data available. Manual inspection needed.

| Repository | Tier | Score | Language | Stars |
|---|---|---|---|---|
{_table("mixed")}
{_table("unknown")}
""" if (role_counts.get("mixed") or role_counts.get("unknown")) else ""

    return f"""## MT Framework vs Adopter Classification

Each explicit MT repo is classified by **where** its MT patterns appear in the file tree:

| Role | Repos | % of explicit |
|---|---|---|
{summary_rows}

> **Heuristic**: ≥ 65 % of findings in test dirs/files → *Adopter*; ≤ 35 % → *Framework*; between → *Mixed*. This is file-path based and may misclassify repos with unusual directory layouts — use the per-repo tables for manual verification.
{adopter_section}{framework_section}{mixed_section}"""


# ---------------------------------------------------------------------------
# No-signal repos (for manual inspection)
# ---------------------------------------------------------------------------

def sec_no_signal_repos(data: dict) -> str:
    scores  = data["repo_scores"] or []
    summary = data.get("summary")
    if not scores:
        return ""

    none_repos = [r for r in scores if r["classification"] == "none"]
    if not none_repos:
        return ""

    raw_to_surface = _build_raw_to_surface(summary)
    none_repos = sorted(none_repos, key=lambda r: r.get("stars", 0), reverse=True)

    def _surfaces(r: dict) -> str:
        found = {_entry_surface(q, raw_to_surface) for q in r.get("found_by_queries", [])}
        return ", ".join(sorted(found)) if found else "—"

    rows = "\n".join(
        f"| [{r['repo']}](https://github.com/{r['repo']}) "
        f"| {r.get('stars', 0):,} "
        f"| {r.get('language') or '—'} "
        f"| {(r.get('created_at') or '')[:4] or '—'} "
        f"| {_surfaces(r)} |"
        for r in none_repos
    )

    return f"""## No-Signal Repositories ({len(none_repos):,} repos — manual inspection)

These repos were returned by GitHub's search but Phase 3 found **zero** MT patterns in their source code. Sorted by stars so higher-profile repos can be prioritised for manual review.

| Repository | Stars | Language | Year | Found via |
|---|---|---|---|---|
{rows}
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

    # Invert found_by_queries to count unique repos per query label.
    # found_by_queries may store raw query strings (old data) or proper labels
    # (new data after the search.py fix); use summary.json to normalise both.
    raw_to_lbl = _build_raw_to_label(data.get("summary"))
    repos_per_label: Counter = Counter()
    for repo in (data["repo_scores"] or []):
        for entry in repo.get("found_by_queries", []):
            lbl = entry if _surface_of(entry) != "discussion" else raw_to_lbl.get(entry, entry)
            repos_per_label[lbl] += 1

    rows = "\n".join(
        f"| {q.get('type','').upper()} | {q.get('query','')} | {q.get('label','')} "
        f"| {q.get('hits',0):,} | {repos_per_label.get(q.get('label',''), 0):,} |"
        for q in sorted(queries, key=lambda q: q.get("hits", 0), reverse=True)
    )
    total = sum(q.get("hits", 0) for q in queries)

    return f"""## Search Query Statistics ({len(queries)} queries · {total:,} total hits)

*API hits = raw results returned by GitHub (before deduplication). Unique repos = distinct repos in the final analysed set that were found by this query.*

| Surface | Query | Label | API hits | Unique repos |
|---|---|---|---|---|
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

The pipeline queries GitHub across six search surfaces using MT-related terms. Each surface
searches a different part of a repository's history and content:

| Surface | Label prefix | Exactly what is searched | What a hit means |
|---|---|---|---|
| **Repositories** | `repo_` | Repository name, description, topic tags, and README file content | The repo presents itself as MT-related |
| **Code** | `code_` | Current content of every source file on the default branch at the time of search | MT terminology exists in the live source code |
| **Issues** | `issue_` | Issue title and body text (not comments) | A developer opened a ticket discussing MT |
| **Pull Requests** | `pr_` | PR title and body text (not review comments or the code diff) | A developer proposed a change described in MT terms |
| **Commits** | `commit_` | **Commit message text only** — not the code changes introduced by the commit | A developer wrote a commit message mentioning MT; the committed code itself is not searched here |
| **Discussions** | (GraphQL) | GitHub Discussion title and body text | A community discussion referenced MT |

> **Important:** A commit hit means the *message* said something like "add metamorphic testing for login module" — it does not mean the committed code contains MT patterns. Code-level adoption is only confirmed by the Code surface (Phase 1) and the local file scan (Phase 3).

Every candidate that could plausibly be relevant is collected across all six surfaces; false
positives are filtered out in the analysis phase.

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
| Comment: metamorphic property/properties | A code comment mentioning a metamorphic property |
| String: "metamorphic property/properties" | An MP phrase used as a string literal |
| Abbreviation: MT (metamorphic testing) | The standalone uppercase abbreviation `MT` used after the full term has been introduced |
| Abbreviation: MR (metamorphic relation) | The standalone uppercase abbreviation `MR` used after the full term has been introduced |
| Lemmatised Comment/String | A comment or string line containing "metamorphic" where NLTK lemmatisation identified a related concept (catches inflected forms like "tested", "grouped", "propert*" that the regex patterns miss) |

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
        sec_framework_vs_adopter(data),
        "---\n",
        sec_no_signal_repos(data),
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
