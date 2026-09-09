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


def _word_freq(text: str, top_n: int = 100) -> dict[str, int]:
    words = re.findall(r"[a-z][a-z_\-]{2,}", text.lower())
    stopwords = {
        "the", "and", "for", "are", "this", "with", "that", "from", "have",
        "has", "not", "can", "will", "its", "but", "was", "they", "you",
        "your", "our", "all", "any", "more", "also", "into", "use", "used",
        "using", "based", "which", "when", "each", "some", "been", "one",
        "two", "three", "new", "well", "how", "get", "may", "see", "here",
        "out", "per", "way", "set", "add", "run", "now", "via",
    }
    counts = Counter(w for w in words if w not in stopwords)
    return dict(counts.most_common(top_n))


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

def run(slug: str, restart: bool = False) -> None:
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

    all_wordcloud_text: list[str] = []

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

            clean = _clean_text(full_text)
            all_wordcloud_text.append(clean)
            word_freq = _word_freq(clean)
            domains   = _detect_domains(full_text)

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
                "word_freq":           word_freq,
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

    # Save aggregated word cloud text
    wc_path = analysis_dir / "wordcloud_text.txt"
    wc_path.write_text(" ".join(all_wordcloud_text), encoding="utf-8")

    print(f"\nNon-code analysis complete: {len(results)} items processed.")
    logger.info(f"Non-code analysis done: {len(results)} items")
