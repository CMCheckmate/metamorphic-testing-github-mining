"""
Analysis Orchestrator
=====================
Runs code_analysis and non_code_analysis, optionally in parallel,
then aggregates all results into overall.json.

Overall.json is the single source of truth for the report phase.
The report performs NO calculations — it reads stored values only.
"""

from __future__ import annotations

import concurrent.futures
from collections import Counter, defaultdict
from pathlib import Path

from core_helpers import config as cfg
from core_helpers.utils import (
    resolve_technique, technique_dirs, ensure_dirs,
    setup_logging, load_json, save_json, descriptive_stats,
    load_analysis_keywords,
)


# ---------------------------------------------------------------------------
# Word-cloud custom stopwords (applied at aggregation, not collection)
# ---------------------------------------------------------------------------

def _load_custom_stopwords() -> frozenset[str]:
    return frozenset({
        # --- URL / domain fragments ---
        "com", "org", "net", "github", "http", "https", "www", "html",
        "blob", "tree", "main", "master", "refs", "head", "raw", "git",

        # --- Generic dev/repo noise ---
        "repo", "repos", "repository", "repositories",
        "issue", "issues", "pull", "request", "requests",
        "commit", "commits", "branch", "branches",
        "merge", "merged", "release", "releases",
        "build", "built", "update", "updated", "change", "changes",
        "file", "files", "line", "lines", "path", "paths",
        "version", "feature", "support", "implement", "implementation",
        "function", "method", "class", "module", "package",
        "import", "return", "value", "type", "string", "object",
        "true", "false", "none", "null", "bool", "int", "str",
        "var", "val", "arg", "param", "config", "option", "default",
        "data", "result", "output", "input", "user", "name", "number",
        "project", "work", "step", "note", "example", "open", "close",

        # --- 3-letter words not caught by built-in STOPWORDS ---
        "add", "new", "one", "run", "per", "now", "non",
        "set", "use", "via", "end", "pre", "self", "key",
        "two", "three", "zero", "pass", "full", "real",
        "make", "read", "end", "let", "got", "ago",
        "way", "yes", "yet", "old", "put", "say", "see",
        "top", "sub", "pro", "ref", "src", "tmp", "log",
        "bit", "big", "cut", "due", "far", "hit", "low",

        # --- Generic English verbs ---
        "every", "first", "still", "must", "never", "rather",
        "instead", "already", "without", "across", "based",
        "existing", "exactly", "check", "checks", "source",
        "added", "adds", "runs", "passed", "used", "using",
        "generated", "verified", "closed", "missing", "required",
        "including", "exact", "clean", "single", "current",
        "local", "cross", "plus", "level", "order", "time",
        "case", "cases", "target", "results", "runtime", "core",
        "scope", "context", "found", "review",

        # --- Process / documentation noise ---
        "summary", "plan", "design", "docs", "report",
        "code", "authored",

        # --- Platform / CI noise ---
        "noreply",

        # --- Reference / generic nouns ---
        "reference", "identity", "production", "integration",
        "execution", "harness", "surface", "schema",
        "agent", "agents", "decision", "rule", "field", "point",
        "text", "list", "dict", "args", "docs", "spec",

        # --- Common English words absent from wordcloud built-in STOPWORDS ---
        "may", "back", "high", "create", "entry", "remain", "remains",
        "small", "future", "notes", "root", "round", "need", "needs",
        "follow", "whole", "types", "section", "workflow", "findings",
        "artifact", "external", "explicitly", "candidate", "records",
        "process",

        # --- Domain-agnostic testing vocabulary ---
        "coverage", "validation", "suite", "failure", "failures",
        "regression", "behavior", "verification", "independent",
        "evidence", "unit", "verify", "expected", "stable",
        "valid", "explicit", "analysis", "tool", "comparison",
        "evaluation", "quality", "research", "tdd",

        # --- Confirmed high-frequency noise ---
        "four", "second",
        "feat", "silently", "audit", "status", "documented",
        "different", "complete", "correct", "live", "changed",
        "specific", "known", "free", "shared", "final", "nothing",
        "green",
        "uses", "fails", "passes", "makes", "keep", "call", "calls",
        "claim", "claims",
        "json", "multi", "separate", "wrong", "table", "record",
        "next", "mode", "gap", "phase", "documentation",
        "block", "public", "content", "names", "base", "reports",
        "count", "will",

        # --- Basic dev vocab (high freq, no domain signal) ---
        "fix", "fixed", "fixes", "bug",
        "error", "errors", "values",
        "fail", "failed",

        # --- Generic code-level terms ---
        "empty", "layer", "dependency",
        "written", "write", "returns", "requires", "exists",
        "include", "checked", "removed", "named", "adding",
        "made", "measured", "recorded", "whether",

        # --- Generic nouns ---
        "loop", "post", "document", "problem", "cost", "part",
        "row", "form", "hand", "task", "comment", "total",
        "side", "readme", "metadata", "index", "counts",
        "examples", "features",

        # --- Generic adjectives / adverbs ---
        "directly", "inside", "start", "actually", "within",
        "stays", "whose", "five", "even", "actual", "distinct",
        "independently", "deliberately", "hard", "finding",
        "closes", "done", "want", "fine", "good", "things",
        "working", "show", "help", "much", "know",

        # --- Platform noise ---
        "pinned", "session", "agentic", "worktree",

        # --- AI model / tool names ---
        "opus", "sonnet", "gpt", "chatgpt", "gemini", "openai",
        "copilot", "coderabbit",

        # --- Geology contamination (metamorphic rocks repos) ---
        "sedimentary", "igneous", "geology", "rocks",

        # --- Generic language tooling ---
        "ruff", "clippy", "mypy", "cargo",
    })


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _aggregate_code(results: list[dict]) -> dict:
    if not results:
        return {}

    specific_hits_per_repo = [r.get("scan", {}).get("total_specific_hits", 0) for r in results]
    general_hits_per_repo  = [r.get("scan", {}).get("total_general_hits",  0) for r in results]
    files_per_repo         = [r.get("scan", {}).get("total_files",         0) for r in results]
    hit_files_per_repo     = [r.get("scan", {}).get("total_hit_files",     0) for r in results]
    lines_per_repo         = [r.get("scan", {}).get("total_lines",         0) for r in results]
    hit_lines_per_repo     = [r.get("scan", {}).get("total_hit_lines",     0) for r in results]
    stars = [r.get("stars") for r in results if r.get("stars") is not None]

    classifications: Counter = Counter()
    for r in results:
        for cls in r.get("classification", {}).get("classifications", []):
            classifications[cls] += 1

    lang_counts: Counter = Counter()
    for r in results:
        lang = r.get("language")
        if lang:
            lang_counts[lang] += 1
        for lang2, cnt in r.get("scan", {}).get("language_distribution", {}).items():
            if cnt > 0:
                lang_counts[lang2] += 1

    # File category breakdown
    cat_totals: dict[str, dict] = {}
    for cat in ["test_code", "source_code", "docs", "config", "other"]:
        total_files = hit_files = total_lines = hit_lines = gen_hits = spec_hits = 0
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

    all_files_total = sum(v["total_files"] for v in cat_totals.values())
    all_lines_total = sum(v["total_lines"] for v in cat_totals.values())
    for cat, stats in cat_totals.items():
        stats["pct_of_all_files"] = round(stats["total_files"] / max(all_files_total, 1) * 100, 1)
        stats["pct_of_all_lines"] = round(stats["total_lines"] / max(all_lines_total, 1) * 100, 1)

    # Keyword hits aggregated
    kw_totals: dict[str, dict] = {}
    for r in results:
        for kw_id, kw_data in r.get("scan", {}).get("hits_by_keyword", {}).items():
            entry = kw_totals.setdefault(kw_id, {"count": 0, "label": "", "category": ""})
            entry["count"] += kw_data.get("count", 0) if isinstance(kw_data, dict) else kw_data
            if isinstance(kw_data, dict) and not entry["label"]:
                entry["label"]    = kw_data.get("label", kw_id)
                entry["category"] = kw_data.get("category", "")

    kw_ranked = sorted(kw_totals.items(), key=lambda x: x[1]["count"], reverse=True)

    # Per-keyword, per-file-category breakdown (from file_details)
    kw_by_cat: dict[str, dict[str, int]] = {}
    kw_labels_map: dict[str, str] = {}
    for r in results:
        scan = r.get("scan", {})
        for fdr in scan.get("file_details", []):
            cat = fdr.get("category", "other")
            for kw_id, cnt in fdr.get("specific_hits", {}).items():
                if kw_id not in kw_by_cat:
                    kw_by_cat[kw_id] = {"test_code": 0, "source_code": 0, "docs": 0, "config": 0, "other": 0}
                kw_by_cat[kw_id][cat] = kw_by_cat[kw_id].get(cat, 0) + cnt
        for kw_id, kw_data in scan.get("hits_by_keyword", {}).items():
            if isinstance(kw_data, dict) and kw_id not in kw_labels_map:
                kw_labels_map[kw_id] = kw_data.get("label", kw_id)

    keywords_by_category = sorted(
        [
            {
                "id":               kw_id,
                "label":            kw_labels_map.get(kw_id, kw_id),
                "total_count":      sum(cats.values()),
                "hits_test_code":   cats.get("test_code", 0),
                "hits_source_code": cats.get("source_code", 0),
                "hits_docs":        cats.get("docs", 0),
                "hits_config":      cats.get("config", 0),
                "hits_other":       cats.get("other", 0),
            }
            for kw_id, cats in kw_by_cat.items()
        ],
        key=lambda x: x["total_count"], reverse=True,
    )

    # Test vs non-test stats
    test_cat = cat_totals.get("test_code", {})
    nontest_files     = sum(cat_totals.get(c, {}).get("total_files",         0) for c in ["source_code", "docs", "config", "other"])
    nontest_lines     = sum(cat_totals.get(c, {}).get("total_lines",         0) for c in ["source_code", "docs", "config", "other"])
    nontest_spec      = sum(cat_totals.get(c, {}).get("total_specific_hits", 0) for c in ["source_code", "docs", "config", "other"])
    nontest_gen       = sum(cat_totals.get(c, {}).get("total_general_hits",  0) for c in ["source_code", "docs", "config", "other"])
    nontest_hit_files = sum(cat_totals.get(c, {}).get("hit_file_count",      0) for c in ["source_code", "docs", "config", "other"])
    nontest_hit_lines = sum(cat_totals.get(c, {}).get("hit_line_count",      0) for c in ["source_code", "docs", "config", "other"])
    test_vs_nontest_stats = {
        "test_code": {
            "files":            test_cat.get("total_files", 0),
            "lines":            test_cat.get("total_lines", 0),
            "specific_hits":    test_cat.get("total_specific_hits", 0),
            "general_hits":     test_cat.get("total_general_hits", 0),
            "pct_of_all_files": test_cat.get("pct_of_all_files", 0),
            "pct_of_all_lines": test_cat.get("pct_of_all_lines", 0),
            "hit_file_pct":     test_cat.get("hit_file_pct", 0),
            "hit_line_pct":     test_cat.get("hit_line_pct", 0),
        },
        "non_test_code": {
            "files":            nontest_files,
            "lines":            nontest_lines,
            "specific_hits":    nontest_spec,
            "general_hits":     nontest_gen,
            "hit_files":        nontest_hit_files,
            "hit_lines":        nontest_hit_lines,
            "pct_of_all_files": round(nontest_files     / max(all_files_total, 1) * 100, 1),
            "pct_of_all_lines": round(nontest_lines     / max(all_lines_total, 1) * 100, 1),
            "hit_file_pct":     round(nontest_hit_files / max(nontest_files, 1) * 100, 1),
            "hit_line_pct":     round(nontest_hit_lines / max(nontest_lines, 1) * 100, 1),
        },
        "total_files": all_files_total,
        "total_lines": all_lines_total,
    }

    # Per-repo hit-% distribution (for exact ranked line charts)
    hit_pct_distribution = sorted(
        [
            {
                "name":          r.get("full_name") or r.get("repo_full_name", ""),
                "specific_hits": r.get("scan", {}).get("total_specific_hits", 0),
                "total_lines":   r.get("scan", {}).get("total_lines", 0),
                "total_files":   r.get("scan", {}).get("total_files", 0),
                "hit_pct_lines": round(r.get("scan", {}).get("total_hit_lines", 0) / max(r.get("scan", {}).get("total_lines", 1), 1) * 100, 2),
                "hit_pct_files": round(r.get("scan", {}).get("total_hit_files", 0) / max(r.get("scan", {}).get("total_files", 1), 1) * 100, 2),
            }
            for r in results
        ],
        key=lambda x: x["hit_pct_lines"], reverse=True,
    )

    specific_hits_ranked = sorted(
        [{
            "name":         r.get("full_name") or r.get("repo_full_name", ""),
            "hits":         r.get("scan", {}).get("total_specific_hits", 0),
            "hit_file_pct": round(r.get("scan", {}).get("total_hit_files", 0) / max(r.get("scan", {}).get("total_files",  1), 1) * 100, 1),
            "hit_line_pct": round(r.get("scan", {}).get("total_hit_lines", 0) / max(r.get("scan", {}).get("total_lines",  1), 1) * 100, 1),
        } for r in results],
        key=lambda x: x["hits"], reverse=True,
    )

    # Technique Commit Spans — avg interval between consecutive technique commits
    commit_spans: list[float] = []
    commit_spans_sorted: list[dict] = []
    commit_spans_excluded = 0
    for r in results:
        name = r.get("full_name") or r.get("repo_full_name", "")
        commits = r.get("commits", {})
        span = commits.get("technique_commit_span_avg_days")
        if span is None:
            span = commits.get("commit_span_days")  # backward compat with older code_repos.json
        if span is not None and span >= 0:
            commit_spans.append(float(span))
            commit_spans_sorted.append({"name": name, "span_days": float(span)})
        else:
            commit_spans_excluded += 1
    commit_spans_sorted.sort(key=lambda x: x["span_days"], reverse=True)

    # Timeline
    commits_by_month: Counter = Counter()
    tech_commits_by_month: Counter = Counter()
    creation_years: Counter = Counter()
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

    # Technique density labels (10-label scheme) + artifact classification — from file_details
    #
    # File class is derived from `fdr["category"]`:
    #   code   = test_code | source_code
    #   doc    = docs
    #   config = config
    #   other  = other
    #
    # Hit type:
    #   technique = total_specific > 0
    #   test      = total_general > 0, total_specific == 0
    #   non_hit   = no hits
    #
    # Label matrix (4 types × 3 hit states):
    #   technique_code, technique_doc, technique_config, technique_other  (4)
    #   test_code,      test_doc,      test_config,      test_other       (4)
    #   non_hit_code, non_hit_doc, non_hit_config, non_hit_other          (4)
    _TD_LABELS = [
        "technique_code",   "technique_doc",   "technique_config",   "technique_other",
        "test_code",        "test_doc",        "test_config",        "test_other",
        "non_hit_code",     "non_hit_doc",     "non_hit_config",     "non_hit_other",
    ]
    td_global: dict[str, dict] = {lbl: {"files": 0, "lines": 0, "hit_lines": 0, "gen_hits": 0, "spec_hits": 0, "hit_files": 0}
                                   for lbl in _TD_LABELS}
    td_per_repo: dict[str, list[dict]] = {lbl: [] for lbl in _TD_LABELS}
    art_ext_counts: Counter = Counter()
    art_cat_counts = {"code": 0, "docs": 0, "config": 0, "other": 0}
    technique_ext_counts: Counter = Counter()
    technique_lang_repo: list[set] = []  # one set per repo, contains languages of technique files
    has_file_details = False

    _BINARY_EXTS = {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".ico", ".webp",
        ".mp4", ".mp3", ".wav", ".ogg", ".pdf", ".ttf", ".woff", ".woff2",
        ".eot", ".zip", ".tar", ".gz", ".exe", ".bin", ".dll", ".so",
        ".class", ".pyc", ".pyo", ".o", ".a", ".lib", ".pdb",
    }
    _EXT_TO_LANG: dict[str, str] = {
        ".py": "Python", ".pyw": "Python",
        ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
        ".ts": "TypeScript", ".tsx": "TypeScript",
        ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
        ".scala": "Scala", ".sc": "Scala",
        ".go": "Go",
        ".rs": "Rust",
        ".c": "C", ".h": "C",
        ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
        ".cs": "C#",
        ".rb": "Ruby",
        ".php": "PHP",
        ".swift": "Swift",
        ".m": "Objective-C",
        ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
        ".r": "R", ".R": "R",
        ".jl": "Julia",
        ".hs": "Haskell",
        ".ex": "Elixir", ".exs": "Elixir",
        ".erl": "Erlang", ".hrl": "Erlang",
        ".ml": "OCaml", ".mli": "OCaml",
        ".clj": "Clojure", ".cljs": "Clojure",
        ".lua": "Lua",
        ".pl": "Perl", ".pm": "Perl",
        ".dart": "Dart",
        ".f90": "Fortran", ".f95": "Fortran", ".f": "Fortran",
    }

    # Spec definition: Usage = ≥1 code file (test or source) with a technique hit;
    # Non-Usage = ≥1 technique hit, but none in a code file; no_hit = no technique hit
    # anywhere (GitHub search matches our regexes do not confirm — investigated separately).
    _GRP = ["non_usage", "usage", "no_hit"]
    _repo_group: dict[str, str] = {}
    for _r in results:
        _bc = _r.get("scan", {}).get("by_category", {})
        _code_hit_files = (_bc.get("test_code",   {}).get("hit_file_count", 0) +
                           _bc.get("source_code", {}).get("hit_file_count", 0))
        _rn = _r.get("full_name") or _r.get("repo_full_name", "")
        if _code_hit_files > 0:
            _repo_group[_rn] = "usage"
        elif _r.get("scan", {}).get("total_specific_hits", 0) > 0:
            _repo_group[_rn] = "non_usage"
        else:
            _repo_group[_rn] = "no_hit"

    td_global_grp   = {g: {lbl: {"files": 0, "lines": 0, "hit_lines": 0,
                                  "gen_hits": 0, "spec_hits": 0, "hit_files": 0}
                             for lbl in _TD_LABELS} for g in _GRP}
    td_per_repo_grp = {g: {lbl: [] for lbl in _TD_LABELS} for g in _GRP}

    for r in results:
        file_details = r.get("scan", {}).get("file_details", [])
        if not file_details:
            continue
        has_file_details = True
        repo_td: dict[str, dict] = {lbl: {"files": 0, "lines": 0, "hit_lines": 0, "gen_hits": 0, "spec_hits": 0, "hit_files": 0}
                                     for lbl in _TD_LABELS}
        repo_tech_langs: set[str] = set()

        for fdr in file_details:
            cat      = fdr.get("category", "other")
            is_code  = cat in {"test_code", "source_code"}
            is_doc   = cat == "docs"
            is_cfg   = cat == "config"
            has_spec = fdr.get("total_specific", 0) > 0
            has_gen  = fdr.get("total_general",  0) > 0

            if has_spec:
                if is_code:   lbl = "technique_code"
                elif is_doc:  lbl = "technique_doc"
                elif is_cfg:  lbl = "technique_config"
                else:         lbl = "technique_other"
            elif has_gen:
                if is_code:   lbl = "test_code"
                elif is_doc:  lbl = "test_doc"
                elif is_cfg:  lbl = "test_config"
                else:         lbl = "test_other"
            else:
                if is_code:     lbl = "non_hit_code"
                elif is_doc:    lbl = "non_hit_doc"
                elif is_cfg:    lbl = "non_hit_config"
                else:           lbl = "non_hit_other"

            nl = fdr.get("n_lines", 0)
            hl = fdr.get("n_hit_lines", 0)
            gh = fdr.get("total_general", 0)
            sh = fdr.get("total_specific", 0)
            is_hit = (gh > 0 or sh > 0)
            for d in (repo_td[lbl], td_global[lbl]):
                d["files"]     += 1
                d["lines"]     += nl
                d["hit_lines"] += hl
                d["gen_hits"]  += gh
                d["spec_hits"] += sh
                if is_hit:
                    d["hit_files"] += 1

            # Artifact classification by extension (all files)
            ext = Path(fdr.get("rel_path", fdr.get("path", "x"))).suffix.lower()
            art_ext_counts[ext] += 1
            if ext in cfg.CODE_EXTENSIONS:     art_cat_counts["code"]   += 1
            elif ext in cfg.DOC_EXTENSIONS:    art_cat_counts["docs"]   += 1
            elif ext in cfg.CONFIG_EXTENSIONS: art_cat_counts["config"] += 1
            else:                              art_cat_counts["other"]  += 1

            # Technique-file extension + language (skip binary/image)
            if has_spec and ext not in _BINARY_EXTS:
                technique_ext_counts[ext] += 1
                lang = _EXT_TO_LANG.get(ext)
                if lang:
                    repo_tech_langs.add(lang)

        for lbl, rs in repo_td.items():
            td_per_repo[lbl].append(rs)
        technique_lang_repo.append(repo_tech_langs)

        _grp_key = _repo_group.get(r.get("full_name") or r.get("repo_full_name", ""), "non_usage")
        for lbl in _TD_LABELS:
            for k, v in repo_td[lbl].items():
                td_global_grp[_grp_key][lbl][k] += v
            td_per_repo_grp[_grp_key][lbl].append(repo_td[lbl])

    if has_file_details:
        total_td_files = sum(v["files"] for v in td_global.values())
        total_td_lines = sum(v["lines"] for v in td_global.values())
        n_rp = len(td_per_repo[_TD_LABELS[0]]) if (_TD_LABELS and td_per_repo) else 0
        if n_rp:
            _rp_totalf = [sum(td_per_repo[l][i]["files"] for l in _TD_LABELS) for i in range(n_rp)]
            _rp_totall = [sum(td_per_repo[l][i]["lines"] for l in _TD_LABELS) for i in range(n_rp)]
            _td_avg = {
                lbl: {
                    "pct_files":       round(sum(td_per_repo[lbl][i]["files"] / max(_rp_totalf[i], 1) for i in range(n_rp)) / n_rp * 100, 1),
                    "pct_lines":       round(sum(td_per_repo[lbl][i]["lines"] / max(_rp_totall[i], 1) for i in range(n_rp)) / n_rp * 100, 1),
                    "hit_line_pct":    round(
                        sum(td_per_repo[lbl][i]["hit_lines"] / td_per_repo[lbl][i]["lines"]
                            for i in range(n_rp) if td_per_repo[lbl][i]["lines"] > 0) /
                        max(sum(1 for i in range(n_rp) if td_per_repo[lbl][i]["lines"] > 0), 1) * 100, 1),
                    "repos_with_files": sum(1 for i in range(n_rp) if td_per_repo[lbl][i]["files"] > 0),
                }
                for lbl in _TD_LABELS
            }
        else:
            _td_avg = {lbl: {"pct_files": 0.0, "pct_lines": 0.0, "hit_line_pct": 0.0, "repos_with_files": 0} for lbl in _TD_LABELS}

        _CAT_GROUPS = {
            "code":   ["technique_code",   "test_code",   "non_hit_code"],
            "doc":    ["technique_doc",    "test_doc",    "non_hit_doc"],
            "config": ["technique_config", "test_config", "non_hit_config"],
            "other":  ["technique_other",  "test_other",  "non_hit_other"],
        }
        _td_within_cat: dict[str, float] = {}
        for cat_lbls in _CAT_GROUPS.values():
            for lbl in cat_lbls:
                _td_within_cat[lbl] = round(
                    sum(
                        td_per_repo[lbl][i]["files"] /
                        max(sum(td_per_repo[l][i]["files"] for l in cat_lbls), 1)
                        for i in range(n_rp)
                    ) / max(n_rp, 1) * 100, 1) if n_rp else 0.0

        technique_density_labels = {
            "by_label": {
                lbl: {
                    "files":            td_global[lbl]["files"],
                    "hit_files":        td_global[lbl]["hit_files"],
                    "lines":            td_global[lbl]["lines"],
                    "gen_hits":         td_global[lbl]["gen_hits"],
                    "spec_hits":        td_global[lbl]["spec_hits"],
                    "pct_files":        _td_avg[lbl]["pct_files"],
                    "pct_lines":        _td_avg[lbl]["pct_lines"],
                    "hit_line_pct":     _td_avg[lbl]["hit_line_pct"],
                    "pct_within_cat":   _td_within_cat.get(lbl, 0.0),
                    "repos_with_files": _td_avg[lbl]["repos_with_files"],
                    "files_per_repo":   descriptive_stats([r["files"]    for r in td_per_repo[lbl]]),
                    "lines_per_repo":   descriptive_stats([r["lines"]    for r in td_per_repo[lbl]]),
                    "gen_per_repo":     descriptive_stats([r["gen_hits"] for r in td_per_repo[lbl]]),
                    "spec_per_repo":    descriptive_stats([r["spec_hits"] for r in td_per_repo[lbl]]),
                }
                for lbl in _TD_LABELS
            },
            "total_files": total_td_files,
            "total_lines": total_td_lines,
            "repos_total": n_rp,
        }

        def _grp_density(g: str) -> dict:
            rp = td_per_repo_grp[g]
            n  = len(rp[_TD_LABELS[0]])
            if n == 0:
                return {"count": 0, "by_label": {}, "avg_hit_file_pct": 0.0,
                        "avg_hit_line_pct": 0.0, "bucket_avgs": {}}

            totf = [sum(rp[l][i]["files"] for l in _TD_LABELS) for i in range(n)]
            totl = [sum(rp[l][i]["lines"] for l in _TD_LABELS) for i in range(n)]

            def _excl_avg(vals_fn, denom_fn):
                pairs = [(vals_fn(i), denom_fn(i)) for i in range(n) if denom_fn(i) > 0]
                return round(sum(v / d for v, d in pairs) / max(len(pairs), 1) * 100, 1)

            avg_lbl = {
                lbl: {
                    "pct_files":    round(sum(rp[lbl][i]["files"] / max(totf[i], 1) for i in range(n)) / n * 100, 1),
                    "pct_lines":    round(sum(rp[lbl][i]["lines"] / max(totl[i], 1) for i in range(n)) / n * 100, 1),
                    "hit_line_pct": _excl_avg(lambda i, l=lbl: rp[l][i]["hit_lines"],
                                              lambda i, l=lbl: rp[l][i]["lines"]),
                }
                for lbl in _TD_LABELS
            }
            wcat: dict[str, float] = {}
            for cat_lbls in _CAT_GROUPS.values():
                for lbl in cat_lbls:
                    wcat[lbl] = round(
                        sum(rp[lbl][i]["files"] /
                            max(sum(rp[l][i]["files"] for l in cat_lbls), 1)
                            for i in range(n)) / n * 100, 1)

            by_lbl = {
                lbl: {
                    "files":          td_global_grp[g][lbl]["files"],
                    "hit_files":      td_global_grp[g][lbl]["hit_files"],
                    "lines":          td_global_grp[g][lbl]["lines"],
                    "gen_hits":       td_global_grp[g][lbl]["gen_hits"],
                    "spec_hits":      td_global_grp[g][lbl]["spec_hits"],
                    "pct_files":      avg_lbl[lbl]["pct_files"],
                    "pct_lines":      avg_lbl[lbl]["pct_lines"],
                    "hit_line_pct":   avg_lbl[lbl]["hit_line_pct"],
                    "pct_within_cat": wcat.get(lbl, 0.0),
                }
                for lbl in _TD_LABELS
            }

            grp_results = [r for r in results
                           if _repo_group.get(r.get("full_name") or r.get("repo_full_name", ""), "non_usage") == g]
            a_l, b_l, c_l, d_l, hf_l, hl_l = [], [], [], [], [], []
            bk = ["test_hit", "test_nohit", "nontest_hit", "nontest_nohit"]
            for r in grp_results:
                sc = r.get("scan", {})
                bc = sc.get("by_category", {})
                nf = max(sc.get("total_files", 0), 1)
                nl = max(sc.get("total_lines", 0), 1)
                hf_l.append(sc.get("total_hit_files", 0) / nf * 100)
                hl_l.append(sc.get("total_hit_lines", 0) / nl * 100)
                if g != "usage":
                    bk = ["doc_hit", "doc_nohit", "nondoc_hit", "nondoc_nohit"]
                    a = bc.get("docs", {}).get("hit_file_count", 0)
                    b = bc.get("docs", {}).get("file_count", 0) - a
                    c = sum(bc.get(cat, {}).get("hit_file_count", 0) for cat in ["config", "other"])
                    d = sum(bc.get(cat, {}).get("file_count", 0) - bc.get(cat, {}).get("hit_file_count", 0) for cat in ["config", "other"])
                else:
                    bk = ["test_hit", "test_nohit", "nontest_hit", "nontest_nohit"]
                    a = bc.get("test_code",   {}).get("hit_file_count", 0)
                    b = bc.get("test_code",   {}).get("file_count", 0) - a
                    c = bc.get("source_code", {}).get("hit_file_count", 0)
                    d = bc.get("source_code", {}).get("file_count", 0) - c
                tot = max(a + b + c + d, 1)
                a_l.append(a / tot * 100); b_l.append(b / tot * 100)
                c_l.append(c / tot * 100); d_l.append(d / tot * 100)

            def _avg(lst): return round(sum(lst) / max(len(lst), 1), 1)
            return {
                "count":            n,
                "avg_hit_file_pct": _avg(hf_l),
                "avg_hit_line_pct": _avg(hl_l),
                "bucket_avgs":      dict(zip(bk, [_avg(a_l), _avg(b_l), _avg(c_l), _avg(d_l)])),
                "by_label":         by_lbl,
            }

        group_density = {g: _grp_density(g) for g in _GRP}

        # Compact per-repo table so report.py never re-reads the >1 GB code_repos.json
        # (whose stored categories are pre-repair).
        repo_table = []
        for r in results:
            sc = r.get("scan", {})
            bc = sc.get("by_category", {})
            nf, nl = max(sc.get("total_files", 0), 1), max(sc.get("total_lines", 0), 1)
            cm = r.get("commits", {})
            repo_table.append({
                "full_name":     r.get("full_name", ""),
                "stars":         r.get("stars"),
                "language":      r.get("language"),
                "group":         _repo_group.get(r.get("full_name", ""), "non_usage"),
                "total_files":   sc.get("total_files", 0),
                "code_files":    bc.get("test_code", {}).get("file_count", 0) + bc.get("source_code", {}).get("file_count", 0),
                "doc_files":     bc.get("docs", {}).get("file_count", 0),
                "specific_hits": sc.get("total_specific_hits", 0),
                "hit_file_pct":  round(sc.get("total_hit_files", 0) / nf * 100, 2),
                "hit_line_pct":  round(sc.get("total_hit_lines", 0) / nl * 100, 2),
                "technique_span_days": cm.get("technique_commit_span_avg_days", cm.get("commit_span_days")),
                "classification":    r.get("classification", {}).get("classifications", []),
            })
        repo_table.sort(key=lambda x: x["specific_hits"], reverse=True)
        total_art_files = sum(art_cat_counts.values())
        artifact_classification = {
            "by_category":     art_cat_counts,
            "by_category_pct": {k: round(v / max(total_art_files, 1) * 100, 1) for k, v in art_cat_counts.items()},
            "by_extension":    dict(art_ext_counts.most_common(60)),
            "total_files":     total_art_files,
        }
        # Extension + language distributions scoped to technique files only (Item 27, 28)
        tech_lang_counter: Counter = Counter()
        for repo_langs in technique_lang_repo:
            for lang in repo_langs:
                tech_lang_counter[lang] += 1
        technique_file_stats = {
            "ext_counts":           dict(technique_ext_counts.most_common(60)),
            "lang_distribution":    dict(tech_lang_counter.most_common(30)),
            "total_technique_files": sum(technique_ext_counts.values()),
        }
    else:
        technique_density_labels = {}
        artifact_classification  = {}
        technique_file_stats     = {}
        group_density            = {}
        repo_table               = []


    return {
        "repo_count":               len(results),
        "specific_hits_per_repo":   descriptive_stats(specific_hits_per_repo),
        "general_hits_per_repo":    descriptive_stats(general_hits_per_repo),
        "files_per_repo":           descriptive_stats(files_per_repo),
        "hit_files_per_repo":       descriptive_stats(hit_files_per_repo),
        "lines_per_repo":           descriptive_stats(lines_per_repo),
        "hit_lines_per_repo":       descriptive_stats(hit_lines_per_repo),
        "stars_stats":              descriptive_stats([float(s) for s in stars]),
        "classification_counts":    dict(classifications),
        "repo_table":               repo_table,
        "language_distribution":    dict(lang_counts.most_common(30)),
        "by_category":              cat_totals,
        "keywords_ranked":          [
            {"id": kid, "label": v["label"], "count": v["count"], "category": v.get("category", "")}
            for kid, v in kw_ranked
        ],
        "keywords_by_category":       keywords_by_category,
        "test_vs_nontest_stats":      test_vs_nontest_stats,
        "hit_pct_distribution":       hit_pct_distribution,
        "specific_hits_ranked":       specific_hits_ranked,
        "commit_spans_sorted":        commit_spans_sorted,
        "technique_density_labels":   technique_density_labels,
        "group_density":              group_density,
        "artifact_classification":    artifact_classification,
        "technique_file_stats":       technique_file_stats,
        "timeline": {
            "creation_years":             dict(sorted(creation_years.items())),
            "commits_by_month":           dict(sorted(commits_by_month.items())),
            "technique_commits_by_month": dict(sorted(tech_commits_by_month.items())),
            "commit_span_stats":          descriptive_stats(commit_spans),
            "commit_span_excluded_count": commit_spans_excluded,
        },
    }


