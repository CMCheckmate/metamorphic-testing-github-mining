"""
Generate dummy example reports with real plots for MT, Fuzzing, and PBT.

Usage:
    python generate_example.py
    python generate_example.py --out-dir my_example_reports

Outputs to:
    example_reports/
        metamorphic_testing/
            analysis/summary_report.md
            plots/*.png
        fuzzing/
            analysis/summary_report.md
            plots/*.png
        property_based_testing/
            analysis/summary_report.md
            plots/*.png
        combined/
            comparative_report.md
            plots/*.png
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

random.seed(42)
np.random.seed(42)


# ---------------------------------------------------------------------------
# Technique definitions
# ---------------------------------------------------------------------------

TECHNIQUES = {
    "metamorphic_testing": {
        "name":       "Metamorphic Testing",
        "short_name": "MT",
        "color":      "#1a6e3c",
        "n_total":    1103,
        "n_detected": 186,
        "top_langs":  [("Python", 0.40), ("Java", 0.20), ("C++", 0.10), ("JavaScript", 0.08),
                       ("C", 0.05), ("Go", 0.04), ("Scala", 0.03), ("C#", 0.03),
                       ("Haskell", 0.02), ("Ruby", 0.02), ("Other", 0.03)],
        "top_domains": [("machine_learning", 0.33), ("scientific", 0.20), ("compiler", 0.15),
                        ("testing_infrastructure", 0.17), ("web", 0.10), ("database", 0.08),
                        ("security", 0.05), ("bioinformatics", 0.04)],
        "project_types": [("general_usage", 0.45), ("research_artifact", 0.23), ("framework", 0.17),
                          ("mixed", 0.12), ("unknown", 0.03)],
        "patterns": [
            {"id": "class_MetamorphicTest",     "label": "Class name: MetamorphicTest"},
            {"id": "class_MetamorphicRelation", "label": "Class name: MetamorphicRelation"},
            {"id": "decorator_metamorphic",     "label": "Decorator: @metamorphic"},
            {"id": "identifier_mr",             "label": "Identifier: metamorphic_relation"},
            {"id": "identifier_mt",             "label": "Identifier: metamorphic_test"},
            {"id": "string_mt_phrase",          "label": "String: metamorphic test/testing"},
            {"id": "string_mr_phrase",          "label": "String: metamorphic relation"},
            {"id": "comment_mt",                "label": "Comment: metamorphic test/testing"},
            {"id": "comment_mr",                "label": "Comment: metamorphic relation"},
            {"id": "abbrev_MT",                 "label": "Abbreviation: MT"},
            {"id": "abbrev_MR",                 "label": "Abbreviation: MR"},
        ],
        "queries": [
            ("repo", "metamorphic testing",    "repo_metamorphic_testing",    8341),
            ("code", "MetamorphicRelation",    "code_MetamorphicRelation",    4112),
            ("code", "metamorphic_relation",   "code_metamorphic_relation",   3887),
            ("commit", "metamorphic testing",  "commit_metamorphic_testing",  3241),
            ("repo", "metamorphic relation",   "repo_metamorphic_relation",   2914),
            ("code", "MetamorphicTest",        "code_MetamorphicTest",        2631),
            ("issue", "metamorphic testing",   "issue_metamorphic_testing",   2418),
            ("commit", "metamorphic relation", "commit_metamorphic_relation", 1987),
            ("code", "@metamorphic",           "code_at_metamorphic",         1743),
            ("pr", "metamorphic testing",      "pr_metamorphic_testing",       987),
        ],
        "score_dist_params": (0.7, 2.5),  # lognormal mu, sigma
        "orgs": ["soarsmu", "gemtest", "icst-research", "jodavimeta", "aerospace-mt",
                 "compiler-testing", "ml-oracle", "nlp-lab-unipi", "se-research",
                 "test-oracle-group", "metamorphic-testing", "bioinf-lab", "db-testing"],
    },
    "fuzzing": {
        "name":       "Fuzzing",
        "short_name": "Fuzzing",
        "color":      "#e65100",
        "n_total":    1850,
        "n_detected": 534,
        "top_langs":  [("C", 0.28), ("C++", 0.24), ("Python", 0.18), ("Go", 0.10),
                       ("Rust", 0.07), ("Java", 0.05), ("JavaScript", 0.04), ("Other", 0.04)],
        "top_domains": [("security", 0.42), ("compiler", 0.24), ("web", 0.16),
                        ("scientific", 0.09), ("testing_infrastructure", 0.18),
                        ("database", 0.11)],
        "project_types": [("general_usage", 0.52), ("framework", 0.15), ("mixed", 0.11),
                          ("research_artifact", 0.18), ("unknown", 0.04)],
        "patterns": [
            {"id": "import_libfuzzer",  "label": "LibFuzzer harness"},
            {"id": "import_atheris",    "label": "Import: atheris"},
            {"id": "afl_fuzz",          "label": "AFL/AFL++ usage"},
            {"id": "cargo_fuzz",        "label": "cargo-fuzz"},
            {"id": "go_fuzz",           "label": "Go native fuzz (testing.F)"},
            {"id": "jazzer",            "label": "Jazzer (Java)"},
            {"id": "oss_fuzz",          "label": "OSS-Fuzz config"},
            {"id": "comment_fuzz",      "label": "Comment: fuzzing/fuzzer"},
            {"id": "string_fuzz",       "label": "String: fuzz/fuzzer"},
            {"id": "identifier_fuzz",   "label": "Identifier: fuzz_/Fuzz"},
        ],
        "queries": [
            ("repo", "fuzzing",         "repo_fuzzing",          15201),
            ("code", "libfuzzer",       "code_libfuzzer",        9843),
            ("code", "LLVMFuzzerTest",  "code_LLVMFuzzer",       7621),
            ("code", "atheris",         "code_atheris",           5234),
            ("commit", "fuzzing",       "commit_fuzzing",         4987),
            ("code", "cargo-fuzz",      "code_cargo_fuzz",        3812),
            ("code", "testing.F",       "code_go_fuzz",           3241),
            ("issue", "fuzzing",        "issue_fuzzing",          4102),
            ("repo", "oss-fuzz",        "repo_oss_fuzz",          2901),
            ("code", "jazzer",          "code_jazzer",            2103),
        ],
        "score_dist_params": (1.1, 2.2),
        "orgs": ["google", "microsoft", "aflteam", "google-oss-fuzz", "fuzzbench",
                 "libfuzzer-sys", "cargo-fuzz", "atheris-corp", "sec-research",
                 "compiler-fuzzing", "protocol-fuzz", "network-sec"],
    },
    "property_based_testing": {
        "name":       "Property-Based Testing",
        "short_name": "PBT",
        "color":      "#1565c0",
        "n_total":    2287,
        "n_detected": 712,
        "top_langs":  [("Python", 0.32), ("Haskell", 0.12), ("Java", 0.14), ("Scala", 0.09),
                       ("JavaScript", 0.08), ("Rust", 0.08), ("C#", 0.06),
                       ("Kotlin", 0.04), ("Ruby", 0.03), ("Other", 0.04)],
        "top_domains": [("testing_infrastructure", 0.30), ("compiler", 0.20), ("database", 0.16),
                        ("scientific", 0.12), ("web", 0.14), ("security", 0.08),
                        ("bioinformatics", 0.06)],
        "project_types": [("general_usage", 0.49), ("framework", 0.20), ("mixed", 0.13),
                          ("research_artifact", 0.14), ("unknown", 0.04)],
        "patterns": [
            {"id": "import_hypothesis",  "label": "Import: hypothesis"},
            {"id": "given_decorator",    "label": "Decorator: @given"},
            {"id": "import_quickcheck",  "label": "Import: QuickCheck"},
            {"id": "import_scalacheck",  "label": "Import: ScalaCheck"},
            {"id": "import_proptest",    "label": "Import: proptest (Rust)"},
            {"id": "import_jqwik",       "label": "Import: jqwik (Java)"},
            {"id": "import_fastcheck",   "label": "Import: fast-check"},
            {"id": "comment_pbt",        "label": "Comment: property-based testing"},
            {"id": "string_pbt",         "label": "String: property-based test"},
            {"id": "identifier_prop",    "label": "Identifier: prop_/Property"},
        ],
        "queries": [
            ("repo", "property-based testing",  "repo_pbt",              12804),
            ("code", "from hypothesis import",  "code_hypothesis_import", 9412),
            ("code", "@given",                  "code_given",             8901),
            ("code", "import QuickCheck",        "code_quickcheck",       6234),
            ("code", "import org.scalacheck",    "code_scalacheck",       4821),
            ("commit", "property-based test",   "commit_pbt",             3912),
            ("code", "proptest",                "code_proptest",          3401),
            ("issue", "property-based testing", "issue_pbt",              3102),
            ("code", "jqwik",                   "code_jqwik",             2743),
            ("code", "fast-check",              "code_fastcheck",         2341),
        ],
        "score_dist_params": (0.9, 2.0),
        "orgs": ["HypothesisWorks", "haskell", "scalatest", "qcheckml", "proptest-rs",
                 "jqwik-team", "dubzzz", "hypothesis-users", "property-testing",
                 "quickcheck-java", "pbt-community", "scala-testing"],
    },
}


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

def _sample_lang(lang_dist, n):
    langs, probs = zip(*lang_dist)
    probs = np.array(probs); probs /= probs.sum()
    return np.random.choice(langs, size=n, p=probs).tolist()


def _sample_domain(domain_dist, n):
    """Each repo gets 0–2 domains drawn from the distribution."""
    all_domains = [d for d, _ in domain_dist]
    probs = np.array([p for _, p in domain_dist]); probs /= probs.sum()
    result = []
    for _ in range(n):
        k = random.randint(0, 2)
        chosen = np.random.choice(all_domains, size=k, p=probs, replace=False).tolist()
        result.append(chosen)
    return result


def _sample_project_type(type_dist, n):
    types, probs = zip(*type_dist)
    probs = np.array(probs); probs /= probs.sum()
    return np.random.choice(types, size=n, p=probs).tolist()


def _lognormal_score(mu, sigma, n):
    raw = np.random.lognormal(mu, sigma, n)
    return np.clip(raw.round().astype(int), 1, 500).tolist()


def _make_monthly_commits(created_year, last_year=2025):
    monthly_total = {}
    monthly_tech  = {}
    year = max(created_year, 2012)
    for y in range(year, last_year + 1):
        for m in range(1, 13):
            key = f"{y}-{m:02d}"
            total = max(0, int(np.random.poisson(8)))
            tech  = max(0, int(np.random.binomial(total, 0.06))) if total > 0 else 0
            if total > 0:
                monthly_total[key] = total
            if tech > 0:
                monthly_tech[key] = tech
    return monthly_total, monthly_tech


def generate_repos(tech_key: str, cfg: dict) -> tuple:
    """Returns (repo_scores, findings, summary_dict)."""
    n_total    = cfg["n_total"]
    n_detected = cfg["n_detected"]
    n_none     = n_total - n_detected
    short      = cfg["short_name"]
    orgs       = cfg["orgs"]

    repos = []
    findings_list = []

    # --- Detected repos ---
    scores = _lognormal_score(*cfg["score_dist_params"], n_detected)
    langs  = _sample_lang(cfg["top_langs"], n_detected)
    ptypes = _sample_project_type(cfg["project_types"], n_detected)
    domains = _sample_domain(cfg["top_domains"], n_detected)
    stars_det = np.random.lognormal(2.5, 1.8, n_detected).astype(int).tolist()

    patterns_all = cfg["patterns"]

    for i in range(n_detected):
        score = scores[i]
        org   = random.choice(orgs)
        repo  = f"{org}/repo-{short.lower()}-{i:04d}"
        year  = random.randint(2012, 2025)
        month = random.randint(1, 12)
        day   = random.randint(1, 28)
        created = f"{year}-{month:02d}-{day:02d}"

        # Distribute score across files
        n_files = max(1, int(np.random.lognormal(0.4, 0.9)))
        n_files = min(n_files, score)
        total_files_scanned = max(n_files, random.randint(10, 300))
        total_lines_scanned = total_files_scanned * random.randint(50, 300)
        technique_lines     = score * random.randint(1, 3)
        file_ratio = n_files / total_files_scanned if total_files_scanned > 0 else 0.0
        line_density = technique_lines / total_lines_scanned if total_lines_scanned > 0 else 0.0
        avg_mentions = score / n_files if n_files > 0 else 0.0
        max_mentions = int(avg_mentions * random.uniform(1.2, 3.0))

        # Artifact breakdown
        ptype = ptypes[i]
        if ptype == "general_usage":
            artifact_breakdown = {"test_code": int(score * 0.75), "source_code": int(score * 0.15),
                                   "documentation": int(score * 0.07), "config": int(score * 0.03)}
        elif ptype == "framework":
            artifact_breakdown = {"source_code": int(score * 0.70), "test_code": int(score * 0.20),
                                   "documentation": int(score * 0.07), "config": int(score * 0.03)}
        elif ptype == "research_artifact":
            artifact_breakdown = {"source_code": int(score * 0.40), "documentation": int(score * 0.35),
                                   "test_code": int(score * 0.20), "config": int(score * 0.05)}
        else:
            artifact_breakdown = {"test_code": int(score * 0.50), "source_code": int(score * 0.35),
                                   "documentation": int(score * 0.10), "config": int(score * 0.05)}
        artifact_breakdown = {k: v for k, v in artifact_breakdown.items() if v > 0}

        # Pick patterns matched
        n_pat = min(len(patterns_all), max(1, int(np.random.lognormal(0.5, 0.8))))
        matched_pats = [p["label"] for p in random.sample(patterns_all, n_pat)]

        # Git commit stats
        total_commits = random.randint(50, 500)
        tech_commits  = max(1, int(total_commits * random.betavariate(1.5, 12)))
        commit_ratio  = tech_commits / total_commits
        span_days     = int(abs(np.random.lognormal(5.0, 1.1)))

        # Generate technique_commit_dates spread across the activity span
        first_year = year
        last_year  = min(year + max(1, int(span_days / 365)), 2025)
        _commit_dates = []
        if tech_commits > 0:
            yr_range = list(range(first_year, last_year + 1))
            for _ in range(tech_commits):
                cy = random.choice(yr_range)
                cm = random.randint(1, 12)
                _commit_dates.append(f"{cy}-{cm:02d}-01")

        # Monthly commits
        monthly_total, monthly_tech = _make_monthly_commits(year)

        # Found by queries
        found_by = [random.choice([q[2] for q in cfg["queries"]]),
                    random.choice([f"repo_{short.lower()}_{j}" for j in range(3)])]

        r = {
            "repo":                          repo,
            "classification":                "strong_explicit" if score >= 3 else "weak_explicit",
            "score":                         score,
            "direct_matches":                score,
            "stars":                         int(stars_det[i]),
            "language":                      langs[i],
            "created_at":                    created,
            "technique_files":               n_files,
            "technique_lines":               technique_lines,
            "total_files_scanned":           total_files_scanned,
            "total_lines_scanned":           total_lines_scanned,
            "technique_file_ratio":          round(file_ratio, 4),
            "technique_line_density":        round(line_density, 5),
            "avg_mentions_per_technique_file": round(avg_mentions, 2),
            "max_mentions_in_file":          max_mentions,
            "patterns_matched":              matched_pats,
            "project_type":                  ptype,
            "artifact_breakdown":            artifact_breakdown,
            "inferred_domains":              domains[i],
            "contributor_count_git":         max(1, int(np.random.lognormal(0.8, 1.0))),
            "total_commits_sampled":         total_commits,
            "technique_commits_count":       tech_commits,
            "technique_commit_ratio":        round(commit_ratio, 4),
            "first_technique_commit_date":   created,
            "last_technique_commit_date":    f"{min(year + int(span_days/365)+1, 2025)}-01-01",
            "technique_commit_span_days":    span_days,
            "technique_commit_dates":        _commit_dates,
            "monthly_total_commits":         monthly_total,
            "monthly_technique_commits":     monthly_tech,
            "found_by_queries":              found_by,
        }
        repos.append(r)

        # Generate findings entries for this repo
        _LANG_EXT = {
            "Python": ".py", "Java": ".java", "C++": ".cpp", "C": ".c",
            "JavaScript": ".js", "TypeScript": ".ts", "Go": ".go", "Rust": ".rs",
            "Scala": ".scala", "C#": ".cs", "Haskell": ".hs", "Ruby": ".rb", "Kotlin": ".kt",
        }
        _DOC_EXTS    = [".md", ".rst", ".txt"]
        _CONFIG_EXTS = [".yml", ".toml", ".ini", ".gradle", "Makefile"]
        dirs = {"test_code": "tests", "source_code": "src", "documentation": "docs", "config": "."}
        src_ext = _LANG_EXT.get(langs[i], ".py")
        for atype, cnt in artifact_breakdown.items():
            fdir = dirs.get(atype, "src")
            n_art_files = max(1, int(cnt / max(avg_mentions, 1)))
            for fi in range(n_art_files):
                if atype == "documentation":
                    ext   = random.choice(_DOC_EXTS)
                    fname = f"{fdir}/README{ext}" if fi == 0 else f"{fdir}/doc_{fi}{ext}"
                elif atype == "config":
                    cfg_name = random.choice(_CONFIG_EXTS)
                    fname    = f"{fdir}/{cfg_name}" if cfg_name == "Makefile" else f"{fdir}/config_{fi}{cfg_name}"
                elif atype == "test_code":
                    fname = f"{fdir}/test_{fi}{src_ext}"
                else:
                    fname = f"{fdir}/module_{fi}{src_ext}"
                pat_label = random.choice(matched_pats)
                for li in range(max(1, cnt // n_art_files)):
                    findings_list.append({
                        "repo":          repo,
                        "file":          fname,
                        "label":         pat_label,
                        "line":          random.randint(1, 200),
                        "artifact_type": atype,
                    })

    # --- Not-detected repos ---
    langs_none   = _sample_lang(cfg["top_langs"], n_none)
    stars_none   = np.random.lognormal(1.5, 1.5, n_none).astype(int).tolist()
    surfaces_none = ["repo", "issue", "commit", "pr"]
    for i in range(n_none):
        org  = random.choice(orgs + [f"user-{random.randint(1000,9999)}"])
        repo = f"{org}/repo-nodet-{i:04d}"
        year = random.randint(2010, 2025)
        repos.append({
            "repo":               repo,
            "classification":     "none",
            "score":              0,
            "direct_matches":     0,
            "stars":              int(stars_none[i]),
            "language":           langs_none[i],
            "created_at":         f"{year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "technique_files":    0,
            "technique_lines":    0,
            "total_files_scanned": random.randint(5, 200),
            "total_lines_scanned": random.randint(200, 20000),
            "technique_file_ratio": 0.0,
            "technique_line_density": 0.0,
            "avg_mentions_per_technique_file": 0.0,
            "max_mentions_in_file": 0,
            "patterns_matched":   [],
            "project_type":       "unknown",
            "artifact_breakdown": {},
            "inferred_domains":   [],
            "contributor_count_git": max(1, int(np.random.poisson(2))),
            "total_commits_sampled": 0,
            "technique_commits_count": 0,
            "technique_commit_ratio": 0.0,
            "technique_commit_span_days": 0,
            "technique_commit_dates": [],
            "monthly_total_commits": {},
            "monthly_technique_commits": {},
            "found_by_queries":   [f"{random.choice(surfaces_none)}_{short.lower()}_{i % 5}"],
        })

    # Summary
    summary = {
        "queries": [
            {"type": qtype, "query": qtext, "label": qlabel, "hits": qhits}
            for qtype, qtext, qlabel, qhits in cfg["queries"]
        ]
    }

    return repos, findings_list, summary


# ---------------------------------------------------------------------------
# Mock profile
# ---------------------------------------------------------------------------

def make_profile(tech_key: str, cfg: dict, results_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        name                  = cfg["name"],
        short_name            = cfg["short_name"],
        slug                  = tech_key,
        color                 = cfg["color"],
        results_dir           = results_dir,
        report_intro          = "",
        extra_report_sections = [],
        classification_strong = 3,
        classification_weak   = 1,
        patterns_raw          = cfg["patterns"],
        commit_keywords       = [],
        domain_keywords       = {},
    )


# ---------------------------------------------------------------------------
# Write data files
# ---------------------------------------------------------------------------

def write_data(out_dir: Path, repos, findings, summary):
    (out_dir / "analysis").mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    (out_dir / "cloned").mkdir(parents=True, exist_ok=True)
    (out_dir / "plots").mkdir(parents=True, exist_ok=True)

    with open(out_dir / "analysis" / "repo_scores.json", "w") as f:
        json.dump(repos, f)
    with open(out_dir / "analysis" / "findings.json", "w") as f:
        json.dump(findings, f)
    with open(out_dir / "raw" / "summary.json", "w") as f:
        json.dump(summary, f)

    # Minimal manifest so the funnel doesn't error
    manifest = {
        "repos": {
            r["repo"]: {"status": "cloned"} for r in repos
        }
    }
    with open(out_dir / "cloned" / "manifest.json", "w") as f:
        json.dump(manifest, f)

    # All repos in search results (raw)
    repos_raw = [{"full_name": r["repo"]} for r in repos]
    with open(out_dir / "raw" / "repos.json", "w") as f:
        json.dump(repos_raw, f)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate example reports with real plots")
    parser.add_argument("--out-dir", type=Path, default=BASE_DIR / "example_reports")
    parser.add_argument("--dpi",     type=int, default=130)
    parser.add_argument("--format",  choices=["png", "pdf", "svg"], default="png")
    args = parser.parse_args()

    out_root = args.out_dir.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"Output root: {out_root}")

    import plot as plot_mod
    import report as report_mod

    for tech_key, cfg in TECHNIQUES.items():
        print(f"\n{'='*60}")
        print(f"  Generating: {cfg['name']}")
        print(f"{'='*60}")

        results_dir = out_root / tech_key
        plots_dir   = results_dir / "plots"
        out_report  = results_dir / "analysis" / "summary_report.md"

        # Generate & write data
        repos, findings, summary = generate_repos(tech_key, cfg)
        write_data(results_dir, repos, findings, summary)
        print(f"  Data: {len(repos)} repos, {len(findings)} findings")

        # Create mock profile
        profile = make_profile(tech_key, cfg, results_dir)

        # Generate plots
        print("  Generating plots…")
        plot_mod.run(plots_dir, args.format, args.dpi, profile=profile)

        # Generate report
        print("  Generating report…")
        data      = report_mod.load_data(results_dir)
        plots_rel = os.path.relpath(plots_dir.resolve(), out_report.parent.resolve()).replace("\\", "/")
        report_text = report_mod.build_report(data, plots_rel, args.format, 30, profile)
        out_report.parent.mkdir(parents=True, exist_ok=True)
        with open(out_report, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"  Report saved: {out_report}")

    # Combined report
    print(f"\n{'='*60}")
    print(f"  Generating: Combined Report (MT + Fuzzing + PBT)")
    print(f"{'='*60}")

    import combine as combine_mod
    combined_plots = out_root / "combined" / "plots"
    combined_out   = out_root / "combined" / "comparative_report.md"

    # Temporarily point combine.py at our example_reports/ directory
    original_results = combine_mod.RESULTS_DIR
    combine_mod.RESULTS_DIR = out_root

    techniques = combine_mod.discover_techniques(out_root)
    if techniques:
        print(f"  Found: {[t['short_name'] for t in techniques]}")
        combined_plots.mkdir(parents=True, exist_ok=True)

        # Adoption (RQ1)
        combine_mod.plot_adoption_rates(        techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_detection_depth(       techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_contributor_comparison(techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_technique_ratios(      techniques, combined_plots, args.format, args.dpi)

        # Usage (RQ2)
        combine_mod.plot_language_comparison(        techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_project_type_comparison(    techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_test_structure_comb(        techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_artifact_comparison(        techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_extension_comparison(       techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_domain_comparison(          techniques, combined_plots, args.format, args.dpi)

        # Timeline (RQ3)
        combine_mod.plot_yearly_trend(               techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_technique_commit_timeline_comb(techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_commit_first_last(          techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_commit_span(                techniques, combined_plots, args.format, args.dpi)
        combine_mod.plot_commit_ratio(               techniques, combined_plots, args.format, args.dpi)

        combined_out.parent.mkdir(parents=True, exist_ok=True)
        plots_rel = os.path.relpath(combined_plots.resolve(), combined_out.parent.resolve()).replace("\\", "/")
        report_text = combine_mod.build_report(techniques, plots_rel, args.format)
        with open(combined_out, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"  Combined report saved: {combined_out}")
    else:
        print("  [WARN] No techniques discovered for combined report")

    combine_mod.RESULTS_DIR = original_results

    print(f"\n{'='*60}")
    print(f"  Done. Example reports in: {out_root}")
    print(f"  Individual:  {out_root}/{{technique}}/analysis/summary_report.md")
    print(f"  Combined:    {out_root}/combined/comparative_report.md")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
