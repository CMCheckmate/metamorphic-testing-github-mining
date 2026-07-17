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
BASE_DIR = Path(__file__).parent
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", BASE_DIR / "results"))
REPOS_DIR = Path(os.getenv("REPOS_DIR", BASE_DIR / "repos"))

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
REPOS_DIR.mkdir(parents=True, exist_ok=True)
(RESULTS_DIR / "raw").mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API_BASE = "https://api.github.com"
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

# ---------------------------------------------------------------------------
# Rate-limit delays (seconds between requests, per endpoint bucket)
#
# GitHub authenticated limits:
#   Standard search (/repositories, /issues, /commits): 30 req/min → 2.0s min gap
#   Code search (/code):                                  9 req/min → 6.7s min gap
#   GraphQL (discussions):                         5000 pts/hour → ~0.72s/query
#
# We add ~10% headroom to avoid edge-case 429s.
# ---------------------------------------------------------------------------
STANDARD_SEARCH_DELAY = 2.2   # /repositories, /issues, /commits
CODE_SEARCH_DELAY     = 7.0   # /code  (9 req/min bucket, separate from standard)
GRAPHQL_DELAY         = 1.5   # GraphQL discussions (conservative)

# ---------------------------------------------------------------------------
# Adaptive date-range slicing
#
# When a query returns total_count > SLICE_THRESHOLD, search.py automatically
# splits the date range in two and recurses until each slice is under the cap.
# GitHub hard-caps results at 1,000 per query regardless of total_count.
# Slicing is the only documented workaround.
#
# SLICE_THRESHOLD: start slicing if total_count exceeds this value.
#   Set to 900 (not 1000) to have a small buffer for results added mid-slice.
# SLICE_MAX_DEPTH: maximum recursion depth (2^N slices = 2^6 = 64 sub-queries
#   per original query).  Most MT queries need 0–2 levels.
# SLICE_MIN_DAYS: stop recursing when a slice is this many days wide.
#   Prevents infinite recursion on queries with >1000 results in a single day.
# ---------------------------------------------------------------------------
SLICE_THRESHOLD = 900
SLICE_MAX_DEPTH = 6
SLICE_MIN_DAYS  = 7

# Default overall date window for sliced searches (YYYY-MM-DD strings)
SLICE_START_DATE = "2010-01-01"
SLICE_END_DATE   = "2026-06-30"   # update as needed

# ---------------------------------------------------------------------------
# Explicit MT search queries
# ---------------------------------------------------------------------------

# --- Repository searches ---
# Hits: repo name, description, topics, README content
REPO_QUERIES: list[dict] = [
    {"query": "metamorphic testing",            "label": "repo_mt"},
    {"query": "metamorphic test",               "label": "repo_mt_singular"},
    {"query": "metamorphic tests",              "label": "repo_mt_plural"},
    {"query": "metamorphic relation",           "label": "repo_mr"},
    {"query": "metamorphic relations",          "label": "repo_mr_plural"},
    {"query": "metamorphic relationship",       "label": "repo_mr_relationship"},
    {"query": "metamorphic testing framework",  "label": "repo_mt_framework"},
    {"query": "topic:metamorphic-testing",      "label": "repo_topic"},
]

# --- Code searches ---
# Hits: all files on the default branch (source, config, docs, README, etc.)
# Rate limit: 9 req/min (separate bucket from the other search endpoints)
CODE_QUERIES: list[dict] = [
    # Library imports
    {"query": "import metamorphic",             "label": "import_metamorphic",      "lang": None},
    {"query": "from metamorphic",               "label": "from_metamorphic",        "lang": None},
    {"query": "MetamorphicTest",                "label": "class_MetamorphicTest",   "lang": None},
    {"query": "MetamorphicRelation",            "label": "class_MR",                "lang": None},
    {"query": "metamorphic_relation",           "label": "fn_metamorphic_rel",      "lang": None},
    {"query": "metamorphic_test",               "label": "fn_metamorphic_test",     "lang": None},
    # Python libraries
    {"query": "pytest-metamorphic",             "label": "lib_pytest_mt",           "lang": "Python"},
    {"query": "hypothesis_metamorphic",         "label": "lib_hypothesis_mt",       "lang": "Python"},
    {"query": "from mt_testing",                "label": "lib_mt_testing",          "lang": "Python"},
    # Java libraries
    {"query": "MetamorphicTesting",             "label": "java_MetamorphicTesting", "lang": "Java"},
    {"query": "org.metamorphictesting",         "label": "java_org_mt",             "lang": "Java"},
    # Decorators / annotations
    {"query": "@metamorphic",                   "label": "decorator_metamorphic",   "lang": None},
    # String literals / comments — singular, plural, and relationship forms
    {"query": '"metamorphic relation"',         "label": "string_mr",               "lang": None},
    {"query": '"metamorphic relations"',        "label": "string_mr_plural",        "lang": None},
    {"query": '"metamorphic relationship"',     "label": "string_mr_relationship",  "lang": None},
    {"query": '"metamorphic testing"',          "label": "string_mt",               "lang": None},
    {"query": '"metamorphic test"',             "label": "string_mt_singular",      "lang": None},
    {"query": '"metamorphic tests"',            "label": "string_mt_plural",        "lang": None},
    # Java function-naming convention from MT literature
    {"query": "void testMR",                    "label": "java_testMR",             "lang": "Java"},
]