def _aggregate_noncode(results: list[dict], code_repos: list[dict] | None = None) -> dict:
    _code_repos_for_wordcloud = code_repos or []
    if not results:
        return {}

    by_surface: dict[str, list] = defaultdict(list)
    for r in results:
        by_surface[r["surface"]].append(r)

    surface_stats = {}
    for surface, items in by_surface.items():
        spec_hits = [i.get("total_specific_hits", 0) for i in items]
        hits_ranked = sorted(
            [{"id": str(i.get("id", "")), "title": str(i.get("title", ""))[:80], "hit_count": i.get("total_specific_hits", 0)}
             for i in items],
            key=lambda x: x["hit_count"], reverse=True,
        )[:200]
        surf_kw: Counter = Counter()
        for i in items:
            for label, cnt in i.get("hits_by_keyword", {}).items():
                surf_kw[label] += cnt
        # Per-repo hit aggregation (Item 9)
        repo_hits: Counter = Counter()
        for i in items:
            rn = i.get("repo_full_name", "")
            if rn:
                repo_hits[rn] += i.get("total_specific_hits", 0)
        repos_ranked = [{"repo": rn, "hit_count": cnt}
                        for rn, cnt in repo_hits.most_common()]
        repo_hit_values = list(repo_hits.values())
        surface_stats[surface] = {
            "count":                  len(items),
            "total_specific_hits":    sum(spec_hits),
            "specific_hits_per_item": descriptive_stats(spec_hits),
            "hits_ranked":            hits_ranked,
            "repos_ranked":           repos_ranked,
            "repo_hit_stats":         descriptive_stats(repo_hit_values),
            "keywords_ranked": [{"keyword": k, "count": v} for k, v in surf_kw.most_common()],
        }

    # Cross-surface keyword table (same format as search keywords)
    nc_cross: list[dict] = []
    for surface, stats in surface_stats.items():
        for kw_entry in stats.get("keywords_ranked", []):
            nc_cross.append({
                "surface":       surface,
                "keyword":       kw_entry["keyword"],
                "surface_label": f"{surface.upper()}: {kw_entry['keyword']}",
                "count":         kw_entry["count"],
            })
    nc_cross.sort(key=lambda x: x["count"], reverse=True)

    all_kw: Counter = Counter()
    for r in results:
        for label, cnt in r.get("hits_by_keyword", {}).items():
            all_kw[label] += cnt

    domain_counts: Counter = Counter()
    for r in results:
        for d in r.get("domains", []):
            domain_counts[d] += 1

    repo_word_sets: dict[str, set[str]] = defaultdict(set)
    for r in results:
        repo = r.get("repo_full_name") or r.get("id", "unknown")
        for w in r.get("word_set", []):
            repo_word_sets[repo].add(w)

    # The spec restricts the word cloud to non-CODE surfaces, so cloned CODE-surface
    # doc_word_set is no longer merged in. (_aggregate_overall then replaces this with
    # sections_aggregate's version, which also strips agent trailers.)
    _custom_stops = _load_custom_stopwords()
    word_freq: Counter = Counter()
    for words in repo_word_sets.values():
        for w in words:
            if w not in _custom_stops:
                word_freq[w] += 1

    lang_counts: Counter = Counter()
    for r in by_surface.get("repos", []):
        lang = r.get("language")
        if lang:
            lang_counts[lang] += 1

    return {
        "total_items":          len(results),
        "by_surface":           surface_stats,
        "keywords_ranked":      dict(all_kw.most_common()),
        "keywords_cross_surface": nc_cross,
        "domain_counts":        dict(domain_counts.most_common()),
        "top_word_freq":        dict(word_freq.most_common(200)),
        "language_distribution": dict(lang_counts.most_common(30)),
    }


