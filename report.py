"""
Phase 5 — Results Report
========================
All analysis sections apply exclusively to repositories where at least one
technique pattern was detected (score > 0). Non-detected repositories are
listed in Appendix A for manual review.

    python report.py --technique techniques/metamorphic_testing.yaml
"""

import argparse
import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

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

def _med(lst) -> str:
    return f"{statistics.median(lst):.1f}" if lst else "—"

def _mean(lst) -> str:
    return f"{statistics.mean(lst):.1f}" if lst else "—"

def _detected(scores):
    return [r for r in (scores or []) if r.get("score", 0) > 0]

def _not_detected(scores):
    return [r for r in (scores or []) if r.get("score", 0) == 0]

_SURFACE_LABEL = {
    "repo":       "Repo / README",
    "code":       "Code (source files)",
    "commit":     "Commit messages",
    "issue":      "Issues",
    "pr":         "Pull requests",
    "discussion": "Discussions",
}

_SURFACE_DESC = {
    "code":       "Contents of source files on the default branch",
    "repo":       "Repository name, description, topic tags, and README",
    "commit":     "Commit message text (not the diff/code itself)",
    "issue":      "Issue titles and body text",
    "pr":         "Pull request titles and body text",
    "discussion": "GitHub Discussion titles and body text",
}

def _surface_of(query_label: str) -> str:
    for prefix in ("code", "commit", "issue", "pr", "repo"):
        if query_label.startswith(prefix + "_"):
            return prefix
    return "discussion"


# ---------------------------------------------------------------------------
# Pipeline Summary
# ---------------------------------------------------------------------------

def sec_pipeline_summary(data: dict, profile) -> str:
    short = profile.short_name

    n_cloned = n_error = n_skipped_size = 0
    if data["manifest"]:
        for v in data["manifest"].get("repos", {}).values():
            if v.get("status") in ("cloned", "refreshed", "skipped_exists"):
                n_cloned += 1
            elif v.get("status") == "error":
                n_error += 1
            elif v.get("status") == "skipped_size":
                n_skipped_size += 1

    scores   = data["repo_scores"] or []
    n        = len(scores)
    n_det    = sum(1 for r in scores if r.get("score", 0) > 0)
    n_not    = n - n_det
    det_rate = n_det / n * 100 if n else 0

    total_hits = sum(q.get("hits", 0) for q in (data["summary"] or {}).get("queries", []))
    n_queries  = len((data["summary"] or {}).get("queries", []))

    repo_set: set = set()
    for r in (data["repos"] or []):
        repo_set.add(r.get("repo", "") or r.get("full_name", ""))
    repo_set.discard("")

    size_row = f"| Skipped — too large | {n_skipped_size:,} |\n" if n_skipped_size else ""

    # Which search surfaces were actually used
    used_surfaces: set = set()
    for q in (data["summary"] or {}).get("queries", []):
        s = q.get("type", "")
        if s:
            used_surfaces.add(s)

    surface_rows = "\n".join(
        f"| **{s.capitalize()}** | {_SURFACE_DESC.get(s, '')} |"
        for s in ["code", "repo", "commit", "issue", "pr", "discussion"]
        if s in used_surfaces
    )

    return f"""\
## Pipeline Summary

| Stage | Count |
|---|---|
| Candidates found via search | {len(repo_set):,} |
| Cloned | {n_cloned:,} |
| Clone errors | {n_error:,} |
{size_row}| Analysed | {n:,} |
| **Detected** | **{n_det:,} ({_pct(det_rate)})** |
| Not detected | {n_not:,} ({_pct(100 - det_rate)}) |

| Search | Value |
|---|---|
| Total queries run | {n_queries:,} |
| Total API hits | {total_hits:,} |

> *Detected* = ≥ 1 pattern match found in the cloned default branch. Not detected means no matching signal was found in our patterns — not that the technique is absent (non-standard terminology, non-default branches, or vendored code all cause misses). All figures are lower-bound estimates.

### Search Surfaces Used

Each surface corresponds to a distinct GitHub Search API endpoint.

| Surface | What is searched |
|---|---|
{surface_rows}

{_img('../plots', 'surface_breakdown', 'png', f'{short} — repositories found per search surface')}
{_img('../plots', 'query_hits', 'png', f'{short} — raw search hit counts per query')}
"""


