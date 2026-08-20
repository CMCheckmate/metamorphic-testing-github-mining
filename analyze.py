"""
Phase 3 — Local Analysis
=========================
Walks each cloned repo and scans every file for MT adoption signals.

Produces results in results/analysis/:
  - findings.json      — per-file matches with line numbers and code snippets
  - repo_scores.json   — per-repo scores and classification tier
  - summary_report.md  — human-readable markdown summary

Usage:
    python analyze.py [--repo OWNER/NAME] [--min-score N]
                      [--output-dir PATH] [--workers N] [--append]
                      [--cleanup-clones]

    --repo FULL_NAME   Analyse a single repo only (e.g. owner/name)
    --min-score N      Only include repos with score >= N in the report
    --workers N        Parallel worker threads (default: 4)
    --append           Merge with any existing analysis outputs
    --cleanup-clones   Delete each cloned repo after analysis to save disk
"""

import argparse
import json
import re
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from config import RESULTS_DIR, REPOS_DIR, ANALYSIS_EXTENSIONS, SKIP_DIRS, SKIP_EXTENSIONS

console = Console()

# ---------------------------------------------------------------------------
# Optional NLTK lemmatization — catches inflected forms in comments/strings
# that the regex patterns miss (e.g. "metamorphic tested", "was grouped").
# Gracefully disabled if NLTK is not installed.
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
        ("tokenizers/punkt_tab",                        "punkt_tab"),
        ("taggers/averaged_perceptron_tagger_eng",      "averaged_perceptron_tagger_eng"),
        ("corpora/wordnet",                             "wordnet"),
    ]:
        try:
            nltk.data.find(resource)
        except LookupError:
            nltk.download(kind, quiet=True)


# Base lemmas mapped to a readable concept label used in findings output.
_MT_CONCEPT_LEMMAS: dict[str, str] = {
    "test":     "metamorphic testing",
    "relation": "metamorphic relation",
    "group":    "metamorphic group",
    "property": "metamorphic property",
}

# Patterns for extracting comment and string text from source files.
_COMMENT_LINE_RE  = re.compile(r'(?:#|//)(.+)$',   re.MULTILINE)
_STRING_LITERAL_RE = re.compile(r'"([^"\n]{4,})"')

