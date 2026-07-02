"""
Phase 3 — Local Analysis
=========================
Walks each cloned repo and scans source files for both explicit MT usage
(direct library imports / class names) and implicit MT patterns (structural
heuristics defined in config.py).

Produces a rich report in results/analysis/:
  - findings.json      — per-file findings with line numbers and snippets
  - repo_scores.json   — per-repo aggregated scores and classification
  - summary_report.md  — human-readable markdown summary

Usage:
    python analyze.py [--repo FULL_NAME] [--only explicit|implicit|both]
                      [--min-score N] [--output-dir PATH]

    --repo FULL_NAME   Analyse a single repo only (e.g. owner/name)
    --only             Run only explicit or only implicit checks
    --min-score N      Only include repos with score >= N in the report
    --output-dir       Override the output directory (default: results/analysis/)
"""

import argparse
import json
import re
import shutil
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from config import (
    RESULTS_DIR,
    REPOS_DIR,
    ANALYSIS_EXTENSIONS,
    SKIP_DIRS,
    IMPLICIT_PATTERNS,
)

console = Console()

# ---------------------------------------------------------------------------
# Explicit patterns — these are compiled once at import time
# ---------------------------------------------------------------------------

EXPLICIT_PATTERNS: list[dict] = [
    # Library / framework imports
    {"id": "import_metamorphic",   "label": "Import: metamorphic*",          "regex": re.compile(r"^\s*(import|from)\s+metamorphic", re.MULTILINE)},
    {"id": "import_pytest_mt",     "label": "Import: pytest-metamorphic",    "regex": re.compile(r"pytest[_-]metamorphic", re.MULTILINE)},
    {"id": "import_mt_testing",    "label": "Import: mt_testing",            "regex": re.compile(r"(import|from)\s+mt_testing", re.MULTILINE)},
    {"id": "import_hypothesis_mt", "label": "Import: hypothesis_metamorphic","regex": re.compile(r"hypothesis_metamorphic", re.MULTILINE)},
    # Class / decorator names
    {"id": "class_MetamorphicTest",     "label": "Class: MetamorphicTest*",      "regex": re.compile(r"\bMetamorphicTest\w*\b")},
    {"id": "class_MetamorphicRelation", "label": "Class: MetamorphicRelation*",  "regex": re.compile(r"\bMetamorphicRelation\w*\b")},
    {"id": "decorator_metamorphic",     "label": "Decorator: @metamorphic",      "regex": re.compile(r"@metamorphic\b")},
    # Java-style
    {"id": "java_MetamorphicTesting",   "label": "Java: MetamorphicTesting",     "regex": re.compile(r"\bMetamorphicTesting\b")},
    {"id": "java_org_mt",               "label": "Java: org.metamorphictesting", "regex": re.compile(r"org\.metamorphictesting")},
    # String / comment references
    {"id": "string_mt",  "label": 'String: "metamorphic testing"',   "regex": re.compile(r'"[Mm]etamorphic\s+[Tt]esting"')},
    {"id": "string_mr",  "label": 'String: "metamorphic relation"',  "regex": re.compile(r'"[Mm]etamorphic\s+[Rr]elation"')},
    {"id": "comment_mt", "label": "Comment: metamorphic testing",    "regex": re.compile(r"#.*metamorphic\s+testing|//.*metamorphic\s+testing", re.IGNORECASE)},
    {"id": "comment_mr", "label": "Comment: metamorphic relation",   "regex": re.compile(r"#.*metamorphic\s+relation|//.*metamorphic\s+relation", re.IGNORECASE)},
    # Function-naming conventions from MT literature
    {"id": "fn_mr_prefix",    "label": "Fn: def mr_*()",     "regex": re.compile(r"\bdef\s+mr_\w+\s*\(")},
    {"id": "fn_check_mr",     "label": "Fn: def check_mr*",  "regex": re.compile(r"\bdef\s+check_mr\w*\s*\(")},
    {"id": "fn_follow_up",    "label": "Fn: def follow_up*", "regex": re.compile(r"\bdef\s+follow_up\w*\s*\(")},
    {"id": "java_testMR",     "label": "Java fn: testMR*()", "regex": re.compile(r"\bvoid\s+testMR\w*\s*\(")},
]