# ---------------------------------------------------------------------------
# Adoption Overview — RQ1
# ---------------------------------------------------------------------------

def sec_adoption(data: dict, plots_rel: str, fmt: str, profile) -> str:
    scores   = data["repo_scores"] or []
    findings = data["findings"]    or []
    short    = profile.short_name
    detected = _detected(scores)
    not_det  = _not_detected(scores)
    n        = len(scores)
    n_det    = len(detected)
    if not n_det:
        return ""

    det_scores = [r["score"] for r in detected]
    med_score  = statistics.median(det_scores)
    mean_score = statistics.mean(det_scores)
    max_score  = max(det_scores)
    n_single   = sum(1 for s in det_scores if s == 1)

    # Code vs non-code: artifact breakdown aggregated
    total_art: Counter = Counter()
    for r in detected:
        for atype, cnt in (r.get("artifact_breakdown") or {}).items():
            total_art[atype] += cnt
    art_total   = sum(total_art.values())
    code_types  = {"test_code", "source_code"}
    code_total  = sum(v for k, v in total_art.items() if k in code_types)
    noncode_total = art_total - code_total
    cnc_section = ""
    if art_total > 0:
        cnc_section = f"""\

### Code vs Non-Code Mentions

Signal matches classified by where they appear in the repository file tree.

| Category | Matches | % |
|---|---|---|
| Code (test code + source code) | {code_total:,} | {_pct(code_total/art_total*100)} |
| Non-code (docs + config + other) | {noncode_total:,} | {_pct(noncode_total/art_total*100)} |

"""

    # Technique line/file ratios for detected repos
    line_density = [r.get("technique_line_density", 0) for r in detected if r.get("technique_line_density", 0) > 0]
    file_ratio   = [r.get("technique_file_ratio", 0) for r in detected if r.get("technique_file_ratio", 0) > 0]
    tech_lines   = [r.get("technique_lines", 0) for r in detected if r.get("technique_lines", 0) > 0]
    tech_files   = [r.get("technique_files", 0) for r in detected if r.get("technique_files", 0) > 0]

    ratio_section = ""
    if line_density or file_ratio:
        ratio_section = f"""\

### Technique Lines and Files (Detected Repos)

How much of each detected repo's content contains technique signals.

| Metric | Value |
|---|---|
| Median technique lines | {_med(tech_lines)} |
| Mean technique lines | {_mean(tech_lines)} |
| Median technique line density | {_pct(statistics.median(line_density)*100) if line_density else '—'} |
| Median technique files | {_med(tech_files)} |
| Mean technique files | {_mean(tech_files)} |
| Median technique file ratio | {_pct(statistics.median(file_ratio)*100) if file_ratio else '—'} |
| Repos with > 10% file coverage | {sum(1 for v in file_ratio if v > 0.1):,} |

{_img(plots_rel, 'technique_ratios', fmt, f'{short} — technique line density and file ratio distributions')}
"""

    # Contributor stats
    git_c = [r.get("contributor_count_git", 0) for r in detected if r.get("contributor_count_git", 0) > 0]
    contrib_section = ""
    if git_c:
        contrib_section = f"""\

### Contributor Activity

Unique author email addresses from sampled git history (≤ 500 commits per repo).

| Metric | Value |
|---|---|
| Repos with contributor data | {len(git_c):,} |
| Median contributors | {_med(git_c)} |
| Mean contributors | {_mean(git_c)} |
| Max contributors | {max(git_c):,} |
| Single-contributor repos | {sum(1 for c in git_c if c == 1):,} ({_pct(sum(1 for c in git_c if c == 1)/len(git_c)*100)}) |
| Repos with > 10 contributors | {sum(1 for c in git_c if c > 10):,} ({_pct(sum(1 for c in git_c if c > 10)/len(git_c)*100)}) |

{_img(plots_rel, 'contributor_dist', fmt, f'{short} — contributor count distribution')}"""

    return f"""\
## Adoption Overview

### Detection Count Distribution

{_img(plots_rel, 'detection_count_hist', fmt, f'{short} — detection count distribution (detected repos)')}

| Metric | Value |
|---|---|
| Total analysed | {n:,} |
| Total detected | {n_det:,} ({_pct(n_det/n*100)}) |
| Not detected | {len(not_det):,} ({_pct(len(not_det)/n*100)}) |
| Median detection count | {med_score:.1f} |
| Mean detection count | {mean_score:.1f} |
| Maximum detection count | {max_score:,} |
| Single-match detections | {n_single:,} ({_pct(n_single/n_det*100)}) |
{cnc_section}{ratio_section}{contrib_section}
"""


