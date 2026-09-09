"""
Analysis Orchestrator
=====================
Runs code_analysis and non_code_analysis, optionally in parallel,
then aggregates all results into overall.json.

Modes:
  default     — code + non-code in parallel
  --code-only — code analysis only
  --noncode-only — non-code analysis only
  --restart   — reset all analysis data and history before running

Overall.json is the single source of truth for the report phase.
The report performs NO calculations — it reads stored values only.
"""

from __future__ import annotations

import concurrent.futures
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import config as cfg
from utils import (
    resolve_technique, technique_dirs, ensure_dirs,
    setup_logging, load_json, save_json, descriptive_stats,
)


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _aggregate_code(results: list[dict]) -> dict:
    if not results:
        return {}

    # Per-repo stats
    specific_hits_per_repo = [r.get("scan", {}).get("total_specific_hits", 0) for r in results]
    general_hits_per_repo  = [r.get("scan", {}).get("total_general_hits",  0) for r in results]
    files_per_repo         = [r.get("scan", {}).get("total_files",         0) for r in results]
    hit_files_per_repo     = [r.get("scan", {}).get("total_hit_files",     0) for r in results]
    lines_per_repo         = [r.get("scan", {}).get("total_lines",         0) for r in results]
    hit_lines_per_repo     = [r.get("scan", {}).get("total_hit_lines",     0) for r in results]

    # Contributor count (stars used as proxy; real contributor data requires API call)
    stars = [r.get("stars") for r in results if r.get("stars") is not None]

    # Classification breakdown
    classifications: Counter = Counter()
    for r in results:
        for cls in r.get("classification", {}).get("classifications", []):
            classifications[cls] += 1

    # Language distribution
    lang_counts: Counter = Counter()
    for r in results:
        lang = r.get("language")
        if lang:
            lang_counts[lang] += 1
        for lang2, cnt in r.get("scan", {}).get("language_distribution", {}).items():
            if cnt > 0:
                lang_counts[lang2] += 1

    # File category breakdown (aggregated)
    cat_totals: dict[str, dict] = {}
    for cat in ["test_code", "source_code", "docs", "config", "other"]:
        total_files = 0
        hit_files   = 0
        total_lines = 0
        hit_lines   = 0
        gen_hits    = 0
        spec_hits   = 0
        for r in results:
            bc = r.get("scan", {}).get("by_category", {}).get(cat, {})
            total_files += bc.get("file_count", 0)
            hit_files   += bc.get("hit_file_count", 0)
            total_lines += bc.get("total_lines", 0)
            hit_lines   += bc.get("hit_line_count", 0)
            gen_hits    += bc.get("total_general_hits", 0)
            spec_hits   += bc.get("total_specific_hits", 0)
        cat_totals[cat] = {
            "total_files":         total_files,
            "hit_file_count":      hit_files,
            "total_lines":         total_lines,
            "hit_line_count":      hit_lines,
            "total_general_hits":  gen_hits,
            "total_specific_hits": spec_hits,
            "hit_file_pct":        round(hit_files / max(total_files, 1) * 100, 1),
            "hit_line_pct":        round(hit_lines / max(total_lines, 1) * 100, 1),
        }

    # Keyword hits aggregated
    kw_totals: dict[str, dict] = {}
    for r in results:
        for kw_id, kw_data in r.get("scan", {}).get("hits_by_keyword", {}).items():
            entry = kw_totals.setdefault(kw_id, {"count": 0, "label": ""})
            entry["count"] += kw_data.get("count", 0) if isinstance(kw_data, dict) else kw_data
            if isinstance(kw_data, dict) and not entry["label"]:
                entry["label"] = kw_data.get("label", kw_id)

    kw_ranked = sorted(kw_totals.items(), key=lambda x: x[1]["count"], reverse=True)

    # Timeline aggregation
    commits_by_month: Counter = Counter()
    tech_commits_by_month: Counter = Counter()
    creation_years: Counter = Counter()
    commit_spans: list[float] = []

    for r in results:
        commits = r.get("commits", {})
        for month, cnt in commits.get("commits_by_month", {}).items():
            commits_by_month[month] += cnt
        for month, cnt in commits.get("technique_commits_by_month", {}).items():
            tech_commits_by_month[month] += cnt
        created = r.get("created_at", "")
        if created and len(created) >= 4:
            try:
                creation_years[int(created[:4])] += 1
            except ValueError:
                pass
        span = commits.get("commit_span_days")
        if span is not None and span >= 0:
            commit_spans.append(float(span))

    # Density bands (per-repo specific hits)
    density_bands_hits: dict[str, int] = _density_bands(specific_hits_per_repo)
    density_bands_pct:  dict[str, int] = _density_bands_pct(
        [r.get("scan", {}).get("total_specific_hits", 0) / max(r.get("scan", {}).get("total_lines", 1), 1) * 100
         for r in results]
    )

    return {
        "repo_count": len(results),
        "specific_hits_per_repo": descriptive_stats(specific_hits_per_repo),
        "general_hits_per_repo":  descriptive_stats(general_hits_per_repo),
        "files_per_repo":         descriptive_stats(files_per_repo),
        "hit_files_per_repo":     descriptive_stats(hit_files_per_repo),
        "lines_per_repo":         descriptive_stats(lines_per_repo),
        "hit_lines_per_repo":     descriptive_stats(hit_lines_per_repo),
        "stars_stats":            descriptive_stats([float(s) for s in stars]),
        "classification_counts":  dict(classifications),
        "language_distribution":  dict(lang_counts.most_common(30)),
        "by_category":            cat_totals,
        "keywords_ranked":        [
            {"id": kid, "label": v["label"], "count": v["count"]}
            for kid, v in kw_ranked
        ],
        "timeline": {
            "creation_years":          dict(sorted(creation_years.items())),
            "commits_by_month":        dict(sorted(commits_by_month.items())),
            "technique_commits_by_month": dict(sorted(tech_commits_by_month.items())),
            "commit_span_stats":       descriptive_stats(commit_spans),
            "repos_by_commit_span":    _span_bands(commit_spans),
        },
        "density_bands_hits": density_bands_hits,
        "density_bands_pct":  density_bands_pct,
    }


