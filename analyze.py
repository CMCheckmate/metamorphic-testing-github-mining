"""
Phase 3 — Local Analysis
=========================
Walks each cloned repo and scans every file for adoption signals of the specified
testing technique.  Also collects repository-level statistics for coverage, commit
history, domain, and project-type analysis.

Produces in results/<slug>/analysis/:
  findings.json      — per-file pattern matches (with artifact type)
  repo_scores.json   — per-repo scores, classification, and all derived metrics

Usage:
    python analyze.py --technique techniques/metamorphic_testing.yaml
    python analyze.py --technique techniques/fuzzing.yaml --workers 8
    python analyze.py --technique techniques/property_based_testing.yaml --append
"""

import argparse
import json
import re
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()

# ---------------------------------------------------------------------------
# Optional NLTK lemmatization
# ---------------------------------------------------------------------------
try:
    import nltk
    from nltk.stem import WordNetLemmatizer
    from nltk.tokenize import word_tokenize
    _LEMMATIZER: "WordNetLemmatizer | None" = WordNetLemmatizer()
    _NLTK_AVAILABLE = True
except ImportError:
    _LEMMATIZER = None
    _NLTK_AVAILABLE = False


def _ensure_nltk_data() -> None:
    if not _NLTK_AVAILABLE:
        return
    for resource, kind in [
        ("tokenizers/punkt_tab",                   "punkt_tab"),
        ("taggers/averaged_perceptron_tagger_eng", "averaged_perceptron_tagger_eng"),
        ("corpora/wordnet",                        "wordnet"),
    ]:
        try:
            nltk.data.find(resource)
        except LookupError:
            nltk.download(kind, quiet=True)


_COMMENT_LINE_RE   = re.compile(r'(?:#|//)(.+)$',   re.MULTILINE)
_STRING_LITERAL_RE = re.compile(r'"([^"\n]{4,})"')

# ---------------------------------------------------------------------------
# Worker-process globals — set once per worker via ProcessPoolExecutor initializer
# ---------------------------------------------------------------------------

_W_PATTERNS:             list[dict] = []
_W_RESULTS_DIR:          Path       = Path(".")
_W_ANALYSIS_EXTENSIONS:  set[str]   = set()
_W_SKIP_DIRS:            set[str]   = set()
_W_SKIP_EXTENSIONS:      set[str]   = set()
_W_DOC_EXTENSIONS:       set[str]   = set()
_W_CONFIG_EXTENSIONS:    set[str]   = set()
_W_CONCEPT_LEMMAS:       dict       = {}
_W_LEMMA_TRIGGER:        str        = ""
_W_COMMIT_KEYWORDS:      list[str]  = []
_W_DOMAIN_KEYWORDS:      dict       = {}
_W_SHORT_NAME:           str        = ""

# Test-directory name fragments — used by artifact type classifier
_TEST_DIR_PARTS: frozenset[str] = frozenset({
    "test", "tests", "spec", "specs", "testing", "__tests__",
    "e2e", "integration", "unit", "unittest", "functionaltest",
    "systemtest", "acceptancetest", "testcases", "testcase",
    "test_cases", "test_data",
})

# Documentation directory name fragments
_DOC_DIR_PARTS: frozenset[str] = frozenset({
    "docs", "doc", "documentation", "wiki", "guides", "examples",
    "tutorials", "samples",
})


def _worker_init(cfg: dict) -> None:
    """Called once in each worker process before any jobs run."""
    global _W_PATTERNS, _W_RESULTS_DIR, _W_ANALYSIS_EXTENSIONS
    global _W_SKIP_DIRS, _W_SKIP_EXTENSIONS, _W_DOC_EXTENSIONS, _W_CONFIG_EXTENSIONS
    global _W_CONCEPT_LEMMAS, _W_LEMMA_TRIGGER
    global _W_COMMIT_KEYWORDS, _W_DOMAIN_KEYWORDS, _W_SHORT_NAME

    flag_map = {"IGNORECASE": re.IGNORECASE, "MULTILINE": re.MULTILINE}
    _W_PATTERNS = [
        {
            "id":    p["id"],
            "label": p["label"],
            "regex": re.compile(p["regex"], flag_map.get(p.get("flags", ""), 0)),
        }
        for p in cfg["patterns_raw"]
    ]
    _W_RESULTS_DIR         = Path(cfg["results_dir"])
    _W_ANALYSIS_EXTENSIONS = set(cfg["analysis_extensions"])
    _W_SKIP_DIRS           = set(cfg["skip_dirs"])
    _W_SKIP_EXTENSIONS     = set(cfg["skip_extensions"])
    _W_DOC_EXTENSIONS      = set(cfg.get("doc_extensions", []))
    _W_CONFIG_EXTENSIONS   = set(cfg.get("config_extensions", []))
    _W_CONCEPT_LEMMAS      = cfg["concept_lemmas"]
    _W_LEMMA_TRIGGER       = cfg["lemma_trigger"]
    _W_COMMIT_KEYWORDS     = cfg.get("commit_keywords", [])
    _W_DOMAIN_KEYWORDS     = cfg.get("domain_keywords", {})
    _W_SHORT_NAME          = cfg.get("short_name", "")


