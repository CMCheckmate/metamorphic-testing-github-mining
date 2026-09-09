"""
Generate realistic dummy data for all search and analysis result files.
Used for development and testing without a live GitHub token.

Usage:
  python generate_example_data.py --technique mt
  python generate_example_data.py --technique all
"""

from __future__ import annotations

import argparse
import random
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config as cfg
from utils import resolve_technique, technique_dirs, ensure_dirs, save_json, load_analysis_keywords

random.seed(42)

FAKE_ORGS = [
    "google", "microsoft", "apache", "mozilla", "facebook", "netflix",
    "airbnb", "uber", "shopify", "stripe", "elastic", "hashicorp",
    "university-test-lab", "research-artifact", "academic-proj",
]
FAKE_LANGS = ["Python", "Java", "TypeScript", "Go", "Rust", "Scala",
              "C++", "C", "Ruby", "Kotlin", "Haskell", "Erlang"]
FAKE_TOPICS = [
    "testing", "fuzzing", "security", "machine-learning", "compiler",
    "database", "web", "api", "open-source", "research",
]
FAKE_CLASSIFS = ["actual_usage", "framework", "research_artifact"]

MT_KEYWORDS  = ["metamorphic testing", "metamorphic relation", "MetamorphicTest"]
PBT_KEYWORDS = ["property-based testing", "import hypothesis", "forAll"]
FUZZ_KEYWORDS = ["LLVMFuzzerTestOneInput", "fuzz testing", "coverage-guided fuzzing"]

TECH_KEYWORDS = {
    "metamorphic_testing":    MT_KEYWORDS,
    "fuzz_testing":           FUZZ_KEYWORDS,
    "property_based_testing": PBT_KEYWORDS,
}


def _rand_date(start_year: int = 2015, end_year: int = 2024) -> str:
    start = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    end   = datetime(end_year, 12, 31, tzinfo=timezone.utc)
    return (start + timedelta(seconds=random.randint(0, int((end - start).total_seconds())))).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rand_repo_name(slug: str) -> str:
    org  = random.choice(FAKE_ORGS)
    name = random.choice([
        "testing-framework", "test-utils", "fuzzer", "property-tests",
        "mt-examples", "metamorphic-lib", "fuzz-harness", "pbt-demo",
        "research-artifact", "study-replication",
    ])
    return f"{org}/{name}-{random.randint(1, 99)}"


def _make_code_items(slug: str, n: int = 30) -> list[dict]:
    kws = TECH_KEYWORDS.get(slug, MT_KEYWORDS)
    items = []
    for i in range(n):
        repo = _rand_repo_name(slug)
        kw   = random.choice(kws)
        items.append({
            "id":             f"sha_{i:06d}",
            "url":            f"https://api.github.com/repos/{repo}/contents/test_{i}.py",
            "html_url":       f"https://github.com/{repo}/blob/main/test_{i}.py",
            "surface":        "code",
            "file_path":      f"tests/test_{i}.py",
            "repo_id":        100000 + i,
            "repo_full_name": repo,
            "repo_html_url":  f"https://github.com/{repo}",
            "repo_clone_url": f"https://github.com/{repo}.git",
            "language":       random.choice(FAKE_LANGS),
            "stars":          random.randint(0, 5000),
            "matched_keyword": kw,
            "created_at":     _rand_date(),
            "size_kb":        random.randint(100, 50000),
        })
    return items


def _make_repo_items(slug: str, n: int = 40) -> list[dict]:
    kws = TECH_KEYWORDS.get(slug, MT_KEYWORDS)
    items = []
    for i in range(n):
        repo = _rand_repo_name(slug)
        kw   = random.choice(kws)
        items.append({
            "id":             200000 + i,
            "url":            f"https://api.github.com/repos/{repo}",
            "html_url":       f"https://github.com/{repo}",
            "surface":        "repos",
            "repo_id":        200000 + i,
            "repo_full_name": repo,
            "repo_clone_url": f"https://github.com/{repo}.git",
            "title":          repo.split("/")[1],
            "body":           f"A repository demonstrating {kw} in {random.choice(FAKE_LANGS)}.",
            "stars":          random.randint(0, 10000),
            "language":       random.choice(FAKE_LANGS),
            "topics":         random.sample(FAKE_TOPICS, k=random.randint(1, 4)),
            "created_at":     _rand_date(),
            "updated_at":     _rand_date(2022, 2024),
            "size_kb":        random.randint(50, 200000),
            "is_fork":        random.random() < 0.1,
            "matched_keyword": kw,
        })
    return items


