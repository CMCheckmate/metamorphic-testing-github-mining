"""
Technique keyword matching shared by code_specialised_analysis.py (code files) and
sections_aggregate.py (non-code titles/bodies), so both apply identical rules.

Rules (from inputs/<prefix>_analysis_keywords.json, `specific_technique` entries):
  * one hit = one line matching one keyword regex;
  * keywords with `split_first` / `split_second` also count a phrase wrapped over
    two lines (first line ends with the first word, next line starts with the
    second) as one hit on the first line;
  * keywords with `subset_of` only match lines their parent matches; they are
    kept per keyword but excluded from `total()`.
"""

from __future__ import annotations

import re

from core_helpers.utils import load_analysis_keywords, compile_analysis_keywords

# Literal (case-insensitive) that every technique regex needs. Files/texts without it
# cannot hit, so they are skipped cheaply (used as the `git grep -F` prefilter).
PREFILTER = {
    "metamorphic_testing":    ["metamorphic"],
    # A phrase wrapped after "property-based" still has the literal on its first line, which
    # is where the split rule records the hit (a wrap between "property" and "based" is missed).
    "property_based_testing": ["property-based", "property based"],
    "fuzz_testing":           ["fuzz"],
}


_COMMENT_PREFIX = "(?:#|//).*"
_COMMENT_MARK = re.compile(r"#|//")


def _comment_search(tail: re.Pattern, line: str) -> bool:
    """Same result as re.search('(?:#|//).*' + tail, line), in linear time: the pattern matches
    iff `tail` matches somewhere after the first comment marker. The regex form backtracks from
    every '#' / '//' and is quadratic on long lines (minified JS / data files with many URLs
    took hours and froze the scan)."""
    m = _COMMENT_MARK.search(line)
    return bool(m and tail.search(line, m.end()))


class TechniqueMatcher:
    def __init__(self, slug: str) -> None:
        kws = [k for k in compile_analysis_keywords(load_analysis_keywords(slug))
               if k["category"] == "specific_technique"]
        flags_of = lambda k: re.IGNORECASE if "IGNORECASE" in k.get("flags", "") else 0
        for k in kws:                                  # "comment: …" keywords → linear-time check
            if k["regex"].startswith(_COMMENT_PREFIX):
                k["_comment_tail"] = re.compile(k["regex"][len(_COMMENT_PREFIX):], flags_of(k))
        self.keywords = kws
        self.labels   = {k["id"]: k.get("label", k["id"]) for k in kws}
        self.subset   = {k["id"]: k["subset_of"] for k in kws if k.get("subset_of")}
        self.split    = [(k["id"], re.compile(k["split_first"], flags_of(k)), re.compile(k["split_second"], flags_of(k)))
                         for k in kws if k.get("split_first")]
        self.prefilter = [t.lower() for t in PREFILTER.get(slug, [])]

    def could_hit(self, text: str) -> bool:
        if not self.prefilter:
            return True
        low = text.lower()
        return any(t in low for t in self.prefilter)

    def scan_text(self, text: str) -> tuple[dict[str, int], int]:
        """Return ({keyword id: hit count}, number of lines with ≥1 technique hit)."""
        if not self.could_hit(text):
            return {}, 0
        lines = text.splitlines()
        hits: dict[str, int] = {}
        hit_lines: set[int] = set()
        for i, line in enumerate(lines):
            if self.prefilter and not any(t in line.lower() for t in self.prefilter):
                continue
            for kw in self.keywords:
                tail = kw.get("_comment_tail")
                if (_comment_search(tail, line) if tail is not None else kw["compiled"].search(line)):
                    hits[kw["id"]] = hits.get(kw["id"], 0) + 1
                    hit_lines.add(i)
            for kid, first, second in self.split:
                if first.search(line) and i + 1 < len(lines) and second.search(lines[i + 1]):
                    hits[kid] = hits.get(kid, 0) + 1
                    hit_lines.add(i)
        return hits, len(hit_lines)

    def total(self, hits: dict[str, int]) -> int:
        return sum(v for k, v in hits.items() if k not in self.subset)