# ---------------------------------------------------------------------------
# Artifact type classification
# ---------------------------------------------------------------------------

_SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".java", ".js", ".ts", ".jsx", ".tsx", ".cpp", ".c", ".h", ".hpp",
    ".hxx", ".cc", ".cxx", ".cs", ".go", ".rb", ".rs", ".swift", ".kt", ".kts",
    ".scala", ".php", ".r", ".m", ".mm", ".sh", ".bash", ".zsh", ".pl", ".pm",
    ".lua", ".dart", ".hs", ".ml", ".mli", ".clj", ".cljs", ".cljc", ".ex",
    ".exs", ".erl", ".hrl", ".elm", ".groovy", ".f", ".f90", ".f95", ".f03",
    ".jl", ".v", ".sv", ".vhd", ".vhdl", ".zig", ".nim", ".cr",
})


def _classify_artifact_type(rel_path_str: str) -> str:
    """
    Classify a file as: test_code, source_code, documentation, config, or other.
    Uses directory path and extension heuristics.
    """
    path = rel_path_str.replace("\\", "/").lower()
    parts = path.split("/")
    fname = parts[-1]
    ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""

    # Documentation — by extension or directory
    if ext in _W_DOC_EXTENSIONS or any(p in _DOC_DIR_PARTS for p in parts[:-1]):
        return "documentation"

    # Config / build files
    if ext in _W_CONFIG_EXTENSIONS or fname in (
        "makefile", "cmake", "cmakelists.txt", "dockerfile",
        "requirements.txt", "setup.py", "pyproject.toml", "pom.xml",
        "build.gradle", "cargo.toml", "go.mod", "package.json",
    ):
        return "config"

    # Test code — by directory or filename convention
    if any(p in _TEST_DIR_PARTS for p in parts[:-1]):
        return "test_code"
    if (
        fname.startswith("test_") or
        fname.endswith(("_test.py", "_test.java", "_test.go",
                         "_test.rb", "_test.js", "_test.ts",
                         "test.py", "test.java", "test.go",
                         "spec.rb", "spec.js", "spec.ts",
                         "_spec.py", "tests.py")) or
        re.match(r"test[a-z]", fname)
    ):
        return "test_code"

    # Known source code extensions
    if ext in _SOURCE_EXTENSIONS:
        return "source_code"

    # Unrecognized extension — catch-all
    return "other"


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------

def iter_source_files(repo_path: Path):
    """Yield (absolute_path, path_relative_to_repo) for every analysable file."""
    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue
        if any(skip_dir in file_path.parts for skip_dir in _W_SKIP_DIRS):
            continue
        if _W_ANALYSIS_EXTENSIONS and file_path.suffix not in _W_ANALYSIS_EXTENSIONS:
            continue
        if file_path.suffix in _W_SKIP_EXTENSIONS:
            continue
        yield file_path, file_path.relative_to(repo_path)


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------