def _make_issue_items(slug: str, surface: str, n: int = 20) -> list[dict]:
    kws = TECH_KEYWORDS.get(slug, MT_KEYWORDS)
    items = []
    for i in range(n):
        repo = _rand_repo_name(slug)
        kw   = random.choice(kws)
        items.append({
            "id":             300000 + i + (10000 if surface == "prs" else 0),
            "number":         i + 1,
            "url":            f"https://api.github.com/repos/{repo}/issues/{i+1}",
            "html_url":       f"https://github.com/{repo}/issues/{i+1}",
            "surface":        surface,
            "title":          f"Improve {kw} coverage in module {i}",
            "body":           f"We should add more {kw} to cover edge cases.\n\nSee also: {kw} docs.",
            "state":          random.choice(["open", "closed"]),
            "comment_count":  random.randint(0, 30),
            "created_at":     _rand_date(),
            "updated_at":     _rand_date(2022, 2024),
            "repo_full_name": repo,
            "matched_keyword": kw,
        })
    return items


def _make_commit_items(slug: str, n: int = 25) -> list[dict]:
    kws = TECH_KEYWORDS.get(slug, MT_KEYWORDS)
    items = []
    for i in range(n):
        repo = _rand_repo_name(slug)
        kw   = random.choice(kws)
        items.append({
            "id":             f"commit_sha_{i:06d}",
            "url":            f"https://api.github.com/repos/{repo}/commits/abc{i:04d}",
            "html_url":       f"https://github.com/{repo}/commit/abc{i:04d}",
            "surface":        "commits",
            "body":           f"Add {kw} for {random.choice(['sort', 'search', 'encode', 'hash'])} function",
            "created_at":     _rand_date(),
            "repo_full_name": repo,
            "repo_id":        400000 + i,
            "matched_keyword": kw,
        })
    return items


def _make_discussion_items(slug: str, n: int = 10) -> list[dict]:
    kws = TECH_KEYWORDS.get(slug, MT_KEYWORDS)
    items = []
    for i in range(n):
        repo = _rand_repo_name(slug)
        kw   = random.choice(kws)
        items.append({
            "id":             f"disc_{i:06d}",
            "number":         i + 1,
            "url":            f"https://github.com/{repo}/discussions/{i+1}",
            "html_url":       f"https://github.com/{repo}/discussions/{i+1}",
            "surface":        "discussions",
            "title":          f"Best practices for {kw}?",
            "body":           f"How do you implement {kw} in large codebases? Looking for examples.",
            "comment_count":  random.randint(1, 15),
            "created_at":     _rand_date(),
            "updated_at":     _rand_date(2022, 2024),
            "repo_full_name": repo,
            "matched_keyword": kw,
        })
    return items