def _aggregate_noncode(results: list[dict]) -> dict:
    if not results:
        return {}

    by_surface: dict[str, list] = defaultdict(list)
    for r in results:
        by_surface[r["surface"]].append(r)

    surface_stats = {}
    for surface, items in by_surface.items():
        spec_hits = [i.get("total_specific_hits", 0) for i in items]
        surface_stats[surface] = {
            "count":                  len(items),
            "total_specific_hits":    sum(spec_hits),
            "specific_hits_per_item": descriptive_stats(spec_hits),
        }

    # Keyword hits across all non-code items
    kw_counts: Counter = Counter()
    for r in results:
        for label, cnt in r.get("hits_by_keyword", {}).items():
            kw_counts[label] += cnt

    # Domain distribution
    domain_counts: Counter = Counter()
    for r in results:
        for d in r.get("domains", []):
            domain_counts[d] += 1

    # Word frequency for word cloud
    word_freq: Counter = Counter()
    for r in results:
        for w, cnt in r.get("word_freq", {}).items():
            word_freq[w] += cnt

    # Language distribution (repos surface)
    lang_counts: Counter = Counter()
    for r in by_surface.get("repos", []):
        lang = r.get("language")
        if lang:
            lang_counts[lang] += 1

    return {
        "total_items":      len(results),
        "by_surface":       surface_stats,
        "keywords_ranked":  dict(kw_counts.most_common(cfg.REPORT_TOP_N_KEYWORDS)),
        "domain_counts":    dict(domain_counts.most_common()),
        "top_word_freq":    dict(word_freq.most_common(200)),
        "language_distribution": dict(lang_counts.most_common(30)),
    }


def _aggregate_search_summary(search_dir: Path) -> dict:
    summary_path = search_dir / "summary.json"
    summary = load_json(summary_path, {})
    if not summary:
        return {}
    result = {}
    for surface, data in summary.items():
        if isinstance(data, dict):
            result[surface] = {
                "api_hit_count":  data.get("api_hit_count", 0),
                "unique_results": data.get("unique_results", 0),
            }

    # Keyword hit distribution across all surfaces
    all_kw_hits: Counter = Counter()
    for surface, data in summary.items():
        if isinstance(data, dict):
            for kw, kw_data in data.get("keywords", {}).items():
                if isinstance(kw_data, dict):
                    all_kw_hits[kw] += kw_data.get("unique_results", 0)

    result["keywords_total"] = dict(all_kw_hits.most_common())
    return result


def _aggregate_repo_sizes(search_dir: Path) -> dict:
    repos_file = search_dir / "repos.json"
    code_file  = search_dir / "code.json"
    sizes_all: list[float] = []
    sizes_by_surface: dict[str, list[float]] = defaultdict(list)

    for surface, path in [("repos", repos_file), ("code", code_file)]:
        items = load_json(path, [])
        for item in items:
            kb = item.get("size_kb", 0) or 0
            if kb > 0:
                sizes_all.append(float(kb))
                sizes_by_surface[surface].append(float(kb))

    return {
        "overall": descriptive_stats(sizes_all),
        "by_surface": {s: descriptive_stats(v) for s, v in sizes_by_surface.items()},
    }