# ---------------------------------------------------------------------------
# Usage Patterns — RQ2
# ---------------------------------------------------------------------------

def sec_usage(data: dict, plots_rel: str, fmt: str, profile) -> str:
    scores   = data["repo_scores"] or []
    findings = data["findings"]    or []
    short    = profile.short_name
    detected = _detected(scores)
    not_det  = _not_detected(scores)
    if not detected:
        return ""
    n_det   = len(detected)

    # --- Project type ---
    type_counts = Counter(r.get("project_type", "unknown") for r in detected)
    type_order  = ["general_usage", "framework", "mixed", "research_artifact", "documentation_only", "unknown"]
    type_display = {
        "general_usage":      "Actual Usage",
        "framework":          "Framework / Library",
        "mixed":              "Mixed",
        "research_artifact":  "Research Artifact",
        "documentation_only": "Docs Only",
        "unknown":            "Unknown",
    }
    type_desc = {
        "general_usage":     "Signals in test dirs (`tests/`, `spec/`, `*_test.*`). Technique is actively used in the project's testing.",
        "framework":         "Signals in source dirs (`src/`, `lib/`, `core/`). The project implements or extends the technique.",
        "research_artifact": "Signals alongside paper markers (`paper`, `evaluation`, `artifact`). Replication study or benchmarking repo.",
        "mixed":             "Signals in both source and test dirs. Technique used as both implementation target and test method.",
        "unknown":           "No clear dir-based classification.",
    }
    type_rows = "\n".join(
        f"| {type_display.get(k, k)} | {type_counts[k]:,} | {_pct(type_counts[k]/n_det*100)} |"
        for k in type_order if type_counts.get(k, 0) > 0
    )
    excl_row = f"| **Not Detected (excluded)** | {len(not_det):,} | — |"
    type_desc_rows = "\n".join(
        f"| {type_display.get(k, k)} | {type_desc.get(k, '')} |"
        for k in type_order if type_counts.get(k, 0) > 0
    )

    # --- Detection distribution (coverage depth + keyword density) ---
    files_per: dict = defaultdict(set)
    for f in findings:
        if f.get("repo") in {r["repo"] for r in detected}:
            files_per[f.get("repo")].add(f.get("file", ""))
    if not files_per:
        for r in detected:
            for i in range(int(r.get("technique_files", 0))):
                files_per[r["repo"]].add(f"f{i}")
    file_cnts = [len(v) for v in files_per.values()]
    n_cov     = len(file_cnts)

    bins_spec = [(1, 1, "1"), (2, 2, "2"), (3, 5, "3–5"), (6, 10, "6–10"), (11, 20, "11–20"), (21, 10**9, ">20")]
    cov_rows  = "\n".join(
        f"| {lbl} | {sum(1 for c in file_cnts if lo <= c <= hi):,} |"
        for lo, hi, lbl in bins_spec
    )

    avg_m = [r["avg_mentions_per_technique_file"] for r in detected
             if r.get("avg_mentions_per_technique_file", 0) > 0]
    max_m = [r.get("max_mentions_in_file", 0) for r in detected if r.get("max_mentions_in_file", 0) > 0]
    conc  = [r.get("max_mentions_in_file", 0) / max(r.get("score", 1), 1)
             for r in detected if r.get("score", 0) > 0]
    pat_breadth = [len(r.get("patterns_matched", [])) for r in detected]

    spread_stats = ""
    if avg_m:
        spread_stats = f"""\

| Spread Metric | Value |
|---|---|
| Median signal-containing files per repo | {_med(file_cnts)} |
| Mean signal-containing files per repo | {_mean(file_cnts)} |
| Single-file signal repos | {sum(1 for c in file_cnts if c == 1):,} ({_pct(sum(1 for c in file_cnts if c == 1)/n_cov*100) if n_cov else '—'}) |
| Median avg matches per technique file | {_med(avg_m)} |
| Mean avg matches per technique file | {_mean(avg_m)} |
| Median max matches in a single file | {_med(max_m)} |
| Mean signal concentration (max/total) | {_pct(sum(conc)/len(conc)*100) if conc else '—'} |
| Median unique pattern types per repo | {_med(pat_breadth)} |
| Mean unique pattern types per repo | {_mean(pat_breadth)} |
"""

    # --- Language ---
    lang_counts = Counter(r.get("language") or "Unknown" for r in detected)
    top_langs   = lang_counts.most_common(15)
    lang_rows   = "\n".join(
        f"| {lang} | {cnt:,} | {_pct(cnt/n_det*100)} |"
        for lang, cnt in top_langs
    )

    # --- Artifact type ---
    total_art: Counter = Counter()
    for r in detected:
        for atype, cnt in (r.get("artifact_breakdown") or {}).items():
            total_art[atype] += cnt
    art_total = sum(total_art.values())
    art_order = ["test_code", "source_code", "documentation", "config", "other"]
    art_desc  = {
        "test_code":     "Files in test directories (`tests/`, `spec/`, `*test*`, `*_spec.*`)",
        "source_code":   "Non-test source files (`src/`, `lib/`, `*.py`, `*.java`, `*.cpp`, etc.)",
        "documentation": "Markdown, RST, and plain-text docs (`*.md`, `*.rst`, `*.txt`, `docs/`)",
        "config":        "Config and build files (`*.yml`, `*.toml`, `*.ini`, `*.gradle`, `Makefile`)",
        "other":         "All other file types not matched above",
    }
    art_rows = "\n".join(
        f"| {k.replace('_',' ').title()} | {total_art.get(k, 0):,} | {_pct(total_art.get(k,0)/art_total*100) if art_total else '—'} |"
        for k in art_order if total_art.get(k, 0) > 0
    )
    art_desc_rows = "\n".join(
        f"| {k.replace('_',' ').title()} | {art_desc[k]} |"
        for k in art_order if total_art.get(k, 0) > 0
    )

    # --- Domains ---
    domain_counts: Counter = Counter()
    for r in detected:
        for d in (r.get("inferred_domains") or []):
            domain_counts[d] += 1
    domain_rows = "\n".join(
        f"| {k.replace('_',' ').title()} | {v:,} | {_pct(v/n_det*100)} |"
        for k, v in domain_counts.most_common()
    ) if domain_counts else ""

    domain_section = ""
    if domain_rows:
        domain_section = f"""\

### Application Domain

Inferred from repo name, description, and GitHub topics (keyword matching). A repo can match multiple domains.

| Domain | Repos | % of detected |
|---|---|---|
{domain_rows}

{_img(plots_rel, 'domain_dist', fmt, f'{short} — inferred domain distribution')}"""

    return f"""\
## Usage Patterns

### Project Role Classification

Repos are classified by where technique signals appear in the directory tree. Not-detected repos are excluded from the use-case stats below.

| Classification | Repos | % of detected |
|---|---|---|
{type_rows}
{excl_row}

| Classification | Description |
|---|---|
{type_desc_rows}

{_img(plots_rel, 'project_type_dist', fmt, f'{short} — project role distribution (including not-detected)')}

### Detection Distribution

How technique signals are distributed within repos: spread across files, density per file, and location in test infrastructure.
{spread_stats}
| Files with signals | Repos |
|---|---|
{cov_rows}

{_img(plots_rel, 'coverage_depth', fmt, f'{short} — signal coverage depth (files per repo)')}
{_img(plots_rel, 'keyword_density', fmt, f'{short} — keyword density per technique file')}
{_img(plots_rel, 'test_structure', fmt, f'{short} — signal location in test infrastructure')}

### Language Distribution

| Language | Detected repos | % |
|---|---|---|
{lang_rows}

{_img(plots_rel, 'language_dist', fmt, f'{short} — language distribution (top 15)')}

### Artifact Type Distribution

Where in the file tree signals appear across all {len(findings):,} total matches.

| Artifact Type | Matches | % |
|---|---|---|
{art_rows}

| Artifact Type | Files included |
|---|---|
{art_desc_rows}

{_img(plots_rel, 'artifact_breakdown', fmt, f'{short} — signal distribution by artifact type')}

### File Extension Breakdown

Extension-level breakdown of files containing technique signals.

{_img(plots_rel, 'extension_breakdown', fmt, f'{short} — signal matches by file extension')}
{domain_section}
"""