# Compile implicit patterns
_COMPILED_IMPLICIT: list[dict] = [
    {**p, "regex": re.compile(p["pattern"], re.MULTILINE | re.IGNORECASE)}
    for p in IMPLICIT_PATTERNS
]


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------

def iter_source_files(repo_path: Path):
    """Yield (path, relative_path) for all analysable source files."""
    for p in repo_path.rglob("*"):
        if not p.is_file():
            continue
        # Skip unwanted directories
        if any(skip in p.parts for skip in SKIP_DIRS):
            continue
        if p.suffix not in ANALYSIS_EXTENSIONS:
            continue
        yield p, p.relative_to(repo_path)


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------

def _snippet(text: str, match: re.Match, context: int = 1) -> str:
    """Return the matched line plus `context` lines of surrounding context."""
    lines = text.splitlines()
    line_no = text[:match.start()].count("\n")
    start = max(0, line_no - context)
    end   = min(len(lines), line_no + context + 1)
    return "\n".join(lines[start:end]).strip()


def analyze_file(file_path: Path, rel_path: Path, mode: str) -> list[dict]:
    """Return a list of finding dicts for one file."""
    try:
        text = file_path.read_text(errors="replace")
    except Exception:
        return []

    findings: list[dict] = []

    if mode in ("explicit", "both"):
        for pat in EXPLICIT_PATTERNS:
            for m in pat["regex"].finditer(text):
                line_no = text[:m.start()].count("\n") + 1
                findings.append({
                    "kind":    "explicit",
                    "pattern_id":    pat["id"],
                    "pattern_label": pat["label"],
                    "file":    str(rel_path),
                    "line":    line_no,
                    "snippet": _snippet(text, m),
                })

    if mode in ("implicit", "both"):
        for pat in _COMPILED_IMPLICIT:
            # Only apply implicit checks to test files (heuristic)
            name_lower = rel_path.name.lower()
            is_test_file = (
                "test" in name_lower or
                "spec" in name_lower or
                name_lower.startswith("test_") or
                name_lower.endswith("_test.py")
            )
            if not is_test_file:
                continue
            for m in pat["regex"].finditer(text):
                line_no = text[:m.start()].count("\n") + 1
                findings.append({
                    "kind":    "implicit",
                    "pattern_id":    pat["id"],
                    "pattern_label": pat["label"],
                    "note":          pat.get("note", ""),
                    "file":    str(rel_path),
                    "line":    line_no,
                    "snippet": _snippet(text, m),
                })

    return findings


# ---------------------------------------------------------------------------
# Per-repo scoring
# ---------------------------------------------------------------------------