def _aggregate_search_summary(search_dir: Path) -> dict:
    summary = load_json(search_dir / "summary.json", {})
    if not summary:
        return {}

    result: dict = {}
    cross_surface: list[dict] = []
    all_kw_hits: Counter = Counter()

    for surface, data in summary.items():
        if not isinstance(data, dict):
            continue
        kw_list = []
        for kw, kw_data in data.get("keywords", {}).items():
            if not isinstance(kw_data, dict):
                continue
            hit_count = kw_data.get("api_hit_count", 0)
            unique    = kw_data.get("unique_results", 0)
            kw_list.append({"keyword": kw, "search_hit_count": hit_count, "unique_results": unique})
            cross_surface.append({
                "surface":          surface,
                "keyword":          kw,
                "surface_label":    f"{surface.upper()}: {kw}",
                "search_hit_count": hit_count,
                "unique_results":   unique,
            })
            all_kw_hits[kw] += unique
        kw_list.sort(key=lambda x: x["unique_results"], reverse=True)
        result[surface] = {
            "search_hit_count": data.get("api_hit_count", 0),
            "unique_results":   data.get("unique_results", 0),
            "keywords_ranked":  kw_list,
        }

    cross_surface.sort(key=lambda x: x["unique_results"], reverse=True)
    result["keywords_cross_surface"] = cross_surface
    result["keywords_total"] = dict(all_kw_hits.most_common())
    return result