def _lemmatized_findings(text: str, rel_path: Path) -> list[dict]:
    """Scan comment/string lines for technique concepts via lemmatization."""
    if not _NLTK_AVAILABLE or _LEMMATIZER is None or not _W_LEMMA_TRIGGER or not _W_CONCEPT_LEMMAS:
        return []

    results: list[dict] = []
    seen: set[tuple] = set()

    for context_re, kind in [(_COMMENT_LINE_RE, "Comment"), (_STRING_LITERAL_RE, "String")]:
        for m in context_re.finditer(text):
            segment = m.group(1)
            if _W_LEMMA_TRIGGER not in segment.lower():
                continue
            tokens = word_tokenize(segment.lower())
            lemmas: set[str] = set()
            for tok in tokens:
                lemmas.add(_LEMMATIZER.lemmatize(tok, pos="v"))
                lemmas.add(_LEMMATIZER.lemmatize(tok, pos="n"))
            line_number = text[: m.start()].count("\n") + 1
            for base_lemma, concept_label in _W_CONCEPT_LEMMAS.items():
                key = (line_number, base_lemma)
                if base_lemma in lemmas and key not in seen:
                    seen.add(key)
                    results.append({
                        "id":      f"lemma_{base_lemma}",
                        "label":   f"Lemmatised {kind}: {concept_label}",
                        "file":    str(rel_path),
                        "line":    line_number,
                        "snippet": segment[:200].strip(),
                    })
    return results


def _context_snippet(text: str, m: re.Match, context_lines: int = 1) -> str:
    lines      = text.splitlines()
    match_line = text[:m.start()].count("\n")
    first_line = max(0, match_line - context_lines)
    last_line  = min(len(lines), match_line + context_lines + 1)
    return "\n".join(lines[first_line:last_line]).strip()


def _analyze_file_text(file_path: Path, rel_path: Path, text: str) -> list[dict]:
    """Scan pre-read file text against all patterns. Returns match records.

    Lemmatized findings are only added for lines not already matched by a regex
    pattern, preventing double-counting of the same (file, line) in the score.
    """
    match_records: list[dict] = []
    regex_lines: set[int] = set()
    for pattern in _W_PATTERNS:
        for m in pattern["regex"].finditer(text):
            line_number = text[:m.start()].count("\n") + 1
            match_records.append({
                "id":      pattern["id"],
                "label":   pattern["label"],
                "file":    str(rel_path),
                "line":    line_number,
                "snippet": _context_snippet(text, m),
            })
            regex_lines.add(line_number)
    for lemma_rec in _lemmatized_findings(text, rel_path):
        if lemma_rec["line"] not in regex_lines:
            match_records.append(lemma_rec)
    return match_records


# ---------------------------------------------------------------------------
# Git commit history analysis
# ---------------------------------------------------------------------------