# ---------------------------------------------------------------------------
# Timeline — RQ3
# ---------------------------------------------------------------------------

def sec_temporal(data: dict, plots_rel: str, fmt: str, profile) -> str:
    scores   = data["repo_scores"] or []
    short    = profile.short_name
    detected = _detected(scores)
    if not scores:
        return ""

    # Yearly breakdown
    by_year: dict = defaultdict(lambda: {"det": 0, "not": 0})
    for r in scores:
        d = r.get("created_at", "")
        if d and len(d) >= 4 and d[:4].isdigit():
            y = int(d[:4])
            if 2010 <= y <= 2026:
                if r.get("score", 0) > 0:
                    by_year[y]["det"] += 1
                else:
                    by_year[y]["not"] += 1
    year_rows = "\n".join(
        f"| {y} | {by_year[y]['det']:,} | {by_year[y]['not']:,} | {by_year[y]['det']+by_year[y]['not']:,} |"
        for y in sorted(by_year)
    )

    # Commit stats (detected only)
    commit_ratio  = [r.get("technique_commit_ratio", 0.0) for r in detected
                     if r.get("total_commits_sampled", 0) > 0]
    commit_span   = [r.get("technique_commit_span_days", 0) / 365.25 for r in detected
                     if r.get("technique_commit_span_days", 0) > 0]
    total_sampled = [r.get("total_commits_sampled", 0) for r in detected
                     if r.get("total_commits_sampled", 0) > 0]

    # First / last commit years
    first_years = []
    last_years  = []
    for r in detected:
        fd = r.get("first_technique_commit_date", "")
        ld = r.get("last_technique_commit_date", "")
        if fd and len(fd) >= 4 and fd[:4].isdigit():
            first_years.append(int(fd[:4]))
        if ld and len(ld) >= 4 and ld[:4].isdigit():
            last_years.append(int(ld[:4]))

    commit_section = ""
    if commit_ratio:
        n_high = sum(1 for v in commit_ratio if v >= 0.1)

        first_yr_row = f"| Median first technique commit year | {_med(first_years)} |" if first_years else ""
        last_yr_row  = f"| Median last technique commit year  | {_med(last_years)} |"  if last_years  else ""
        span_row     = f"| Median technique commit span       | {_med(commit_span)} yrs |" if commit_span else ""

        commit_section = f"""\

### Commit Activity

Computed from up to 500 most-recent commits per repo (git log, no merges).

| Metric | Value |
|---|---|
| Repos with commit data | {len(commit_ratio):,} |
| Median commits sampled | {_med(total_sampled)} |
{first_yr_row}
{last_yr_row}
{span_row}
| Mean technique commit span | {_mean(commit_span)} yrs |
| Median technique commit ratio | {_med([v*100 for v in commit_ratio])}% |
| Mean technique commit ratio | {_mean([v*100 for v in commit_ratio])}% |
| Repos with > 10% technique commits | {n_high:,} ({_pct(n_high/len(commit_ratio)*100)}) |

{_img(plots_rel, 'commit_timeline', fmt, f'{short} — technique commit activity over time (commits per year)')}
{_img(plots_rel, 'commit_first_last', fmt, f'{short} — first and last technique commit year (overlaid)')}
{_img(plots_rel, 'commit_span', fmt, f'{short} — first-to-last commit duration distribution (years)')}
{_img(plots_rel, 'commit_ratio_dist', fmt, f'{short} — technique commit ratio distribution')}"""

    return f"""\
## Timeline

### Repository Creation Trend

| Year | Detected | Not detected | Total |
|---|---|---|---|
{year_rows}

{_img(plots_rel, 'yearly_trend', fmt, f'{short} — detected repos by creation year')}
{commit_section}
"""