def _make_code_repo_record(slug: str, i: int) -> dict:
    repo_name = _rand_repo_name(slug)
    cls = random.choices(FAKE_CLASSIFS, weights=[0.6, 0.25, 0.15])[0]
    lang = random.choice(FAKE_LANGS)
    stars = random.randint(0, 5000)
    created_at = _rand_date()
    n_files = random.randint(20, 500)
    n_hit_files = random.randint(1, max(1, n_files // 3))
    n_lines = random.randint(1000, 100000)
    n_hit_lines = random.randint(5, max(5, n_lines // 20))
    specific_hits = random.randint(3, 200)
    general_hits  = random.randint(specific_hits, specific_hits * 5)

    by_category = {
        cat: {
            "file_count":         random.randint(0, 50),
            "hit_file_count":     random.randint(0, 10),
            "total_lines":        random.randint(0, 20000),
            "hit_line_count":     random.randint(0, 100),
            "total_general_hits": random.randint(0, 200),
            "total_specific_hits":random.randint(0, 50),
            "hit_file_pct":       round(random.uniform(0, 40), 1),
            "hit_line_pct":       round(random.uniform(0, 10), 1),
        }
        for cat in ["test_code", "source_code", "docs", "config", "other"]
    }

    n_commits = random.randint(10, 2000)
    tech_commits = random.randint(1, max(1, n_commits // 5))
    first_dt = _rand_date(2015, 2020)
    last_dt  = _rand_date(2021, 2024)
    span_days = random.randint(30, 3000)

    return {
        "full_name":   repo_name,
        "html_url":    f"https://github.com/{repo_name}",
        "stars":       stars,
        "language":    lang,
        "description": f"Example project using {'metamorphic' if 'mt' in slug else 'fuzz' if 'fuzz' in slug else 'property-based'} testing.",
        "topics":      random.sample(FAKE_TOPICS, k=random.randint(1, 4)),
        "created_at":  created_at,
        "size_kb":     random.randint(50, 50000),
        "scan": {
            "total_files":        n_files,
            "total_hit_files":    n_hit_files,
            "total_lines":        n_lines,
            "total_hit_lines":    n_hit_lines,
            "total_general_hits": general_hits,
            "total_specific_hits":specific_hits,
            "by_category":        by_category,
            "hits_by_keyword":    {
                "phrase_mt":  {"count": random.randint(0, 30), "label": "metamorphic test(ing)"},
                "class_mt":   {"count": random.randint(0, 20), "label": "class MetamorphicTest"},
                "abbrev_MT":  {"count": random.randint(0, 50), "label": "abbreviation MT"},
            },
            "language_distribution": {lang: n_files},
        },
        "commits": {
            "total_commits":          n_commits,
            "technique_commits":      tech_commits,
            "first_commit_date":      first_dt,
            "last_commit_date":       last_dt,
            "commit_span_days":       span_days,
            "avg_commit_interval_days": round(span_days / max(n_commits - 1, 1), 2),
            "commits_by_month":       {f"202{random.randint(0,4)}-{random.randint(1,12):02d}": random.randint(1, 30)
                                       for _ in range(random.randint(3, 12))},
            "technique_commits_by_month": {},
        },
        "classification": {
            "classifications": [cls],
            "signals":         [f"signal_{random.randint(1,5)}"],
            "scores":          {"research": random.randint(0, 5), "framework": random.randint(0, 3), "usage": random.randint(0, 3)},
        },
        "domains": random.sample(list(cfg.DOMAIN_KEYWORDS.keys()), k=random.randint(0, 3)),
        "readme_snippet": f"This project implements {cls} for testing.",
    }


def _make_noncode_results(slug: str, n: int = 80) -> list[dict]:
    surfaces = ["repos", "commits", "prs", "issues", "discussions"]
    kws = TECH_KEYWORDS.get(slug, MT_KEYWORDS)
    results = []
    for i in range(n):
        surface = surfaces[i % len(surfaces)]
        kw = random.choice(kws)
        results.append({
            "id":                  f"{surface}_{i:06d}",
            "surface":             surface,
            "url":                 f"https://github.com/example/repo/issues/{i}",
            "html_url":            f"https://github.com/example/repo/issues/{i}",
            "title":               f"Discussion about {kw} in project {i}",
            "repo_full_name":      _rand_repo_name(slug),
            "created_at":         _rand_date(),
            "updated_at":         _rand_date(2022, 2024),
            "stars":              random.randint(0, 5000) if surface == "repos" else None,
            "language":           random.choice(FAKE_LANGS) if surface == "repos" else None,
            "topics":             random.sample(FAKE_TOPICS, 2) if surface == "repos" else [],
            "matched_keyword":    kw,
            "total_general_hits": random.randint(0, 10),
            "total_specific_hits":random.randint(0, 5),
            "hits_by_keyword":    {kw: random.randint(1, 5)},
            "domains":            random.sample(["machine_learning", "web", "security"], k=random.randint(0, 2)),
            "word_freq":          {"testing": random.randint(1, 20), "property": random.randint(0, 10)},
        })
    return results


def _make_summary(slug: str) -> dict:
    surfaces = ["code", "repos", "issues", "prs", "commits", "discussions"]
    kws = TECH_KEYWORDS.get(slug, MT_KEYWORDS)
    summary = {}
    for surface in surfaces:
        api_hits    = random.randint(50, 2000)
        unique      = int(api_hits * random.uniform(0.5, 0.95))
        kw_data = {}
        for kw in kws:
            k_hits   = random.randint(0, unique // len(kws))
            k_unique = int(k_hits * random.uniform(0.6, 1.0))
            kw_data[kw] = {"api_hit_count": k_hits, "unique_results": k_unique}
        summary[surface] = {
            "api_hit_count":  api_hits,
            "unique_results": unique,
            "keywords":       kw_data,
        }
    return summary


def generate(slug: str) -> None:
    ensure_dirs(slug)
    dirs = technique_dirs(slug)

    print(f"Generating example data for {slug}...")

    # Search data
    save_json(dirs["search"] / "code.json",        _make_code_items(slug, 30))
    save_json(dirs["search"] / "repos.json",       _make_repo_items(slug, 40))
    save_json(dirs["search"] / "issues.json",      _make_issue_items(slug, "issues", 20))
    save_json(dirs["search"] / "prs.json",         _make_issue_items(slug, "prs", 15))
    save_json(dirs["search"] / "commits.json",     _make_commit_items(slug, 25))
    save_json(dirs["search"] / "discussions.json", _make_discussion_items(slug, 10))
    save_json(dirs["search"] / "summary.json",     _make_summary(slug))

    kws_done = {kw: "done" for kw in TECH_KEYWORDS.get(slug, MT_KEYWORDS)}
    save_json(dirs["search"] / "search_history.json", kws_done)

    # Analysis data — code repos
    code_repos = [_make_code_repo_record(slug, i) for i in range(20)]
    save_json(dirs["analysis"] / "code_repos.json", code_repos)

    history = {r["full_name"]: "done" for r in code_repos}
    save_json(dirs["analysis"] / "code_history.json", history)

    # Analysis data — non-code
    noncode = _make_noncode_results(slug, 80)
    save_json(dirs["analysis"] / "noncode_results.json", noncode)
    save_json(dirs["analysis"] / "noncode_history.json",
              [f"{r['surface']}:{r['id']}" for r in noncode])

    print(f"  Search, code, and non-code data written.")

    # Overall aggregation
    from analysis import _aggregate_code, _aggregate_noncode, _aggregate_search_summary, _aggregate_repo_sizes
    code_agg    = _aggregate_code(code_repos)
    nc_agg      = _aggregate_noncode(noncode)
    search_agg  = _aggregate_search_summary(dirs["search"])
    size_agg    = _aggregate_repo_sizes(dirs["search"])

    all_repos: set[str] = set()
    for surface in ["code", "repos", "commits", "prs", "issues", "discussions"]:
        items_file = dirs["search"] / f"{surface}.json"
        from utils import load_json
        for item in load_json(items_file, []):
            rn = item.get("repo_full_name", "")
            if rn:
                all_repos.add(rn)

    overall = {
        "slug":              slug,
        "repos_found_total": len(all_repos),
        "repos_by_surface": {
            s: len({i.get("repo_full_name", "")
                    for i in load_json(dirs["search"] / f"{s}.json", [])
                    if i.get("repo_full_name")})
            for s in ["code", "repos", "commits", "prs", "issues", "discussions"]
        },
        "repo_size_stats":  size_agg,
        "search_summary":   search_agg,
        "code_analysis":    code_agg,
        "noncode_analysis": nc_agg,
    }
    save_json(dirs["analysis"] / "overall.json", overall)
    print(f"  overall.json written.")

    # Generate the report
    import report
    report.run(slug)
    print(f"  Report generated.")
    print(f"Done for {slug}.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate example pipeline data.")
    parser.add_argument("--technique", default="mt",
                        help="mt, fuzz, pbt, or 'all' (default: mt)")
    args = parser.parse_args()

    if args.technique == "all":
        for slug in ["metamorphic_testing", "fuzz_testing", "property_based_testing"]:
            generate(slug)
    else:
        from utils import resolve_technique
        slug = resolve_technique(args.technique)
        generate(slug)


if __name__ == "__main__":
    main()