def _analyze_git_commits(repo_path: Path) -> dict:
    """
    Run git log on the cloned repository and extract commit statistics.
    Returns a dict of commit metrics; empty dict on any failure.
    """
    if not _W_COMMIT_KEYWORDS:
        return {}
    try:
        result = subprocess.run(
            ["git", "log", "--no-merges", "--format=%ae|%ai|%s"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=60,
            errors="replace",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}

        emails: set[str] = set()
        technique_dates: list[str] = []
        monthly_total:     Counter = Counter()
        monthly_technique: Counter = Counter()
        total_count = 0

        kw_lower = [k.lower() for k in _W_COMMIT_KEYWORDS]

        for raw_line in result.stdout.strip().split("\n"):
            if "|" not in raw_line:
                continue
            parts = raw_line.split("|", 2)
            if len(parts) < 3:
                continue
            email, date_str, msg = parts
            email    = email.strip()
            date_str = date_str.strip()[:10]   # YYYY-MM-DD
            month    = date_str[:7]            # YYYY-MM
            msg_low  = msg.lower()

            emails.add(email)
            total_count += 1
            monthly_total[month] += 1

            if any(kw in msg_low for kw in kw_lower):
                technique_dates.append(date_str)
                monthly_technique[month] += 1

        technique_dates.sort()
        span_days = 0
        if len(technique_dates) >= 2:
            try:
                span_days = (
                    datetime.fromisoformat(technique_dates[-1]) -
                    datetime.fromisoformat(technique_dates[0])
                ).days
            except ValueError:
                span_days = 0

        return {
            "total_commits_sampled":        total_count,
            "contributor_count_git":        len(emails),
            "technique_commits_count":      len(technique_dates),
            "technique_commit_ratio":       len(technique_dates) / total_count if total_count else 0.0,
            "first_technique_commit_date":  technique_dates[0]  if technique_dates else None,
            "last_technique_commit_date":   technique_dates[-1] if technique_dates else None,
            "technique_commit_span_days":   span_days,
            "technique_commit_dates":       technique_dates,
            "monthly_total_commits":        dict(monthly_total),
            "monthly_technique_commits":    dict(monthly_technique),
        }
    except Exception as exc:
        return {"git_error": str(exc)}


# ---------------------------------------------------------------------------
# Domain inference
# ---------------------------------------------------------------------------

def _infer_domains(name: str, description: str, topics: list[str]) -> list[str]:
    """
    Keyword-based domain inference from repo name, description, and GitHub topics.
    Returns a (possibly empty) list of matched domain keys from DOMAIN_KEYWORDS.
    """
    text = " ".join(filter(None, [name.split("/")[-1], description or "", " ".join(topics or [])])).lower()
    matched = []
    for domain, keywords in _W_DOMAIN_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(domain)
    return matched


# ---------------------------------------------------------------------------
# Project type classification
# ---------------------------------------------------------------------------

def _classify_project_type(repo_name: str, description: str, artifact_counts: dict) -> str:
    """
    Classify whether this repo is a framework/library, research artifact, or
    a project that uses the technique in its own test suite.
    """
    # Research artifact signals in name/description
    name_lower = (repo_name.split("/")[-1] + " " + (description or "")).lower().replace("-", " ").replace("_", " ")
    research_signals = [
        "replication", "artifact", "replication package", "icse", "issta",
        "fse", "ase", "emse", "tosem", "tse", "paper", "evaluation",
        "experiment", "benchmark", "reproduction",
    ]
    if sum(1 for s in research_signals if s in name_lower) >= 2:
        return "research_artifact"

    test_hits   = artifact_counts.get("test_code", 0)
    source_hits = artifact_counts.get("source_code", 0)
    total       = test_hits + source_hits
    if total == 0:
        # Only documentation/config matches — treat as research or unknown
        if artifact_counts.get("documentation", 0) > 0:
            return "documentation_only"
        return "unknown"

    ratio = test_hits / total
    if ratio >= 0.65:
        return "general_usage"   # technique used in testing the repo's own code
    if ratio <= 0.25:
        return "framework"       # technique infrastructure / library
    return "mixed"


# ---------------------------------------------------------------------------
# Per-repo scoring
# ---------------------------------------------------------------------------

def score_repo(
    findings:     list[dict],
    total_files:  int,
    total_lines:  int,
) -> dict:
    """Compute score and all derived metrics for one repo."""
    total_matches = len(findings)

    # Files with technique signals
    files_with_matches = {f["file"] for f in findings}
    n_technique_files  = len(files_with_matches)

    # Unique (file, line) pairs with a match — technique line count
    technique_lines = len({(f["file"], f["line"]) for f in findings})

    # Per-file mention counts
    mentions_per_file = Counter(f["file"] for f in findings)
    avg_mentions = (
        sum(mentions_per_file.values()) / len(mentions_per_file)
        if mentions_per_file else 0.0
    )
    max_mentions = max(mentions_per_file.values()) if mentions_per_file else 0

    # Coverage ratios
    file_ratio = n_technique_files / total_files if total_files > 0 else 0.0
    line_density = technique_lines / total_lines if total_lines > 0 else 0.0

    # Artifact type breakdown (counts among findings)
    artifact_counts = dict(Counter(f.get("artifact_type", "other") for f in findings))

    return {
        "score":                     total_matches,
        "direct_matches":            total_matches,

        # File and line coverage
        "total_files_scanned":       total_files,
        "total_lines_scanned":       total_lines,
        "technique_files":           n_technique_files,
        "technique_lines":           technique_lines,
        "technique_file_ratio":      round(file_ratio,    4),
        "technique_line_density":    round(line_density,  6),

        # Per-file spread
        "avg_mentions_per_technique_file": round(avg_mentions, 2),
        "max_mentions_in_file":            max_mentions,

        # Artifact breakdown
        "artifact_breakdown":        artifact_counts,
        "patterns_matched":          list({f["label"] for f in findings}),
    }


# ---------------------------------------------------------------------------
# Per-repo worker (runs in a separate process via ProcessPoolExecutor)
# ---------------------------------------------------------------------------

def _analyse_repo(repo_meta: dict) -> tuple[list[dict], dict | None]:
    """Walk one cloned repo, scan files, analyse commits. Returns (findings, score_record)."""
    import os, time as _time
    repo_name  = repo_meta["full_name"]
    local_path = Path(repo_meta["local_path"])

    if not local_path.exists():
        return [], None

    log_dir  = _W_RESULTS_DIR / "analysis" / "worker_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{os.getpid()}.log"

    all_findings: list[dict] = []
    total_files  = 0
    total_lines  = 0
    t0 = _time.monotonic()

    with open(log_path, "a", buffering=1, errors="replace") as log:
        log.write(f"\n=== {repo_name} ===\n")
        for file_path, rel_path in iter_source_files(local_path):
            total_files += 1
            try:
                text = file_path.read_text(errors="replace")
            except Exception:
                continue
            total_lines += max(1, text.count("\n") + 1)

            artifact_type = _classify_artifact_type(str(rel_path))
            for finding in _analyze_file_text(file_path, rel_path, text):
                finding["repo"]          = repo_name
                finding["artifact_type"] = artifact_type
                all_findings.append(finding)

            log.write(f"  {rel_path}\n")
        elapsed = _time.monotonic() - t0
        log.write(f"  done — {total_files} files, {total_lines} lines, "
                  f"{len(all_findings)} findings, {elapsed:.1f}s\n")

    # --- Git commit history ---
    commit_stats = _analyze_git_commits(local_path)

    # --- Artifact breakdown and project type ---
    artifact_counts = dict(Counter(f.get("artifact_type", "other") for f in all_findings))
    project_type    = _classify_project_type(
        repo_name,
        repo_meta.get("description", ""),
        artifact_counts,
    )

    # --- Domain inference ---
    inferred_domains = _infer_domains(
        repo_name,
        repo_meta.get("description", ""),
        repo_meta.get("topics", []),
    )

    # --- Score record ---
    base_score = score_repo(all_findings, total_files, total_lines)
    score_record = {
        "repo":              repo_name,
        "url":               repo_meta.get("html_url", ""),
        "stars":             repo_meta.get("stars", 0),
        "language":          repo_meta.get("language", ""),
        "created_at":        repo_meta.get("created_at", ""),
        "description":       repo_meta.get("description", ""),
        "topics":            repo_meta.get("topics", []),
        "found_by_queries":  repo_meta.get("matched_queries", []),

        # Project metadata
        "project_type":      project_type,
        "inferred_domains":  inferred_domains,

        # Commit analysis
        **commit_stats,

        # Score + coverage metrics
        **base_score,
    }
    return all_findings, score_record


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _dedup_records(records: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    seen: set[tuple] = set()
    out:  list[dict] = []
    for r in records:
        key = tuple(r.get(f) for f in key_fields)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _load_existing_outputs(out_dir: Path) -> tuple[list[dict], list[dict]]:
    findings_path = out_dir / "findings.json"
    scores_path   = out_dir / "repo_scores.json"
    existing_findings: list[dict] = []
    existing_scores:   list[dict] = []
    if findings_path.exists():
        with open(findings_path) as fh:
            existing_findings = json.load(fh)
    if scores_path.exists():
        with open(scores_path) as fh:
            existing_scores = json.load(fh)
    return existing_findings, existing_scores


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    target_repo: str | None,
    min_score:   int,
    out_dir:     Path,
    workers:     int | None,
    append:      bool,
    cleanup:     bool,
    profile,                  # TechniqueProfile
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _ensure_nltk_data()

    # --- Load manifest ---
    manifest_path = profile.results_dir / "cloned" / "manifest.json"
    if not manifest_path.exists():
        console.print("[red]No clone manifest found. Run clone.py first.[/]")
        return
    with open(manifest_path) as fh:
        manifest = json.load(fh)

    # --- Load repos.json to enrich manifest entries with description/topics ---
    repo_meta_lookup: dict[str, dict] = {}
    repos_json_path = profile.results_dir / "raw" / "repos.json"
    if repos_json_path.exists():
        try:
            with open(repos_json_path) as fh:
                for r in json.load(fh):
                    repo_meta_lookup[r.get("full_name", "")] = {
                        "description": r.get("description", ""),
                        "topics":      r.get("topics", []),
                    }
        except Exception:
            pass

    # --- Build list of repos to analyse ---
    existing_findings: list[dict] = []
    existing_scores:   list[dict] = []
    if append:
        existing_findings, existing_scores = _load_existing_outputs(out_dir)
    already_done: set[str] = {s["repo"] for s in existing_scores}

    repos_to_analyse = [
        {
            **entry,
            **repo_meta_lookup.get(entry["full_name"], {}),
        }
        for entry in manifest.get("repos", {}).values()
        if entry.get("status") in ("cloned", "refreshed", "skipped_exists")
        and entry["full_name"] not in already_done
    ]
    if target_repo:
        repos_to_analyse = [r for r in repos_to_analyse if r["full_name"] == target_repo]
        if not repos_to_analyse:
            already = " (already analysed)" if target_repo in already_done else ""
            console.print(f"[red]Repo '{target_repo}' not found in manifest{already}.[/]")
            return

    import os
    effective_workers = workers or os.cpu_count() or 4
    skip_msg = f"  ([dim]{len(already_done)} already done, skipping[/])" if already_done else ""
    console.print(
        f"\n[bold]{len(repos_to_analyse)}[/] repos to analyse  "
        f"(processes={effective_workers}){skip_msg}"
    )
    console.print(f"  [dim]Commit keywords: {', '.join(profile.commit_keywords[:5])}"
                  f"{'...' if len(profile.commit_keywords) > 5 else ''}[/]")
    console.print(f"  [dim]Per-file progress: tail {out_dir}/worker_logs/<pid>.log[/]\n")

    worker_cfg = profile.worker_config()
    new_findings: list[dict] = []
    new_scores:   list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        ptask = progress.add_task("Analysing…", total=len(repos_to_analyse))

        with ProcessPoolExecutor(
            max_workers=effective_workers,
            initializer=_worker_init,
            initargs=(worker_cfg,),
        ) as executor:
            future_map = {
                executor.submit(_analyse_repo, repo_entry): repo_entry
                for repo_entry in repos_to_analyse
            }
            for future in as_completed(future_map):
                repo_entry = future_map[future]
                repo_name  = repo_entry["full_name"]
                try:
                    findings, score_record = future.result()
                except Exception as exc:
                    console.print(f"  [red]Worker error[/] {repo_name}: {exc}")
                    progress.update(ptask, advance=1)
                    continue

                if score_record is not None:
                    new_findings.extend(findings)
                    new_scores.append(score_record)

                    if cleanup:
                        local_path = Path(repo_entry["local_path"])
                        if local_path.exists():
                            shutil.rmtree(local_path)
                        manifest["repos"][repo_name]["status"] = "cleaned"

                progress.update(ptask, description=f"[cyan]{repo_name[:50]}[/]", advance=1)

    if cleanup:
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh, indent=2)

    combined_findings = _dedup_records(
        existing_findings + new_findings,
        ("repo", "file", "line", "id"),
    )
    scores_by_repo: dict[str, dict] = {s["repo"]: s for s in existing_scores}
    for s in new_scores:
        scores_by_repo[s["repo"]] = s

    combined_scores = [
        s for s in scores_by_repo.values()
        if s.get("score", 0) >= min_score
    ]

    with open(out_dir / "findings.json", "w") as fh:
        json.dump(combined_findings, fh, indent=2)
    with open(out_dir / "repo_scores.json", "w") as fh:
        json.dump(combined_scores, fh, indent=2)

    n_signal = sum(1 for s in scores_by_repo.values() if s.get("score", 0) > 0)
    console.print(
        f"\n[bold green]Done.[/]  "
        f"[cyan]{len(scores_by_repo)}[/] repos  •  "
        f"[cyan]{n_signal}[/] with {profile.short_name} signal  •  "
        f"[cyan]{len(combined_findings)}[/] total findings\n"
        f"Output: [dim]{out_dir}[/]"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: analyse cloned repos for technique patterns")
    parser.add_argument("--technique",      required=True,
                        help="Path to technique YAML file")
    parser.add_argument("--repo",           default=None,   help="Analyse a single repo (owner/name)")
    parser.add_argument("--min-score",      type=int, default=0)
    parser.add_argument("--output-dir",     type=Path, default=None)
    parser.add_argument("--workers",        type=int, default=None)
    parser.add_argument("--append",         action="store_true")
    parser.add_argument("--cleanup-clones", action="store_true")
    args = parser.parse_args()

    from config import load_technique
    profile = load_technique(args.technique)
    out_dir = args.output_dir or (profile.results_dir / "analysis")

    run(args.repo, args.min_score, out_dir, args.workers,
        args.append, args.cleanup_clones, profile=profile)


if __name__ == "__main__":
    main()