# ---------------------------------------------------------------------------
# Pattern Activity (from input YAML patterns)
# ---------------------------------------------------------------------------

def sec_pattern_activity(data: dict, plots_rel: str, fmt: str, profile) -> str:
    scores   = data["repo_scores"] or []
    findings = data["findings"]    or []
    short    = profile.short_name
    detected = _detected(scores)
    n_det    = len(detected)
    if not findings:
        return ""

    pat_totals: Counter = Counter(f["label"] for f in findings)
    repos_per_pat: Counter = Counter()
    for r in scores:
        for lbl in r.get("patterns_matched", []):
            repos_per_pat[lbl] += 1
    if not repos_per_pat:
        return ""

    pat_rows = "\n".join(
        f"| {lbl} | {repos_per_pat[lbl]:,} | {pat_totals[lbl]:,} |"
        for lbl, _ in repos_per_pat.most_common()
    )

    return f"""\
## Pattern Activity

{len(findings):,} total pattern matches across {n_det:,} detected repositories.

| Pattern | Repos | Total matches |
|---|---|---|
{pat_rows}

{_img(plots_rel, 'pattern_freq', fmt, f'{short} — pattern match frequency')}
"""


# ---------------------------------------------------------------------------
# Top Detected Repositories
# ---------------------------------------------------------------------------

