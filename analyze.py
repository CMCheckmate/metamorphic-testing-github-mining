"""
Phase 3 — Local Analysis
=========================
Walks each cloned repo and scans every file for explicit MT adoption signals.

Produces a rich report in results/analysis/:
  - findings.json      — per-file findings with line numbers and snippets
  - repo_scores.json   — per-repo aggregated scores and classification
  - summary_report.md  — human-readable markdown summary

Usage:
    python analyze.py [--repo FULL_NAME] [--min-score N]
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from config import (
    RESULTS_DIR,
    REPOS_DIR,
    ANALYSIS_EXTENSIONS,
    SKIP_DIRS,
)

console = Console()

# ---------------------------------------------------------------------------
# Lemmatization setup (used for normalised comment/doc matching)
# ---------------------------------------------------------------------------

try:
    import nltk
    from nltk.stem import WordNetLemmatizer
    from nltk.tokenize import RegexpTokenizer

    for _pkg in ("wordnet", "omw-1.4"):
        try:
            nltk.data.find(f"corpora/{_pkg}")
        except LookupError:
            nltk.download(_pkg, quiet=True)

    _lemmatizer = WordNetLemmatizer()
    _word_tok = RegexpTokenizer(r"[a-zA-Z]+")
    _LEMMATIZE_AVAILABLE = True

except ImportError:
    _LEMMATIZE_AVAILABLE = False


def _lemmatize_text(text: str) -> str:
    """
    Return a whitespace-joined string of lemmatized alphabetic tokens.
    Used to preprocess comment/docstring text so morphological variants
    (e.g. 'metamorphically', 'relationships') are normalised before matching.
    Falls back to lowercased original text if NLTK is unavailable.
    """
    if not _LEMMATIZE_AVAILABLE:
        return text.lower()
    tokens = _word_tok.tokenize(text)
    return " ".join(_lemmatizer.lemmatize(t.lower()) for t in tokens)


# Extracts comment lines and docstring blocks for the lemmatised pass
_COMMENT_LINE_RE = re.compile(
    r"(?:#[^\n]*|//[^\n]*|\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?''')",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Explicit patterns — compiled once at import time
# ---------------------------------------------------------------------------

EXPLICIT_PATTERNS: list[dict] = [
    # Import patterns — any module whose name contains "metamorphic"
    # (user-defined modules or future libraries following MT naming conventions).
    # We do NOT search for specific library names whose names do not contain
    # "metamorphic", even if we know they are MT libraries (e.g. gemtest).
    # Searching by opaque library name is a form of implicit search: it relies
    # on out-of-band knowledge that the name maps to MT, misses any library
    # with a different opaque name, and would be caught anyway by the
    # string/comment patterns below if the library documents itself with MT
    # terminology.
    {"id": "import_metamorphic",        "label": "Import: metamorphic*",         "regex": re.compile(r"^\s*(import|from)\s+metamorphic", re.MULTILINE)},
    # User-defined class / decorator names
    {"id": "class_MetamorphicTest",     "label": "Class: MetamorphicTest*",      "regex": re.compile(r"\bMetamorphicTest\w*\b")},
    {"id": "class_MetamorphicRelation", "label": "Class: MetamorphicRelation*",  "regex": re.compile(r"\bMetamorphicRelation\w*\b")},
    {"id": "decorator_metamorphic",     "label": "Decorator: @metamorphic",      "regex": re.compile(r"@metamorphic\b")},
    # String literal references
    {"id": "string_mt",  "label": 'String: "metamorphic testing[s]?"',  "regex": re.compile(r'"[Mm]etamorphic\s+[Tt]estings?"')},
    {"id": "string_mr",  "label": 'String: "metamorphic relation[s]?"', "regex": re.compile(r'"[Mm]etamorphic\s+[Rr]elations?"')},
    # Inline comment references
    {"id": "comment_mt", "label": "Comment: metamorphic testing",       "regex": re.compile(r"(?:#|//).*metamorphic\s+testing", re.IGNORECASE)},
    {"id": "comment_mr", "label": "Comment: metamorphic relation",      "regex": re.compile(r"(?:#|//).*metamorphic\s+relations?", re.IGNORECASE)},
]

# Lemmatised patterns matched against normalised comment/docstring text
LEMMATIZED_COMMENT_PATTERNS: list[dict] = [
    {"id": "lemma_comment_mt", "label": "Comment (lemmatised): metamorphic test",     "regex": re.compile(r"\bmetamorphic\s+test\b",     re.IGNORECASE)},
    {"id": "lemma_comment_mr", "label": "Comment (lemmatised): metamorphic relation", "regex": re.compile(r"\bmetamorphic\s+relation\b",  re.IGNORECASE)},
]


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------

def iter_source_files(repo_path: Path):
    """Yield (path, relative_path) for all analysable files in the repo."""
    for p in repo_path.rglob("*"):
        if not p.is_file():
            continue
        if any(skip in p.parts for skip in SKIP_DIRS):
            continue
        if ANALYSIS_EXTENSIONS and p.suffix not in ANALYSIS_EXTENSIONS:
            continue
        yield p, p.relative_to(repo_path)


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------

def _snippet(text: str, match: re.Match, context: int = 1) -> str:
    lines = text.splitlines()
    line_no = text[:match.start()].count("\n")
    start = max(0, line_no - context)
    end   = min(len(lines), line_no + context + 1)
    return "\n".join(lines[start:end]).strip()


def analyze_file(file_path: Path, rel_path: Path) -> list[dict]:
    """Return a list of finding dicts for one file."""
    try:
        text = file_path.read_text(errors="replace")
    except Exception:
        return []

    findings: list[dict] = []

    # --- Standard explicit pattern matching ---
    for pat in EXPLICIT_PATTERNS:
        for m in pat["regex"].finditer(text):
            line_no = text[:m.start()].count("\n") + 1
            findings.append({
                "kind":          "explicit",
                "pattern_id":    pat["id"],
                "pattern_label": pat["label"],
                "file":          str(rel_path),
                "line":          line_no,
                "snippet":       _snippet(text, m),
            })

    # --- Lemmatised comment / docstring matching ---
    comment_chunks = _COMMENT_LINE_RE.findall(text)
    if comment_chunks:
        lemma_text = _lemmatize_text(" ".join(comment_chunks))
        found_ids = {f["pattern_id"] for f in findings}
        for pat in LEMMATIZED_COMMENT_PATTERNS:
            if pat["id"] in found_ids:
                continue
            if pat["regex"].search(lemma_text):
                findings.append({
                    "kind":          "explicit",
                    "pattern_id":    pat["id"],
                    "pattern_label": pat["label"],
                    "file":          str(rel_path),
                    "line":          0,
                    "snippet":       "(lemmatised comment match)",
                })

    return findings


# ---------------------------------------------------------------------------
# Per-repo scoring
# ---------------------------------------------------------------------------

def score_repo(findings: list[dict]) -> dict:
    """
    Compute a score and classification for a single repository.
      - Each explicit hit = 3 points, capped at 100.

    Classification tiers:
      strong_explicit  ≥ 3 explicit hits — multiple unambiguous MT signals
      weak_explicit    1–2 explicit hits — at least one direct signal
      none             0 explicit hits
    """
    explicit_count = sum(1 for f in findings if f["kind"] == "explicit")
    score = min(explicit_count * 3, 100)

    if explicit_count >= 3:
        classification = "strong_explicit"
    elif explicit_count >= 1:
        classification = "weak_explicit"
    else:
        classification = "none"

    return {
        "explicit_hits":  explicit_count,
        "score":          score,
        "classification": classification,
        "affected_files": len({f["file"] for f in findings}),
        "pattern_ids":    list({f["pattern_id"] for f in findings}),
    }


# ---------------------------------------------------------------------------
# Per-repo worker (called by ThreadPoolExecutor)
# ---------------------------------------------------------------------------

def _analyse_repo(repo_meta: dict) -> tuple[list[dict], dict]:
    """Walk one repo and return (findings, scored_record). Thread-safe."""
    full_name  = repo_meta["full_name"]
    local_path = Path(repo_meta["local_path"])

    if not local_path.exists():
        return [], None

    repo_findings: list[dict] = []
    for file_path, rel_path in iter_source_files(local_path):
        for ff in analyze_file(file_path, rel_path):
            ff["repo"] = full_name
            repo_findings.append(ff)

    sc = score_repo(repo_findings)
    record = {
        "full_name":       full_name,
        "html_url":        repo_meta.get("html_url", ""),
        "stars":           repo_meta.get("stars", 0),
        "language":        repo_meta.get("language", ""),
        "created_at":      repo_meta.get("created_at", ""),
        "matched_queries": repo_meta.get("matched_queries", []),
        **sc,
    }
    return repo_findings, record


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------

def _dedup_records(records: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for record in records:
        key = tuple(record.get(f) for f in key_fields)
        if key not in seen:
            seen.add(key)
            out.append(record)
    return out


def _load_existing_outputs(out_dir: Path) -> tuple[list[dict], list[dict]]:
    findings_path = out_dir / "findings.json"
    scores_path   = out_dir / "repo_scores.json"
    existing_findings: list[dict] = []
    existing_scores:   list[dict] = []
    if findings_path.exists():
        with open(findings_path) as f:
            existing_findings = json.load(f)
    if scores_path.exists():
        with open(scores_path) as f:
            existing_scores = json.load(f)
    return existing_findings, existing_scores


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    target_repo: str | None,
    min_score: int,
    out_dir: Path,
    workers: int,
    append: bool,
    cleanup: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = RESULTS_DIR / "cloned" / "manifest.json"
    if not manifest_path.exists():
        console.print("[red]No clone manifest found. Run clone.py first.[/]")
        return

    with open(manifest_path) as f:
        manifest = json.load(f)

    existing_findings: list[dict] = []
    existing_scores:   list[dict] = []
    if append:
        existing_findings, existing_scores = _load_existing_outputs(out_dir)

    repos = [
        r for r in manifest.get("repos", {}).values()
        if r.get("status") in ("cloned", "refreshed", "skipped_exists")
    ]
    if target_repo:
        repos = [r for r in repos if r["full_name"] == target_repo]
        if not repos:
            console.print(f"[red]Repo '{target_repo}' not found in manifest.[/]")
            return

    console.print(f"\n[bold]{len(repos)}[/] repos to analyse  (workers={workers})\n")

    all_findings:  list[dict] = []
    repo_scores:   list[dict] = []
    manifest_lock  = Lock()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Analysing…", total=len(repos))

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_repo = {
                executor.submit(_analyse_repo, repo_meta): repo_meta
                for repo_meta in repos
            }

            for future in as_completed(future_to_repo):
                repo_meta = future_to_repo[future]
                full_name = repo_meta["full_name"]
                findings, record = future.result()

                if record is not None:
                    all_findings.extend(findings)
                    repo_scores.append(record)

                    if cleanup:
                        local_path = Path(repo_meta["local_path"])
                        if local_path.exists():
                            shutil.rmtree(local_path)
                        with manifest_lock:
                            manifest["repos"][full_name]["status"] = "cleaned"

                progress.update(task, description=f"[cyan]{full_name[:50]}[/]", advance=1)

    if cleanup:
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    # Merge with existing outputs when appending
    combined_findings = _dedup_records(
        existing_findings + all_findings,
        ("repo", "file", "line", "pattern_id"),
    )
    combined_scores_map: dict[str, dict] = {r["full_name"]: r for r in existing_scores}
    for r in repo_scores:
        combined_scores_map[r["full_name"]] = r
    combined_scores = [r for r in combined_scores_map.values() if r["score"] >= min_score]

    # Write outputs
    with open(out_dir / "findings.json", "w") as f:
        json.dump(combined_findings, f, indent=2)
    with open(out_dir / "repo_scores.json", "w") as f:
        json.dump(combined_scores, f, indent=2)

    total_signal = sum(1 for r in combined_scores_map.values() if r["classification"] != "none")
    console.print(
        f"\n[bold green]Done.[/]  "
        f"[cyan]{len(combined_scores_map)}[/] repos  •  "
        f"[cyan]{total_signal}[/] with MT signal  •  "
        f"[cyan]{len(combined_findings)}[/] total findings\n"
        f"Output: [dim]{out_dir}[/]"
    )


def main() -> None:
    default_out = RESULTS_DIR / "analysis"
    parser = argparse.ArgumentParser(description="Phase 3: analyse cloned repos for explicit MT patterns")
    parser.add_argument("--repo",            default=None,          help="Analyse a single repo (owner/name)")
    parser.add_argument("--min-score",       type=int, default=0)
    parser.add_argument("--output-dir",      type=Path, default=default_out)
    parser.add_argument("--workers",         type=int, default=4,   help="Parallel worker threads (default: 4)")
    parser.add_argument("--append",          action="store_true",   help="Merge with existing outputs")
    parser.add_argument("--cleanup-clones",  action="store_true",   help="Delete each clone after analysis")
    args = parser.parse_args()

    run(args.repo, args.min_score, args.output_dir, args.workers, args.append, args.cleanup_clones)


if __name__ == "__main__":
    main()