def fetch_cloned_repo_metadata(slug: str, token: str, logger) -> int:
    """Fetch GitHub repo metadata for all repos across all 6 search surfaces.
    Uses 4 concurrent workers (~320 req/min, well inside 5 000/hr limit).
    Saves to analysis/cloned_repo_metadata.json; returns new fetch count.
    """
    import time as _time
    import requests as _requests
    from concurrent.futures import ThreadPoolExecutor, as_completed

    dirs = technique_dirs(slug)
    metadata_path = dirs["analysis"] / "cloned_repo_metadata.json"
    repo_metadata: dict = load_json(metadata_path, {}) or {}

    all_repos: set[str] = set()
    for surface in ["code", "repos", "commits", "prs", "issues", "discussions"]:
        for item in load_json(dirs["search"] / f"{surface}.json", []):
            rn = item.get("repo_full_name") or item.get("full_name", "")
            if rn:
                all_repos.add(rn)

    to_fetch = [r for r in all_repos if r not in repo_metadata]
    if not to_fetch:
        print(f"  Repo metadata: all {len(repo_metadata)} repos already cached — skipping fetch.")
        return 0

    print(f"  {len(to_fetch)} repos to fetch ({len(repo_metadata)} already cached), 4 workers...")

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    def _fetch_one(repo_name: str) -> tuple[str, dict | None]:
        _time.sleep(0.75)
        url = f"{cfg.GITHUB_API_BASE}/repos/{repo_name}"
        try:
            resp = _requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 404:
                return repo_name, None
            if resp.status_code in (403, 429):
                reset_ts = int(resp.headers.get("X-RateLimit-Reset", _time.time() + 60))
                wait = max(reset_ts - _time.time(), 5)
                if logger:
                    logger.warning(f"Rate limited — sleeping {wait:.0f}s")
                _time.sleep(wait)
                resp = _requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                if logger:
                    logger.warning(f"Metadata fetch HTTP {resp.status_code} for {repo_name}")
                return repo_name, repo_metadata.get(repo_name)
            data = resp.json()
            topics = [t for t in data.get("topics", []) if isinstance(t, str)]
            return repo_name, {
                "full_name":   data.get("full_name", repo_name),
                "stars":       data.get("stargazers_count"),
                "language":    data.get("language"),
                "size_kb":     data.get("size", 0),
                "created_at":  data.get("created_at"),
                "description": data.get("description", "") or "",
                "topics":      topics,
            }
        except Exception as exc:
            if logger:
                logger.warning(f"Metadata fetch error for {repo_name}: {exc}")
            return repo_name, repo_metadata.get(repo_name)

    fetched = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_fetch_one, r): r for r in to_fetch}
        for i, fut in enumerate(as_completed(futs), 1):
            name, data = fut.result()
            repo_metadata[name] = data
            if data is not None:
                fetched += 1
            if i % 500 == 0:
                save_json(metadata_path, repo_metadata)
                if logger:
                    logger.info(f"cloned_repo_metadata: saved at {i} completions ({fetched} new)")
                print(f"  [{i}/{len(to_fetch)}] {fetched} new entries so far...")

    save_json(metadata_path, repo_metadata)
    if logger:
        logger.info(f"cloned_repo_metadata: fetched {fetched} new entries, total={len(repo_metadata)}")
    print(f"  Repo metadata: {fetched} new entries fetched, {len(repo_metadata)} total in cloned_repo_metadata.json")
    return fetched