# ---------------------------------------------------------------------------
# Patterns — what counts as evidence of MT adoption in source files
#
# Each pattern has:
#   id      — short machine-readable key used in output files and reports
#   label   — human-readable description shown in the summary report
#   regex   — compiled regular expression applied to the full file text
#
# Pattern categories:
#   Class names     — language-agnostic names used by MT frameworks
#   Identifiers     — snake_case variable/function names common in MT code
#   String literals — quoted phrases used in test names, docstrings, etc.
#   Inline comments — #//-style comments mentioning MT concepts;
#                     each regex covers all word forms via (?:...) alternatives
#                     (e.g. test/testing/tests, relation/relationship/...)
# ---------------------------------------------------------------------------
PATTERNS: list[dict] = [
    # --- Class names (used in MT frameworks across multiple languages) ---
    {
        "id":    "class_MetamorphicTest",
        "label": "Class name: MetamorphicTest",
        "regex": re.compile(r"\bMetamorphicTest\w*\b"),
    },
    {
        "id":    "class_MetamorphicRelation",
        "label": "Class name: MetamorphicRelation",
        "regex": re.compile(r"\bMetamorphicRelation\w*\b"),
    },
    # --- Decorator (used by some MT libraries) ---
    {
        "id":    "decorator_metamorphic",
        "label": "Decorator: @metamorphic",
        "regex": re.compile(r"@metamorphic\b"),
    },
    # --- Snake_case identifiers (common naming convention in MT code) ---
    {
        "id":    "identifier_mr",
        "label": "Identifier: metamorphic_relation",
        "regex": re.compile(r"\bmetamorphic_relation\w*\b"),
    },
    {
        "id":    "identifier_mt",
        "label": "Identifier: metamorphic_test",
        "regex": re.compile(r"\bmetamorphic_test\w*\b"),
    },
    # --- String literals containing MT phrases ---
    {
        "id":    "string_mt_phrase",
        "label": 'String: "metamorphic test/testing/tests"',
        "regex": re.compile(r'"[Mm]etamorphic\s+[Tt]est(?:ing|s)?"'),
    },
    {
        "id":    "string_mr_phrase",
        "label": 'String: "metamorphic relation/relationship"',
        "regex": re.compile(r'"[Mm]etamorphic\s+[Rr]elation(?:s|ship|ships)?"'),
    },
    {
        "id":    "string_mg_phrase",
        "label": 'String: "metamorphic group/groups"',
        "regex": re.compile(r'"[Mm]etamorphic\s+[Gg]roups?"'),
    },
    {
        "id":    "string_mp_phrase",
        "label": 'String: "metamorphic property/properties"',
        "regex": re.compile(r'"[Mm]etamorphic\s+[Pp]ropert(?:y|ies)"'),
    },
    # --- Inline comments mentioning MT concepts ---
    {
        "id":    "comment_mt",
        "label": "Comment: metamorphic test/testing/tests",
        "regex": re.compile(r"(?:#|//).*\bmetamorphic\s+test(?:ing|s)?\b", re.IGNORECASE),
    },
    {
        "id":    "comment_mr",
        "label": "Comment: metamorphic relation/relationship",
        "regex": re.compile(r"(?:#|//).*\bmetamorphic\s+relation(?:s|ship|ships)?\b", re.IGNORECASE),
    },
    {
        "id":    "comment_mg",
        "label": "Comment: metamorphic group/groups",
        "regex": re.compile(r"(?:#|//).*\bmetamorphic\s+groups?\b", re.IGNORECASE),
    },
    {
        "id":    "comment_mp",
        "label": "Comment: metamorphic property/properties",
        "regex": re.compile(r"(?:#|//).*\bmetamorphic\s+propert(?:y|ies)\b", re.IGNORECASE),
    },
    # --- Uppercase abbreviations MT / MR used after the full term has been introduced ---
    # Matched case-sensitively and only when surrounded by non-alphanumeric characters
    # (spaces, hyphens, underscores, punctuation) to avoid false positives from
    # variable names like `smtp`, `html`, or matrix row abbreviations.
    {
        "id":    "abbrev_MT",
        "label": "Abbreviation: MT (metamorphic testing)",
        "regex": re.compile(r"(?<![A-Za-z0-9])MT(?![A-Za-z0-9])"),
    },
    {
        "id":    "abbrev_MR",
        "label": "Abbreviation: MR (metamorphic relation)",
        "regex": re.compile(r"(?<![A-Za-z0-9])MR(?![A-Za-z0-9])"),
    },
]


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------

def iter_source_files(repo_path: Path):
    """Yield (absolute_path, path_relative_to_repo) for every analysable file."""
    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue
        if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
            continue
        if ANALYSIS_EXTENSIONS and file_path.suffix not in ANALYSIS_EXTENSIONS:
            continue
        if file_path.suffix in SKIP_EXTENSIONS:
            continue
        yield file_path, file_path.relative_to(repo_path)


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------

def _lemmatized_findings(text: str, rel_path: Path) -> list[dict]:
    """
    Scan comment and string lines for MT concepts via lemmatization.

    Complements the regex PATTERNS by catching inflected forms they don't
    cover — past tense ("was tested"), agentive nouns ("grouped"), etc.
    Only fires when "metamorphic" is already present in the line, so false
    positives from general English lemmas ("test", "group") are avoided.
    """
    if not _NLTK_AVAILABLE or _LEMMATIZER is None:
        return []

    results: list[dict] = []
    seen: set[tuple] = set()  # (line_number, concept) dedup

    for context_re, kind in [(_COMMENT_LINE_RE, "Comment"), (_STRING_LITERAL_RE, "String")]:
        for m in context_re.finditer(text):
            segment = m.group(1)
            if "metamorphic" not in segment.lower():
                continue

            tokens = word_tokenize(segment.lower())
            lemmas: set[str] = set()
            for tok in tokens:
                lemmas.add(_LEMMATIZER.lemmatize(tok, pos="v"))
                lemmas.add(_LEMMATIZER.lemmatize(tok, pos="n"))

            line_number = text[: m.start()].count("\n") + 1
            for base_lemma, concept_label in _MT_CONCEPT_LEMMAS.items():
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