def sec_top_repos(data: dict, profile, top_n: int = 30) -> str:
    scores   = data["repo_scores"] or []
    detected = _detected(scores)
    if not detected:
        return ""
    top = sorted(detected, key=lambda r: (r.get("score", 0), r.get("stars", 0)), reverse=True)[:top_n]
    rows = "\n".join(
        f"| [{r['repo']}](https://github.com/{r['repo']}) "
        f"| {r.get('score', 0):,} "
        f"| {r.get('technique_files', 0):,} "
        f"| {r.get('project_type', '—').replace('_',' ')} "
        f"| {r.get('language') or '—'} "
        f"| {r.get('stars', 0):,} "
        f"| {(r.get('created_at') or '')[:4] or '—'} |"
        for r in top
    )
    return f"""\
## Top Detected Repositories

Top {min(top_n, len(detected))} by detection count (then stars).

| Repository | Detections | Signal files | Project type | Language | Stars | Year |
|---|---|---|---|---|---|---|
{rows}
"""


# ---------------------------------------------------------------------------
# Appendix A — Not-Detected Repositories
# ---------------------------------------------------------------------------

def sec_non_detected(data: dict, profile) -> str:
    scores  = data["repo_scores"] or []
    not_det = _not_detected(scores)
    if not not_det:
        return ""
    short = profile.short_name
    sorted_repos = sorted(not_det, key=lambda r: r.get("stars", 0), reverse=True)

    rows = "\n".join(
        f"| [{r['repo']}](https://github.com/{r['repo']}) "
        f"| {r.get('language') or '—'} "
        f"| {r.get('stars', 0):,} "
        f"| {(r.get('created_at') or '')[:4] or '—'} "
        f"| {'; '.join({_surface_of(q) for q in r.get('found_by_queries', [])}) or '—'} |"
        for r in sorted_repos
    )
    return f"""\
## Appendix A — Not-Detected Repositories ({len(not_det):,})

No {short} pattern matches found in cloned default branch. Listed for manual review (sorted by stars).

| Repository | Language | Stars | Year | Found via |
|---|---|---|---|---|
{rows}
"""


# ---------------------------------------------------------------------------
# Appendix B — Query Statistics
# ---------------------------------------------------------------------------