# --- Issue and PR searches ---
# Uses /search/issues endpoint; `is:issue` and `is:pr` are applied per entry.
# Rate limit: 30 req/min (standard search bucket, shared with repos/commits)
# Hits: issue/PR title, body text, and comment text (all in one endpoint)
ISSUE_QUERIES: list[dict] = [
    {"query": "metamorphic testing",            "label": "issue_mt",          "kind": "issue"},
    {"query": "metamorphic test",               "label": "issue_mt_singular", "kind": "issue"},
    {"query": "metamorphic tests",              "label": "issue_mt_plural",   "kind": "issue"},
    {"query": "metamorphic relation",           "label": "issue_mr",          "kind": "issue"},
    {"query": "metamorphic relations",          "label": "issue_mr_plural",   "kind": "issue"},
    {"query": "metamorphic relationship",       "label": "issue_mr_rel",      "kind": "issue"},
    {"query": "metamorphic testing",            "label": "pr_mt",             "kind": "pr"},
    {"query": "metamorphic test",               "label": "pr_mt_singular",    "kind": "pr"},
    {"query": "metamorphic relation",           "label": "pr_mr",             "kind": "pr"},
    {"query": "metamorphic relations",          "label": "pr_mr_plural",      "kind": "pr"},
    {"query": "metamorphic testing framework",  "label": "issue_mt_fw",       "kind": "issue"},
    # Library-specific: people asking about or reporting bugs in MT tools
    {"query": "pytest-metamorphic",             "label": "issue_pytest_mt",   "kind": "issue"},
    {"query": "MetamorphicTest",                "label": "issue_class_mt",    "kind": "issue"},
]

# --- Commit message searches ---
# Uses /search/commits endpoint — searches default branch commit messages only.
# Rate limit: 30 req/min (standard search bucket)
# Useful for finding projects that added MT incrementally without naming it in code.
COMMIT_QUERIES: list[dict] = [
    {"query": "metamorphic testing",   "label": "commit_mt"},
    {"query": "metamorphic test",      "label": "commit_mt_singular"},
    {"query": "metamorphic tests",     "label": "commit_mt_plural"},
    {"query": "metamorphic relation",  "label": "commit_mr"},
    {"query": "metamorphic relations", "label": "commit_mr_plural"},
    {"query": "add metamorphic",       "label": "commit_add_mt"},
]

# --- GitHub Discussions (GraphQL only) ---
# No REST endpoint exists. Searched via GraphQL search() query.
# Rate limit: 5,000 pts/hour, max 2,000 pts/min (1 pt per non-mutation query)
DISCUSSION_QUERIES: list[str] = [
    "metamorphic testing",
    "metamorphic test",
    "metamorphic tests",
    "metamorphic relation",
    "metamorphic relations",
    "metamorphic relationship",
    "metamorphic test framework",
]

# ---------------------------------------------------------------------------
# File-extension / path filters used during local analysis (Phase 3)
# ---------------------------------------------------------------------------
# Empty set = accept all file extensions (wildcard behaviour).
# Populate with specific extensions to restrict analysis, e.g.:
#   {".py", ".java", ".js", ".ts", ".cs", ".rb", ".go", ".cpp", ".c",
#    ".kt", ".scala", ".rs", ".php", ".swift"}
ANALYSIS_EXTENSIONS: set[str] = set()

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "target", ".tox", ".pytest_cache",
}

# ---------------------------------------------------------------------------
# Implicit-usage patterns searched inside cloned repos (Phase 3)
# ---------------------------------------------------------------------------
IMPLICIT_PATTERNS: list[dict] = [
    {
        "id":      "mr_variable_name",
        "label":   "Variable named after MR convention",
        "pattern": r"\b(mr\d+|MR\d+|metamorphic_rel)\b",
        "note":    "Variable names using MT literature conventions (mr1, MR2, metamorphic_rel)",
    },
    {
        "id":      "oracle_keyword",
        "label":   "MT oracle keyword in test file",
        "pattern": r"\b(test_oracle|pseudo_oracle)\b",
        "note":    "Specific MT oracle terms (excludes bare 'oracle' which matches Oracle DB/Corp)",
    },
]

# ---------------------------------------------------------------------------
# Clone settings
# ---------------------------------------------------------------------------
MAX_REPO_SIZE_KB   = 200_000   # skip repos larger than 200 MB
CLONE_DEPTH        = 1         # shallow clone (latest commit only)
CLONE_DELAY_SECONDS = 0.5