def _aggregate_repo_sizes(analysis_dir: Path, search_dir: Path) -> dict:
    """Compute size stats per surface using cloned_repo_metadata.json (accurate for all surfaces)."""
    repo_metadata: dict = load_json(analysis_dir / "cloned_repo_metadata.json", {}) or {}
    if not repo_metadata:
        # Fall back to reading size_kb from surface items (only REPOS surface has it)
        sizes_all: list[float] = []
        sizes_by_surface: dict[str, list[float]] = defaultdict(list)
        for surface in ["code", "repos", "commits", "prs", "issues", "discussions"]:
            for item in load_json(search_dir / f"{surface}.json", []):
                kb = item.get("size_kb", 0) or 0
                if kb > 0:
                    sizes_all.append(float(kb))
                    sizes_by_surface[surface].append(float(kb))
        return {
            "overall":    descriptive_stats(sizes_all),
            "by_surface": {s: descriptive_stats(v) for s, v in sizes_by_surface.items()},
            "from_metadata": False,
        }

    sizes_by_surface: dict[str, list[float]] = defaultdict(list)
    all_repos_with_size: set[str] = set()
    for surface in ["code", "repos", "commits", "prs", "issues", "discussions"]:
        repos_on_surface: set[str] = set()
        for item in load_json(search_dir / f"{surface}.json", []):
            rn = item.get("repo_full_name") or item.get("full_name", "")
            if rn:
                repos_on_surface.add(rn)
        for rn in repos_on_surface:
            meta = repo_metadata.get(rn)
            if meta and isinstance(meta, dict):
                kb = meta.get("size_kb", 0) or 0
                if kb > 0:
                    sizes_by_surface[surface].append(float(kb))
                    all_repos_with_size.add(rn)

    sizes_all = [float(repo_metadata[rn]["size_kb"])
                 for rn in all_repos_with_size
                 if isinstance(repo_metadata.get(rn), dict) and repo_metadata[rn].get("size_kb", 0) > 0]
    return {
        "overall":    descriptive_stats(sizes_all),
        "by_surface": {s: descriptive_stats(v) for s, v in sizes_by_surface.items()},
        "from_metadata": True,
    }