def score_repo(findings: list[dict]) -> dict:
    """
    Compute a simple score:
      - Each explicit hit    = 3 points
      - Each implicit hit    = 1 point
    Cap at 100. Also return a classification string.
    """
    explicit_count = sum(1 for f in findings if f["kind"] == "explicit")
    implicit_count = sum(1 for f in findings if f["kind"] == "implicit")
    raw = explicit_count * 3 + implicit_count
    score = min(raw, 100)

    if explicit_count >= 3:
        classification = "strong_explicit"
    elif explicit_count >= 1:
        classification = "weak_explicit"
    elif implicit_count >= 5:
        classification = "strong_implicit"
    elif implicit_count >= 1:
        classification = "weak_implicit"
    else:
        classification = "none"

    affected_files = len({f["file"] for f in findings})
    pattern_ids    = list({f["pattern_id"] for f in findings})

    return {
        "explicit_hits":  explicit_count,
        "implicit_hits":  implicit_count,
        "score":          score,
        "classification": classification,
        "affected_files": affected_files,
        "pattern_ids":    pattern_ids,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def write_markdown_report(repo_scores: list[dict], out_dir: Path) -> None:
    lines: list[str] = [
        "# Metamorphic Testing — GitHub Mining Analysis Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary",
        "",
        f"- Total repos analysed: **{len(repo_scores)}**",
        f"- Strong explicit: **{sum(1 for r in repo_scores if r['classification'] == 'strong_explicit')}**",
        f"- Weak explicit:   **{sum(1 for r in repo_scores if r['classification'] == 'weak_explicit')}**",
        f"- Strong implicit: **{sum(1 for r in repo_scores if r['classification'] == 'strong_implicit')}**",
        f"- Weak implicit:   **{sum(1 for r in repo_scores if r['classification'] == 'weak_implicit')}**",
        f"- No MT signal:    **{sum(1 for r in repo_scores if r['classification'] == 'none')}**",
        "",
        "## Classification scale",
        "",
        "| Class | Meaning |",
        "|---|---|",
        "| `strong_explicit` | ≥3 direct MT library/class/decorator matches |",
        "| `weak_explicit`   | 1–2 direct matches |",
        "| `strong_implicit` | No direct matches but ≥5 structural heuristic hits in test files |",
        "| `weak_implicit`   | 1–4 structural heuristic hits |",
        "| `none`            | No signal found |",
        "",
        "## Top repos by score",
        "",
        "| Repo | Score | Class | Explicit | Implicit | Files |",
        "|---|---|---|---|---|---|",
    ]

    for r in sorted(repo_scores, key=lambda x: x["score"], reverse=True)[:50]:
        lines.append(
            f"| [{r['full_name']}]({r.get('html_url','')}) "
            f"| {r['score']} | `{r['classification']}` "
            f"| {r['explicit_hits']} | {r['implicit_hits']} | {r['affected_files']} |"
        )

    lines += [
        "",
        "## Pattern hit distribution",
        "",
        "| Pattern ID | Label | Total hits |",
        "|---|---|---|",
    ]

    pattern_totals: dict[str, dict] = {}
    for r in repo_scores:
        for pid in r.get("pattern_ids", []):
            pattern_totals.setdefault(pid, {"id": pid, "count": 0})
            pattern_totals[pid]["count"] += 1

    all_pats = {**{p["id"]: p["label"] for p in EXPLICIT_PATTERNS},
                **{p["id"]: p["label"] for p in IMPLICIT_PATTERNS}}

    for pid, info in sorted(pattern_totals.items(), key=lambda x: -x[1]["count"]):
        lines.append(f"| `{pid}` | {all_pats.get(pid, '')} | {info['count']} |")

    report_path = out_dir / "summary_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"Markdown report: [dim]{report_path}[/]")


def _dedup_records(records: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for record in records:
        key = tuple(record.get(field) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _load_existing_outputs(out_dir: Path) -> tuple[list[dict], list[dict]]:
    findings_path = out_dir / "findings.json"
    scores_path = out_dir / "repo_scores.json"

    existing_findings: list[dict] = []
    existing_scores: list[dict] = []

    if findings_path.exists():
        with open(findings_path) as f:
            existing_findings = json.load(f)

    if scores_path.exists():
        with open(scores_path) as f:
            existing_scores = json.load(f)

    return existing_findings, existing_scores


def _cleanup_repo(local_path: Path, manifest: dict, full_name: str) -> None:
    if local_path.exists():
        shutil.rmtree(local_path)

    repo_entry = manifest.setdefault("repos", {}).setdefault(full_name, {})
    repo_entry["status"] = "cleaned"
    repo_entry["cleaned_at"] = datetime.now(timezone.utc).isoformat()
    repo_entry["local_path"] = str(local_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(target_repo: str | None, mode: str, min_score: int, out_dir: Path, append: bool, cleanup: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = RESULTS_DIR / "cloned" / "manifest.json"
    if not manifest_path.exists():
        console.print("[red]No clone manifest found. Run clone.py first.[/]")
        return

    with open(manifest_path) as f:
        manifest = json.load(f)

    existing_findings: list[dict] = []
    existing_scores: list[dict] = []
    if append:
        existing_findings, existing_scores = _load_existing_outputs(out_dir)

    repos = list(manifest.get("repos", {}).values())
    repos = [r for r in repos if r.get("status") in ("cloned", "refreshed", "skipped_exists")]

    if target_repo:
        repos = [r for r in repos if r["full_name"] == target_repo]
        if not repos:
            console.print(f"[red]Repo '{target_repo}' not found in manifest.[/]")
            return

    console.print(f"\n[bold]{len(repos)}[/] repos to analyse (mode={mode})\n")

    all_findings: list[dict] = []
    repo_scores: list[dict]  = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Analysing…", total=len(repos))

        for repo_meta in repos:
            full_name = repo_meta["full_name"]
            local_path = Path(repo_meta["local_path"])
            progress.update(task, description=f"[cyan]{full_name[:50]}[/]")

            if not local_path.exists():
                progress.advance(task)
                continue

            repo_findings: list[dict] = []
            for file_path, rel_path in iter_source_files(local_path):
                file_findings = analyze_file(file_path, rel_path, mode)
                for ff in file_findings:
                    ff["repo"] = full_name
                repo_findings.extend(file_findings)

            all_findings.extend(repo_findings)
            sc = score_repo(repo_findings)
            repo_scores.append({
                "full_name":      full_name,
                "html_url":       repo_meta.get("html_url", ""),
                "stars":          repo_meta.get("stars", 0),
                "language":       repo_meta.get("language", ""),
                **sc,
            })

            if cleanup:
                _cleanup_repo(local_path, manifest, full_name)
            progress.advance(task)

    # Merge with any existing outputs when running in batch mode.
    combined_findings = existing_findings + all_findings
    combined_scores = existing_scores + repo_scores

    combined_findings = _dedup_records(
        combined_findings,
        ("repo", "file", "line", "pattern_id", "kind"),
    )
    combined_scores_by_repo: dict[str, dict] = {}
    for record in combined_scores:
        combined_scores_by_repo[record["full_name"]] = record

    repo_scores_filtered = [r for r in combined_scores_by_repo.values() if r["score"] >= min_score]

    # Write outputs
    findings_path = out_dir / "findings.json"
    scores_path   = out_dir / "repo_scores.json"

    with open(findings_path, "w") as f:
        json.dump(combined_findings, f, indent=2)
    with open(scores_path, "w") as f:
        json.dump(repo_scores_filtered, f, indent=2)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    write_markdown_report(repo_scores_filtered, out_dir)

    total_with_signal = sum(1 for r in combined_scores_by_repo.values() if r["classification"] != "none")
    console.print(
        f"\n[bold green]Done.[/]  "
        f"[cyan]{len(combined_scores_by_repo)}[/] repos  •  "
        f"[cyan]{total_with_signal}[/] with MT signal  •  "
        f"[cyan]{len(combined_findings)}[/] total findings\n"
        f"Output: [dim]{out_dir}[/]"
    )


def main() -> None:
    default_out = RESULTS_DIR / "analysis"
    parser = argparse.ArgumentParser(description="Phase 3: analyse cloned repos for MT patterns")
    parser.add_argument("--repo",        default=None, help="Analyse a single repo (owner/name)")
    parser.add_argument("--only",        choices=["explicit", "implicit", "both"], default="both")
    parser.add_argument("--min-score",   type=int, default=0)
    parser.add_argument("--output-dir",  type=Path, default=default_out)
    parser.add_argument("--append",      action="store_true", help="Append to existing analysis outputs")
    parser.add_argument("--cleanup-clones", action="store_true", help="Delete each cloned repo after analysis")
    args = parser.parse_args()

    run(args.repo, args.only, args.min_score, args.output_dir, args.append, args.cleanup_clones)


if __name__ == "__main__":
    main()
