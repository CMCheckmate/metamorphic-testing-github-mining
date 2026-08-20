"""
Central configuration: search queries, file patterns, and runtime paths.
Edit this file to tune what gets searched and which repos get cloned.
"""

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).parent
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", BASE_DIR / "results"))
REPOS_DIR   = Path(os.getenv("REPOS_DIR",   BASE_DIR / "repos"))

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
REPOS_DIR.mkdir(parents=True, exist_ok=True)
(RESULTS_DIR / "raw").mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------
GITHUB_TOKEN       = os.getenv("GITHUB_TOKEN", "")
GITHUB_API_BASE    = "https://api.github.com"
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

# ---------------------------------------------------------------------------
# Rate-limit delays (seconds between requests, per endpoint bucket)
#
# GitHub authenticated limits:
#   Standard search (/repositories, /issues, /commits): 30 req/min → 2.0 s min gap
#   Code search (/code):                                  9 req/min → 6.7 s min gap
#   GraphQL (discussions):                         5 000 pts/hour  → ~0.72 s/query
#
# Values include ~10 % headroom to avoid edge-case 429 responses.
# ---------------------------------------------------------------------------
STANDARD_SEARCH_DELAY = 2.2   # /repositories, /issues, /commits
CODE_SEARCH_DELAY     = 7.0   # /code (separate rate-limit bucket)
GRAPHQL_DELAY         = 1.5   # GraphQL discussions (conservative)

# ---------------------------------------------------------------------------
# Adaptive date-range slicing
#
# GitHub hard-caps results at 1 000 per query.  When total_count exceeds
# SLICE_THRESHOLD, search.py splits the date range in half and recurses until
# each slice fits under the cap.
#
# SLICE_THRESHOLD  — begin slicing when total_count exceeds this value.
#   Set to 900 (not 1 000) for a small buffer against results added mid-slice.
# SLICE_MAX_DEPTH  — maximum recursion depth (2^N slices; 2^6 = 64 sub-queries
#   per original query).  Most MT queries need 0–2 levels.
# SLICE_MIN_DAYS   — stop recursing when a slice is this many days wide.
#   Prevents infinite recursion on queries with >1 000 results in a single day.
# ---------------------------------------------------------------------------
SLICE_THRESHOLD  = 900
SLICE_MAX_DEPTH  = 6
SLICE_MIN_DAYS   = 7

SLICE_START_DATE = "2010-01-01"
SLICE_END_DATE   = "2026-06-30"   # update as needed

# ---------------------------------------------------------------------------
# MT terminology — word forms for each core concept (lemmatisation table)
#
# Maps each canonical MT concept to every word form worth searching for.
# Listing all forms explicitly ensures we cast the widest possible net —
# GitHub's full-text search does not guarantee stemming across all surfaces,
# so "metamorphic test" may not reliably surface repos that only say
# "metamorphic testing".  Explicit variants remove this ambiguity.
#
# Add new forms here; all query lists are built automatically from this table.
# ---------------------------------------------------------------------------
_MT_WORD_VARIANTS: dict[str, list[str]] = {
    "testing":      ["testing", "test", "tests"],
    "relation":     ["relation", "relations", "relationship", "relationships"],
    "group":        ["group", "groups"],
    "property":     ["property", "properties"],
}


def _mt_phrases() -> list[str]:
    """Return every 'metamorphic <form>' phrase, quoted for exact GitHub matching."""
    return [
        f'"metamorphic {word_form}"'
        for word_forms in _MT_WORD_VARIANTS.values()
        for word_form in word_forms
    ]


# Code identifiers — class names, snake_case names, and decorators used in MT
# code.  These appear not only in source files but also in commit messages,
# issue bodies, and repo descriptions when developers discuss code, so they are
# included on every search surface alongside the natural-language phrase queries.
_MT_CODE_IDENTIFIERS: list[str] = [
    "MetamorphicTest",
    "MetamorphicRelation",
    "metamorphic_relation",
    "metamorphic_relations",
    "metamorphic_test",
    "metamorphic_tests",
    "@metamorphic",
]


def _label(prefix: str, term: str) -> str:
    clean = term.strip('"').replace(' ', '_').replace('@', 'at_')
    return f"{prefix}_{clean}"


# ---------------------------------------------------------------------------
# Search queries
#
# Every surface uses the full vocabulary (_mt_phrases() + _MT_CODE_IDENTIFIERS)
# so that:
#   • Phrase queries ("metamorphic testing") catch natural-language mentions in
#     repo descriptions, commit messages, issues, README files, and code comments.
#   • Identifier queries (MetamorphicTest, metamorphic_relation, @metamorphic)
#     catch code-level references that appear without spaces on all surfaces —
#     a commit message or issue may mention a class name or snake_case identifier
#     just as a code file does.
# Filtering for genuine MT adoption happens later in Phase 3.
# ---------------------------------------------------------------------------

REPO_QUERIES: list[dict] = [
    {"query": term, "label": _label("repo", term)}
    for term in _mt_phrases() + _MT_CODE_IDENTIFIERS
] + [
    {"query": '"metamorphic testing framework"', "label": "repo_mt_framework"},
    {"query": "topic:metamorphic-testing",       "label": "repo_topic"},
]

CODE_QUERIES: list[dict] = [
    {"query": term, "label": _label("code", term)}
    for term in _MT_CODE_IDENTIFIERS + _mt_phrases()
]

ISSUE_QUERIES: list[dict] = [
    {"query": term, "label": _label("issue", term), "kind": "issue"}
    for term in _mt_phrases() + _MT_CODE_IDENTIFIERS
] + [
    {"query": term, "label": _label("pr", term), "kind": "pr"}
    for term in _mt_phrases() + _MT_CODE_IDENTIFIERS
] + [
    {"query": '"metamorphic testing framework"', "label": "issue_mt_framework", "kind": "issue"},
]

COMMIT_QUERIES: list[dict] = [
    {"query": term, "label": _label("commit", term)}
    for term in _mt_phrases() + _MT_CODE_IDENTIFIERS
]

DISCUSSION_QUERIES: list[str] = (
    _mt_phrases() + _MT_CODE_IDENTIFIERS + ['"metamorphic testing framework"']
)

# ---------------------------------------------------------------------------
# File-extension filter for local analysis (Phase 3)
#
# Empty set = accept all file types.
# Populate to restrict, e.g. {".py", ".java", ".js", ".ts", ".go"}
# ---------------------------------------------------------------------------
ANALYSIS_EXTENSIONS: set[str] = set()

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "target", ".tox", ".pytest_cache",
}

# Binary and machine-generated output formats — not human-authored, so any
# regex match would be a path/encoding artifact rather than intentional MT content.
# This is only used in Phase 3 (local analysis) to avoid wasting time on large binary 
# files while keeping the search phase (Phase 2) as broad as possible.
SKIP_EXTENSIONS: set[str] = {
    ".out", ".bin", ".pkl", ".npz", ".npy", ".h5", ".hdf5", ".parquet",
}

# ---------------------------------------------------------------------------
# Clone settings
# ---------------------------------------------------------------------------
MAX_REPO_SIZE_KB    = 750_000   # skip repos larger than 750 MB
CLONE_DEPTH         = 1         # shallow clone (latest commit only)
CLONE_DELAY_SECONDS = 0.3       # inter-clone delay per worker thread