def _aggregate_search_hit_distributions(search_dir: Path) -> dict:
    """
    Per-item hit counts (total and unique keywords matched) for each search surface,
    sorted highest to lowest. Used for distribution line charts.
    """
    distributions: dict[str, list[dict]] = {}
    for surface in ["code", "repos", "commits", "prs", "issues", "discussions"]:
        items = load_json(search_dir / f"{surface}.json", [])
        if not items:
            continue
        item_counts = []
        for item in items:
            kws = item.get("matched_keywords", [])
            if not kws:
                kw = item.get("matched_keyword")
                kws = [kw] if kw else []
            name = (item.get("repo_full_name") or item.get("full_name")
                    or str(item.get("title", ""))[:60] or str(item.get("id", "")))
            item_counts.append({
                "name":                name,
                "hit_count":           len(kws),
                "unique_keyword_count": len(set(kws)),
            })
        item_counts.sort(key=lambda x: x["hit_count"], reverse=True)
        distributions[surface] = item_counts
    return distributions


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def run(
    slug: str,
    code_only: bool = False,
    noncode_only: bool = False,
    restart: bool = False,
    workers: int = cfg.ANALYSIS_WORKERS,
    aggregate_only: bool = False,
    no_size_stats: bool = False,
) -> None:
    ensure_dirs(slug)
    dirs   = technique_dirs(slug)
    logger = setup_logging(slug, "analysis")

    if aggregate_only:
        print("--aggregate-only: skipping clone/scan, aggregating from existing data on disk.")
        logger.info("aggregate-only mode: skipping clone/scan")
        _aggregate_overall(slug, dirs, logger)
        return

    from full_analysis import code_analysis
    from full_analysis import non_code_analysis

    if not noncode_only and not code_only:
        logger.info("Running code and non-code analysis in parallel")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            code_fut    = pool.submit(code_analysis.run, slug, restart, workers, no_size_stats)
            noncode_fut = pool.submit(non_code_analysis.run, slug, restart, no_size_stats)
            concurrent.futures.wait([code_fut, noncode_fut])
            for fut in [code_fut, noncode_fut]:
                exc = fut.exception()
                if exc:
                    logger.error(f"Analysis worker error: {exc}", exc_info=True)
    elif code_only:
        code_analysis.run(slug, restart, workers, no_size_stats)
    else:
        non_code_analysis.run(slug, restart, no_size_stats)

    logger.info("Aggregating results into overall.json")
    _aggregate_overall(slug, dirs, logger)


