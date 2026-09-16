"""
Non-Code Analysis Phase
=======================
Analyses metadata and body text from non-code search surfaces:
  repos, commits (metadata only), prs, issues, discussions

No cloning. Applies analysis keywords to title + body text.
Extracts domain signals and word frequencies.

Output:
  results/<slug>/analysis/noncode_results.json
  results/<slug>/analysis/noncode_history.json
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from tqdm import tqdm

import config as cfg
from utils import (
    technique_dirs, ensure_dirs,
    setup_logging, load_json, save_json,
    load_analysis_keywords, compile_analysis_keywords,
)

NON_CODE_SURFACES = ["repos", "commits", "prs", "issues", "discussions"]


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Strip Markdown syntax, URLs, code blocks for word-cloud text."""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)
    text = re.sub(r"\[.*?\]\(.*?\)", " ", text)
    text = re.sub(r"[#*_~>|`]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_stopwords(logger=None) -> frozenset[str]:
    """
    Load base stopwords from the wordcloud library if installed, else use a
    manual fallback. Adds custom domain-noise words on top of either base.
    """
    try:
        from wordcloud import STOPWORDS
        base = set(STOPWORDS)
        if logger:
            logger.info(f"Stopwords loaded from wordcloud library ({len(base)} words)")
    except ImportError:
        base = {
            "the", "and", "for", "are", "this", "with", "that", "from",
            "have", "has", "not", "can", "will", "its", "but", "was",
            "they", "you", "your", "our", "all", "any", "more", "also",
            "into", "use", "used", "using", "which", "when", "each",
            "some", "been", "one", "new", "how", "get", "may", "out",
            "per", "way", "set", "add", "run", "now", "via", "would",
            "could", "should", "there", "these", "those", "then", "than",
            "them", "their", "what", "just", "make", "like", "want",
            "about", "after", "before", "between", "other", "over",
            "only", "same", "does", "did", "had", "where", "while",
            "very", "such", "both", "even", "most", "much", "need",
            "take", "made", "good", "also", "back", "give", "well",
        }
        if logger:
            logger.warning(
                "wordcloud library not installed — using manual stopword fallback. "
                "Install wordcloud for a fuller stopword list: pip install wordcloud"
            )

    base.update({
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

        # --- Generic English verbs (top 100 noise confirmed) ---
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
        "claude", "anthropic", "noreply",

        # --- Reference / generic nouns ---
        "reference", "identity", "production", "integration",
        "execution", "harness", "surface", "schema",
        "agent", "agents", "decision", "rule", "field", "point",
        "text", "list", "dict", "args", "docs", "spec",

        # --- Common English words absent from wordcloud's 192-word built-in STOPWORDS ---
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

        # --- Confirmed noise from frequency analysis (>12% of repos, no domain value) ---
        # Numbers as words
        "four", "second",
        # Git / CI noise
        "feat", "silently", "audit", "status", "documented",
        # Generic adjectives / adverbs
        "different", "complete", "correct", "live", "changed",
        "specific", "known", "free", "shared", "final", "nothing",
        "green",
        # Generic verbs (forms not already covered)
        "uses", "fails", "passes", "makes", "keep", "call", "calls",
        "claim", "claims",
        # Generic nouns
        "json", "multi", "separate", "wrong", "table", "record",
        "next", "mode", "gap", "phase", "documentation",
        "block", "public", "content", "names", "base", "reports",
        "count", "will",

        # --- Already-missing basic dev vocab (unfiltered at 500+ freq) ---
        "fix", "fixed", "fixes",
        "bug",
        "error", "errors",
        "values",

        # --- Generic test outcomes (universal across ALL testing repos) ---
        "fail", "failed",

        # --- Generic code-level terms (300–500 freq, no domain signal) ---
        "empty", "layer", "dependency",
        "written", "write", "returns", "requires", "exists",
        "include", "checked", "removed", "named", "adding",
        "made", "measured", "recorded", "whether",

        # --- Generic nouns (300–500 freq) ---
        "loop", "post", "document", "problem", "cost", "part",
        "row", "form", "hand", "task", "comment", "total",
        "side", "readme", "metadata", "index", "counts",
        "examples", "features",

        # --- Generic adjectives / adverbs / prepositions ---
        "directly", "inside", "start", "actually", "within",
        "stays", "whose", "five", "even", "actual", "distinct",
        "independently", "deliberately", "hard", "finding",
        "closes", "done", "want", "fine", "good", "things",
        "working", "show", "help", "much", "know",

        # --- Domain-agnostic testing vocabulary ---
        "evaluation", "quality", "research", "tdd",

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

    if logger:
        logger.info(f"Total stopwords after custom additions: {len(base)}")

    return frozenset(base)


def _build_technique_stopwords(slug: str) -> frozenset[str]:
    """
    Extract individual words from the technique's search keyword file so they
    are suppressed in the word cloud. We already know the technique is present.
    e.g. '"metamorphic testing"' -> {"metamorphic", "testing"}
    """
    from utils import load_search_keywords
    words: set[str] = set()
    for kw in load_search_keywords(slug):
        clean = kw.strip('"').strip("'").lower()
        for part in re.split(r"[\s_@]+", clean):
            part = re.sub(r"[^a-z]", "", part)
            if len(part) >= 3:
                words.add(part)
    return frozenset(words)


def _word_set(
    text: str,
    stopwords: frozenset[str],
    extra_stopwords: frozenset[str] = frozenset(),
) -> set[str]:
    """
    Return the set of distinct content words in text.
    Words must be at least 3 characters, letters only.
    Applies base stopwords + technique-specific extras.
    """
    all_stops = stopwords | extra_stopwords
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in all_stops}


# ---------------------------------------------------------------------------
# Keyword matching on text
# ---------------------------------------------------------------------------

def _apply_keywords(
    text: str,
    compiled_kws: list[dict],
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Returns (general_hits, specific_hits) both keyed by keyword id.
    Only general_test and specific_technique categories count.
    """
    general: dict[str, int] = defaultdict(int)
    specific: dict[str, int] = defaultdict(int)

    if not text:
        return dict(general), dict(specific)

    for line in text.splitlines():
        for kw in compiled_kws:
            cat = kw["category"]
            if cat == "test_file_detection":
                continue
            if kw["compiled"].search(line):
                if cat == "general_test":
                    general[kw["id"]] += 1
                else:
                    specific[kw["id"]] += 1

    return dict(general), dict(specific)


# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------

def _detect_domains(text: str) -> list[str]:
    text_lower = text.lower()
    return [
        domain for domain, keywords in cfg.DOMAIN_KEYWORDS.items()
        if any(kw in text_lower for kw in keywords)
    ]


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------

def run(slug: str, restart: bool = False, no_size_stats: bool = False) -> None:
    ensure_dirs(slug)
    dirs = technique_dirs(slug)
    logger = setup_logging(slug, "noncode_analysis")

    analysis_dir = dirs["analysis"]
    analysis_dir.mkdir(parents=True, exist_ok=True)

    history_path = analysis_dir / "noncode_history.json"
    results_path = analysis_dir / "noncode_results.json"

    if restart:
        logger.info("--restart: clearing non-code analysis files")
        for p in (history_path, results_path):
            if p.exists():
                p.unlink()

    history: set = set(load_json(history_path, []))
    results: list[dict] = load_json(results_path, [])

    keywords_raw = load_analysis_keywords(slug)
    compiled_kws = compile_analysis_keywords(keywords_raw)
    kw_labels    = {k["id"]: k["label"] for k in keywords_raw}

    base_stopwords      = _load_stopwords(logger)
    technique_stopwords = _build_technique_stopwords(slug)

    for surface in NON_CODE_SURFACES:
        surface_file = dirs["search"] / f"{surface}.json"
        if not surface_file.exists():
            logger.info(f"SKIP {surface}: file not found")
            continue

        items: list[dict] = load_json(surface_file, [])
        logger.info(f"Processing {len(items)} {surface} items")

        for item in tqdm(items, desc=surface, unit="item"):
            result_id = str(item.get("id", ""))
            if not result_id:
                continue

            history_key = f"{surface}:{result_id}"
            if history_key in history:
                continue

            title = item.get("title", "") or ""
            body  = item.get("body",  "") or ""
            full_text = f"{title}\n{body}"

            general_hits, specific_hits = _apply_keywords(full_text, compiled_kws)

            # Resolve hit labels for readability
            specific_hits_labeled = {
                kw_labels.get(kid, kid): cnt
                for kid, cnt in specific_hits.items()
            }

            clean    = _clean_text(full_text)
            word_set = sorted(_word_set(clean, base_stopwords, technique_stopwords))
            domains  = _detect_domains(full_text)

            record = {
                "id":             result_id,
                "surface":        surface,
                "url":            item.get("url", "") or item.get("html_url", ""),
                "html_url":       item.get("html_url", ""),
                "title":          title[:500],
                "repo_full_name": item.get("repo_full_name", ""),
                "created_at":     item.get("created_at"),
                "updated_at":     item.get("updated_at"),
                "stars":          item.get("stars"),
                "language":       item.get("language"),
                "topics":         item.get("topics", []),
                "matched_keyword": item.get("matched_keyword", ""),
                "total_general_hits":  sum(general_hits.values()),
                "total_specific_hits": sum(specific_hits.values()),
                "hits_by_keyword":     specific_hits_labeled,
                "domains":             domains,
                "word_set":            word_set,
            }
            results.append(record)
            history.add(history_key)

            # Save incrementally every 100 items
            if len(results) % 100 == 0:
                save_json(results_path, results)
                save_json(history_path, list(history))
                logger.info(f"Saved {len(results)} non-code results")

    save_json(results_path, results)
    save_json(history_path, list(history))

    print(f"\nNon-code analysis complete: {len(results)} items processed.")
    logger.info(f"Non-code analysis done: {len(results)} items")

    if not no_size_stats:
        from analysis import fetch_cloned_repo_metadata
        fetch_cloned_repo_metadata(slug, cfg.GITHUB_TOKEN, logger)