def sec_query_stats(data: dict) -> str:
    summary = data["summary"]
    if not summary:
        return ""
    queries = summary.get("queries", [])
    if not queries:
        return ""

    repos_per_label: Counter = Counter()
    for repo in (data["repo_scores"] or []):
        for entry in repo.get("found_by_queries", []):
            repos_per_label[entry] += 1

    rows  = "\n".join(
        f"| {q.get('type','').upper()} | {q.get('query','')[:60]} | {q.get('hits',0):,} | {repos_per_label.get(q.get('label',''), 0):,} |"
        for q in sorted(queries, key=lambda q: q.get("hits", 0), reverse=True)
    )
    total = sum(q.get("hits", 0) for q in queries)

    return f"""\
## Appendix B — Search Query Statistics

{len(queries)} queries · {total:,} total API hits

| Surface | Query | API hits | Repos in analysis |
|---|---|---|---|
{rows}
"""


# ---------------------------------------------------------------------------
# Appendix C — Pattern Reference
# ---------------------------------------------------------------------------

def sec_pattern_index(profile) -> str:
    if not getattr(profile, "patterns_raw", None):
        return ""
    rows = "\n".join(
        f"| `{p['id']}` | {p['label']} |"
        for p in profile.patterns_raw
    )
    return f"""\
## Appendix C — Pattern Reference

| Pattern ID | Description |
|---|---|
{rows}
"""


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(data: dict, plots_rel: str, fmt: str, top_n: int, profile) -> str:
    ts    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tech  = profile.name
    short = profile.short_name

    parts = [
        f"# {tech} — GitHub Mining Report\n\n"
        f"*{short} · Generated: {ts}*\n\n---\n",

        sec_pipeline_summary(data, profile),
        "---\n",
        sec_adoption(data, plots_rel, fmt, profile),
        "---\n",
        sec_usage(data, plots_rel, fmt, profile),
        "---\n",
        sec_temporal(data, plots_rel, fmt, profile),
        "---\n",
        sec_top_repos(data, profile, top_n),
        "---\n",
        sec_pattern_activity(data, plots_rel, fmt, profile),
        "---\n",
        sec_non_detected(data, profile),
        "---\n",
        sec_query_stats(data),
        "---\n",
        sec_pattern_index(profile),
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
    profile,
) -> None:
    console.rule(f"[bold blue]Phase 5: Report — {profile.name}[/]")

    data    = load_data(results_dir)
    missing = [k for k, v in data.items() if v is None]
    if missing:
        console.print(f"  [yellow]Missing (sections skipped):[/] {', '.join(missing)}")
    if not data["repo_scores"]:
        console.print("[red]repo_scores.json missing — run Phase 3 first.[/]")
        return

    plots_dir.mkdir(parents=True, exist_ok=True)
    has_plots = any(plots_dir.iterdir()) if plots_dir.exists() else False
    if refresh_plots or not has_plots:
        console.print("  Regenerating plots…")
        import plot as plot_phase
        plot_phase.run(plots_dir, fmt, dpi, profile=profile)
    else:
        console.print(f"  [dim]Using existing plots (--refresh-plots to regenerate)[/]")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plots_rel = os.path.relpath(plots_dir.resolve(), out_path.parent.resolve()).replace("\\", "/")

    report = build_report(data, plots_rel, fmt, top_n, profile)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    console.print(f"[bold green]Saved:[/] {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python report.py")
    parser.add_argument("--technique",    required=True)
    parser.add_argument("--output",        type=Path, default=None)
    parser.add_argument("--plots-dir",     type=Path, default=None)
    parser.add_argument("--refresh-plots", action="store_true")
    parser.add_argument("--top-repos",     type=int,  default=30)
    parser.add_argument("--format",        choices=["png", "pdf", "svg"], default="png")
    parser.add_argument("--dpi",           type=int,  default=150)
    args = parser.parse_args()

    from config import load_technique
    profile   = load_technique(args.technique)
    out_path  = args.output    or (profile.results_dir / "analysis" / "summary_report.md")
    plots_dir = args.plots_dir or (profile.results_dir / "plots")

    run(
        results_dir   = profile.results_dir,
        out_path      = out_path,
        plots_dir     = plots_dir,
        refresh_plots = args.refresh_plots,
        top_n         = args.top_repos,
        fmt           = args.format,
        dpi           = args.dpi,
        profile       = profile,
    )


if __name__ == "__main__":
    main()