def _is_gone(rec: dict) -> bool:
    """Scan failure meaning the repository no longer exists publicly (not a transient error)."""
    e = (rec.get("error") or "").lower()
    return any(s in e for s in ("repository not found", "is disabled", "access to this repository",
                                "dmca", "could not read username", "authentication failed"))


def _load_code_records(slug: str, dirs: dict, logger=None, use_legacy: bool = False) -> tuple[list[dict], dict]:
    """
    Analysed CODE-surface records for the comparable population (specialised_analysis.
    build_population: CODE repos minus those found only by excluded search keywords),
    using specialised_analysis records (analysis/specialised_repos.json = current
    snapshots) only. Repositories deleted/private since the search are dropped from the
    population. use_legacy=True re-enables the old fallback to repaired code_repos.json
    records (search-time snapshots) for repos the specialised scan has not covered.
    """
    from code_specialised_analysis import build_population
    pop        = build_population(slug, dirs)
    searched   = set(pop["phase1"]) | set(pop["phase2"])
    spec       = load_json(dirs["analysis"] / "specialised_repos.json", {}) or {}
    # Repositories deleted, made private or disabled since the search no longer exist
    # "now", so they leave the population (they are not "not analysed").
    gone       = {n for n, r in spec.items() if n in searched and r.get("status") != "ok" and _is_gone(r)}
    population = searched - gone
    spec_ok    = {n: r for n, r in spec.items() if r.get("status") == "ok" and n in population}
    legacy: list[dict] = []
    if use_legacy:
        history = load_json(dirs["analysis"] / "code_history.json", {}) or {}
        need_legacy = {n for n in population - set(spec_ok) if history.get(n) == "done"}
        if need_legacy:
            legacy = [r for r in load_json(dirs["analysis"] / "code_repos.json", []) or []
                      if r.get("full_name") in need_legacy]
    records = list(spec_ok.values()) + legacy
    status = {
        "searched": len(searched), "gone": len(gone), "gone_repos": sorted(gone),
        "population": len(population), "phase1": len(pop["phase1"]), "phase2": len(pop["phase2"]),
        "excluded": len(pop["excluded"]), "excluded_keywords": pop["exclude_keywords"],
        "specialised_ok": len(spec_ok),
        "specialised_failed": sum(1 for n, r in spec.items() if n in population and r.get("status") != "ok"),
        "failed_repos": {n: (r.get("error") or "")[:160] for n, r in spec.items()
                         if n in population and r.get("status") != "ok"},
        "not_scanned_repos": sorted(population - set(spec)),
        "legacy_fallback": len(legacy),
        "not_analysed": len(population) - len(spec_ok) - len(legacy),
    }
    if logger:
        logger.info(f"code records: {status}")
    return records, status