def _context_snippet(text: str, regex_match: re.Match, context_lines: int = 1) -> str:
    """Return a few lines of code surrounding a regex match."""
    lines      = text.splitlines()
    match_line = text[:regex_match.start()].count("\n")
    first_line = max(0, match_line - context_lines)
    last_line  = min(len(lines), match_line + context_lines + 1)
    return "\n".join(lines[first_line:last_line]).strip()


def analyze_file(file_path: Path, rel_path: Path) -> list[dict]:
    """Scan one file against all PATTERNS and return a list of match records."""
    try:
        text = file_path.read_text(errors="replace")
    except Exception:
        return []

    match_records: list[dict] = []
    for pattern in PATTERNS:
        for regex_match in pattern["regex"].finditer(text):
            line_number = text[:regex_match.start()].count("\n") + 1
            match_records.append({
                "id":      pattern["id"],
                "label":   pattern["label"],
                "file":    str(rel_path),
                "line":    line_number,
                "snippet": _context_snippet(text, regex_match),
            })

    match_records.extend(_lemmatized_findings(text, rel_path))
    return match_records


# ---------------------------------------------------------------------------
# Per-repo scoring
# ---------------------------------------------------------------------------

def score_repo(findings: list[dict]) -> dict:
    """
    Compute a score and classification tier for a single repository.

    Scoring: each pattern match = 3 points, capped at 100.

    Classification tiers:
      strong_explicit  3 or more matches — multiple distinct MT signals
      weak_explicit    1 or 2 matches    — at least one direct signal
      none             0 matches         — no MT evidence found
    """
    total_matches = len(findings)

    if total_matches >= 3:
        tier = "strong_explicit"
    elif total_matches >= 1:
        tier = "weak_explicit"
    else:
        tier = "none"

    return {
        "direct_matches":     total_matches,
        "score":              total_matches,
        "classification":     tier,
        "files_with_matches": len({finding["file"] for finding in findings}),
        "patterns_matched":   list({finding["label"] for finding in findings}),
    }


# ---------------------------------------------------------------------------
# Per-repo worker (runs in a separate process via ProcessPoolExecutor)
# ---------------------------------------------------------------------------