def _density_bands(values: list[float]) -> dict[str, int]:
    bands = {"0": 0, "1-9": 0, "10-49": 0, "50-199": 0, "200+": 0}
    for v in values:
        if v == 0:
            bands["0"] += 1
        elif v < 10:
            bands["1-9"] += 1
        elif v < 50:
            bands["10-49"] += 1
        elif v < 200:
            bands["50-199"] += 1
        else:
            bands["200+"] += 1
    return bands


def _density_bands_pct(values: list[float]) -> dict[str, int]:
    bands = {"0%": 0, "<1%": 0, "1-5%": 0, "5-20%": 0, ">20%": 0}
    for v in values:
        if v == 0:
            bands["0%"] += 1
        elif v < 1:
            bands["<1%"] += 1
        elif v < 5:
            bands["1-5%"] += 1
        elif v <= 20:
            bands["5-20%"] += 1
        else:
            bands[">20%"] += 1
    return bands


def _span_bands(spans: list[float]) -> dict[str, int]:
    bands = {"<30d": 0, "30-180d": 0, "180d-1yr": 0, "1-3yr": 0, ">3yr": 0}
    for s in spans:
        if s < 30:
            bands["<30d"] += 1
        elif s < 180:
            bands["30-180d"] += 1
        elif s < 365:
            bands["180d-1yr"] += 1
        elif s < 1095:
            bands["1-3yr"] += 1
        else:
            bands[">3yr"] += 1
    return bands


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(
    slug: str,
    code_only: bool = False,
    noncode_only: bool = False,
    restart: bool = False,
    workers: int = cfg.ANALYSIS_WORKERS,
) -> None:
    ensure_dirs(slug)
    dirs = technique_dirs(slug)
    logger = setup_logging(slug, "analysis")

    import code_analysis
    import non_code_analysis

    if not noncode_only and not code_only:
        # Run both in parallel
        logger.info("Running code and non-code analysis in parallel")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            code_fut    = pool.submit(code_analysis.run, slug, restart, workers)
            noncode_fut = pool.submit(non_code_analysis.run, slug, restart)
            concurrent.futures.wait([code_fut, noncode_fut])
            for fut in [code_fut, noncode_fut]:
                exc = fut.exception()
                if exc:
                    logger.error(f"Analysis worker error: {exc}", exc_info=True)
    elif code_only:
        code_analysis.run(slug, restart, workers)
    else:
        non_code_analysis.run(slug, restart)

    # Aggregate into overall.json
    logger.info("Aggregating results into overall.json")
    _aggregate_overall(slug, dirs, logger)


def _aggregate_overall(slug: str, dirs: dict, logger) -> None:
    code_repos_path  = dirs["analysis"] / "code_repos.json"
    noncode_path     = dirs["analysis"] / "noncode_results.json"

    code_repos: list[dict]   = load_json(code_repos_path, [])
    noncode_results: list[dict] = load_json(noncode_path, [])

    code_agg   = _aggregate_code(code_repos)
    noncode_agg = _aggregate_noncode(noncode_results)
    search_agg  = _aggregate_search_summary(dirs["search"])
    size_agg    = _aggregate_repo_sizes(dirs["search"])

    # Total unique repos found across all surfaces
    all_repo_names: set[str] = set()
    for surface in ["code", "repos", "commits", "prs", "issues", "discussions"]:
        items = load_json(dirs["search"] / f"{surface}.json", [])
        for item in items:
            rn = item.get("repo_full_name", "")
            if rn:
                all_repo_names.add(rn)

    overall = {
        "slug":              slug,
        "repos_found_total": len(all_repo_names),
        "repos_by_surface":  {
            s: len({i.get("repo_full_name", "") for i in load_json(dirs["search"] / f"{s}.json", [])
                    if i.get("repo_full_name")})
            for s in ["code", "repos", "commits", "prs", "issues", "discussions"]
        },
        "repo_size_stats":   size_agg,
        "search_summary":    search_agg,
        "code_analysis":     code_agg,
        "noncode_analysis":  noncode_agg,
    }

    save_json(dirs["analysis"] / "overall.json", overall)
    logger.info("overall.json written")
    print(f"\nAggregation complete. overall.json saved.")