def _aggregate_overall(slug: str, dirs: dict, logger=None) -> None:
    code_repos, code_status = _load_code_records(slug, dirs, logger)
    noncode_results: list[dict] = load_json(dirs["analysis"] / "noncode_results.json", [])

    # Enrich records with metadata (stars, language, size, description…) from cloned_repo_metadata.json
    metadata_path = dirs["analysis"] / "cloned_repo_metadata.json"
    repo_metadata: dict = {}
    if metadata_path.exists():
        repo_metadata = load_json(metadata_path, {}) or {}
    for entry in code_repos:
        name = entry.get("full_name", "")
        meta = repo_metadata.get(name)
        entry.setdefault("html_url", f"https://github.com/{name}")
        if meta and isinstance(meta, dict):
            for key in ("stars", "language", "created_at", "description", "topics"):
                if entry.get(key) in (None, "", []):
                    entry[key] = meta.get(key)
            if not entry.get("size_kb"):
                entry["size_kb"] = meta.get("size_kb", 0)

    # Repair legacy scan data in memory (test/source split, .ipynb, binary files,
    # subset keywords) and summarise every record — see data_repair.py.
    # code_repos.json on disk is left untouched.
    from report_helpers.data_repair import RepairContext, repair_record
    from report_helpers import sections_aggregate
    rctx      = RepairContext(slug, dirs["analysis"])
    summaries = [repair_record(r, rctx) for r in code_repos]
    if logger:
        logger.info(f"data_repair: {dict(rctx.totals)}")

    code_agg    = _aggregate_code(code_repos)
    noncode_agg = _aggregate_noncode(noncode_results, code_repos)
    search_agg  = _aggregate_search_summary(dirs["search"])
    size_agg    = _aggregate_repo_sizes(dirs["analysis"], dirs["search"])
    hit_dists   = _aggregate_search_hit_distributions(dirs["search"])
    sections    = sections_aggregate.build(slug, dirs, summaries, noncode_results, repo_metadata, rctx, code_status)
    code_agg["data_repair"] = dict(rctx.totals)
    code_agg["record_sources"] = code_status

    # Legacy keys read by report.py now carry the corrected semantics:
    #  domain_counts — per repository, word-boundary matching, relevant items only
    #  top_word_freq — non-CODE sources only (no cloned-repo doc words), agent trailers stripped
    if noncode_agg:
        noncode_agg["domain_counts_items_legacy"] = noncode_agg.get("domain_counts", {})
        noncode_agg["domain_counts"] = sections["a6"]["domain_counts"]
        noncode_agg["top_word_freq"] = dict(list(sections["a7"]["freq"].items())[:200])

    # Enrich keyword categories from analysis keywords JSON (fills blanks from real data
    # where code_analysis.py may not have stored category in hits_by_keyword)
    try:
        kws_raw = load_analysis_keywords(slug)
        kw_cat  = {k["id"]: k.get("category", "") for k in kws_raw}
        for entry in code_agg.get("keywords_ranked", []):
            if not entry.get("category"):
                entry["category"] = kw_cat.get(entry["id"], "")
        for entry in code_agg.get("keywords_by_category", []):
            if not entry.get("category"):
                entry["category"] = kw_cat.get(entry["id"], "")
    except Exception:
        pass

    all_repo_names: set[str] = set()
    for surface in ["code", "repos", "commits", "prs", "issues", "discussions"]:
        for item in load_json(dirs["search"] / f"{surface}.json", []):
            rn = item.get("repo_full_name", "")
            if rn:
                all_repo_names.add(rn)

    # "count" stays the number of repos the statistics were computed over (repos with a
    # size); the union of all repos is reported separately.
    size_agg["overall"]["union_count"] = len(all_repo_names)
    size_agg["overall"]["no_size_count"] = len(all_repo_names) - size_agg["overall"].get("count", 0)

    overall = {
        "slug":                     slug,
        "repos_found_total":        len(all_repo_names),
        "repos_by_surface": {
            s: len({i.get("repo_full_name", "") for i in load_json(dirs["search"] / f"{s}.json", [])
                    if i.get("repo_full_name")})
            for s in ["code", "repos", "commits", "prs", "issues", "discussions"]
        },
        "repo_size_stats":          size_agg,
        "search_summary":           search_agg,
        "search_hit_distributions": hit_dists,
        "code_analysis":            code_agg,
        "noncode_analysis":         noncode_agg,
        "commit_surface_timeline":  sections["t9"],
        "sections":                 sections,
    }

    save_json(dirs["analysis"] / "overall.json", overall)
    if logger:
        logger.info("overall.json written")
    print("\nAggregation complete. overall.json saved.")