def _analyse_repo(repo_meta: dict) -> tuple[list[dict], dict | None]:
    """Walk one cloned repo and return (findings_list, score_record)."""
    import os, time as _time
    repo_name  = repo_meta["full_name"]
    local_path = Path(repo_meta["local_path"])

    if not local_path.exists():
        return [], None

    # Per-worker log file — one per process so no cross-process locking is needed.
    # Written to results/analysis/worker_logs/<pid>.log.
    log_dir  = RESULTS_DIR / "analysis" / "worker_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{os.getpid()}.log"

    all_findings: list[dict] = []
    files_scanned = 0
    t0 = _time.monotonic()

    with open(log_path, "a", buffering=1) as log:
        log.write(f"\n=== {repo_name} ===\n")
        for file_path, rel_path in iter_source_files(local_path):
            files_scanned += 1
            log.write(f"  [{files_scanned}] {rel_path}\n")
            for finding in analyze_file(file_path, rel_path):
                finding["repo"] = repo_name
                all_findings.append(finding)
        elapsed = _time.monotonic() - t0
        log.write(f"  done — {files_scanned} files, {len(all_findings)} findings, {elapsed:.1f}s\n")

    score_record = {
        "repo":             repo_name,
        "url":              repo_meta.get("html_url", ""),
        "stars":            repo_meta.get("stars", 0),
        "language":         repo_meta.get("language", ""),
        "created_at":       repo_meta.get("created_at", ""),
        "found_by_queries": repo_meta.get("matched_queries", []),
        **score_repo(all_findings),
    }
    return all_findings, score_record


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _dedup_records(records: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    """Return records with duplicates removed, keeping the first occurrence."""
    seen_keys:      set[tuple] = set()
    unique_records: list[dict] = []
    for record in records:
        key = tuple(record.get(field) for field in key_fields)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_records.append(record)
    return unique_records


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
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _ensure_nltk_data()

    manifest_path = RESULTS_DIR / "cloned" / "manifest.json"
    if not manifest_path.exists():
        console.print("[red]No clone manifest found. Run clone.py first.[/]")
        return

    with open(manifest_path) as fh:
        manifest = json.load(fh)

    existing_findings: list[dict] = []
    existing_scores:   list[dict] = []
    if append:
        existing_findings, existing_scores = _load_existing_outputs(out_dir)

    already_done: set[str] = {s["repo"] for s in existing_scores}

    repos_to_analyse = [
        repo_entry for repo_entry in manifest.get("repos", {}).values()
        if repo_entry.get("status") in ("cloned", "refreshed", "skipped_exists")
        and repo_entry["full_name"] not in already_done
    ]
    if target_repo:
        repos_to_analyse = [
            repo_entry for repo_entry in repos_to_analyse
            if repo_entry["full_name"] == target_repo
        ]
        if not repos_to_analyse:
            already = " (already analysed)" if target_repo in already_done else ""
            console.print(f"[red]Repo '{target_repo}' not found in manifest{already}.[/]")
            return

    import os
    effective_workers = workers or os.cpu_count() or 4
    skipped_msg = f"  ([dim]{len(already_done)} already done, skipping[/])" if already_done else ""
    console.print(f"\n[bold]{len(repos_to_analyse)}[/] repos to analyse  (processes={effective_workers}){skipped_msg}")
    console.print(f"  [dim]Per-file progress: tail results/analysis/worker_logs/<pid>.log[/]\n")

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
        progress_task = progress.add_task("Analysing…", total=len(repos_to_analyse))

        with ProcessPoolExecutor(max_workers=effective_workers) as executor:
            future_to_repo = {
                executor.submit(_analyse_repo, repo_entry): repo_entry
                for repo_entry in repos_to_analyse
            }

            for future in as_completed(future_to_repo):
                repo_entry = future_to_repo[future]
                repo_name  = repo_entry["full_name"]
                findings, score_record = future.result()

                if score_record is not None:
                    new_findings.extend(findings)
                    new_scores.append(score_record)

                    if cleanup:
                        local_path = Path(repo_entry["local_path"])
                        if local_path.exists():
                            shutil.rmtree(local_path)
                        manifest["repos"][repo_name]["status"] = "cleaned"

                progress.update(progress_task, description=f"[cyan]{repo_name[:50]}[/]", advance=1)

    if cleanup:
        with open(manifest_path, "w") as fh:
            json.dump(manifest, fh, indent=2)

    combined_findings = _dedup_records(
        existing_findings + new_findings,
        ("repo", "file", "line", "id"),
    )
    scores_by_repo: dict[str, dict] = {score["repo"]: score for score in existing_scores}
    for score_record in new_scores:
        scores_by_repo[score_record["repo"]] = score_record

    combined_scores = [
        score for score in scores_by_repo.values()
        if score["score"] >= min_score
    ]

    with open(out_dir / "findings.json", "w") as fh:
        json.dump(combined_findings, fh, indent=2)
    with open(out_dir / "repo_scores.json", "w") as fh:
        json.dump(combined_scores, fh, indent=2)

    repos_with_signal = sum(
        1 for score in scores_by_repo.values()
        if score.get("classification") != "none"
    )
    console.print(
        f"\n[bold green]Done.[/]  "
        f"[cyan]{len(scores_by_repo)}[/] repos  •  "
        f"[cyan]{repos_with_signal}[/] with MT signal  •  "
        f"[cyan]{len(combined_findings)}[/] total findings\n"
        f"Output: [dim]{out_dir}[/]"
    )


def main() -> None:
    default_out = RESULTS_DIR / "analysis"
    parser = argparse.ArgumentParser(description="Phase 3: analyse cloned repos for MT patterns")
    parser.add_argument("--repo",           default=None,        help="Analyse a single repo (owner/name)")
    parser.add_argument("--min-score",      type=int, default=0)
    parser.add_argument("--output-dir",     type=Path, default=default_out)
    parser.add_argument("--workers",        type=int, default=None, help="Parallel worker processes (default: all CPU cores)")
    parser.add_argument("--append",         action="store_true", help="Merge with existing outputs")
    parser.add_argument("--cleanup-clones", action="store_true", help="Delete each clone after analysis")
    args = parser.parse_args()

    run(args.repo, args.min_score, args.output_dir, args.workers, args.append, args.cleanup_clones)


if __name__ == "__main__":
    main()
