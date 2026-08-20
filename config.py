"""
Central configuration: infrastructure settings and technique profile loader.

Technique-specific vocabulary (search phrases, patterns, report settings) now lives
in YAML files under techniques/. Use load_technique(path) to load a profile and pass
it to each phase's run() function.

Infrastructure settings (rate limits, clone params, file-scan filters) remain here
as they are independent of the technique being mined.
"""

from pathlib import Path
from dotenv import load_dotenv
import os
import re

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).parent
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", BASE_DIR / "results"))
REPOS_DIR   = Path(os.getenv("REPOS_DIR",   BASE_DIR / "repos"))

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
REPOS_DIR.mkdir(parents=True, exist_ok=True)

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
# ---------------------------------------------------------------------------
SLICE_THRESHOLD  = 900
SLICE_MAX_DEPTH  = 6
SLICE_MIN_DAYS   = 7

SLICE_START_DATE = "2010-01-01"
SLICE_END_DATE   = "2026-06-30"   # update as needed

# ---------------------------------------------------------------------------
# File-extension filter for local analysis (Phase 3)
# ---------------------------------------------------------------------------
ANALYSIS_EXTENSIONS: set[str] = set()   # empty = accept all

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "target", ".tox", ".pytest_cache",
}

SKIP_EXTENSIONS: set[str] = {
    ".out", ".bin", ".pkl", ".npz", ".npy", ".h5", ".hdf5", ".parquet",
}

# ---------------------------------------------------------------------------
# Clone settings
# ---------------------------------------------------------------------------
MAX_REPO_SIZE_KB    = 750_000   # skip repos larger than 750 MB
CLONE_DEPTH         = 1         # shallow clone (latest commit only)
CLONE_DELAY_SECONDS = 0.3       # inter-clone delay per worker thread


# ---------------------------------------------------------------------------
# TechniqueProfile — loaded from a techniques/*.yaml file
# ---------------------------------------------------------------------------

class TechniqueProfile:
    """
    Holds all vocabulary, patterns, and report settings for one testing technique.
    Loaded via load_technique(yaml_path).  Pass to each phase's run() function.
    """

    def __init__(self, data: dict) -> None:
        # Core metadata
        self.name:        str = data["name"]
        self.short_name:  str = data["short_name"]
        self.slug:        str = data["slug"]
        self.description: str = data.get("description", "")
        self.color:       str = data.get("color", "#1a6e3c")

        # Search vocabulary
        self.search_phrases: list[str] = data.get("search_phrases", [])
        self.identifiers:    list[str] = data.get("identifiers", [])
        raw_extra = data.get("extra_queries", {})
        self.extra_queries: dict = {
            "repos":       raw_extra.get("repos", []),
            "code":        raw_extra.get("code", []),
            "issues":      raw_extra.get("issues", []),
            "commits":     raw_extra.get("commits", []),
            "discussions": raw_extra.get("discussions", []),
        }

        # Analysis patterns (serialisable dicts — regex compiled separately)
        self.patterns_raw: list[dict] = data.get("patterns", [])

        # Scoring
        cls = data.get("classification", {})
        self.classification_strong: int = cls.get("strong_threshold", 3)
        self.classification_weak:   int = cls.get("weak_threshold",   1)

        # Lemmatization
        lem = data.get("lemmatization", {})
        self.lemma_trigger:   str  = lem.get("trigger", "")
        self.concept_lemmas:  dict = lem.get("concept_lemmas", {})

        # Report
        self.extra_report_sections: list[str] = data.get("extra_report_sections", [])
        self.report_intro:          str       = data.get("report_intro", "")

        # Derived paths & queries
        self._setup_dirs()
        self._build_queries()
        self._compile_patterns()

    # ------------------------------------------------------------------
    # Internal setup
    # ------------------------------------------------------------------

    def _setup_dirs(self) -> None:
        self.results_dir = BASE_DIR / "results" / self.slug
        self.repos_dir   = BASE_DIR / "repos"   / self.slug
        for d in (
            self.results_dir / "raw",
            self.results_dir / "cloned",
            self.results_dir / "analysis",
            self.results_dir / "plots",
            self.repos_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _label(prefix: str, term: str) -> str:
        clean = (
            term.strip('"')
            .replace(" ", "_")
            .replace("@", "at_")
            .replace("-", "_")
            .replace(".", "_")
            .replace("/", "_")
        )
        return f"{prefix}_{clean}"

    def _build_queries(self) -> None:
        phrases = [f'"{p}"' for p in self.search_phrases]
        idents  = self.identifiers

        def make(prefix: str, terms: list[str], kind: str | None = None) -> list[dict]:
            q = [
                {"query": t, "label": self._label(prefix, t)}
                for t in terms
            ]
            if kind:
                for entry in q:
                    entry["kind"] = kind
            return q

        self.repo_queries: list[dict] = (
            make("repo", phrases + idents)
            + self.extra_queries["repos"]
        )
        self.code_queries: list[dict] = (
            make("code", idents + phrases)
            + self.extra_queries["code"]
        )
        self.issue_queries: list[dict] = (
            make("issue", phrases + idents, kind="issue")
            + make("pr",    phrases + idents, kind="pr")
            + self.extra_queries["issues"]
        )
        self.commit_queries: list[dict] = (
            make("commit", phrases + idents)
            + self.extra_queries["commits"]
        )
        # Discussion queries are plain strings (used by GraphQL search)
        disc_extras = [
            e if isinstance(e, str) else e.get("query", "")
            for e in self.extra_queries["discussions"]
        ]
        self.discussion_queries: list[str] = phrases + idents + disc_extras

    def _compile_patterns(self) -> None:
        """Compile regex patterns for use in the main process."""
        flag_map = {"IGNORECASE": re.IGNORECASE, "MULTILINE": re.MULTILINE}
        self.patterns: list[dict] = [
            {
                "id":    p["id"],
                "label": p["label"],
                "regex": re.compile(
                    p["regex"],
                    flag_map.get(p.get("flags", ""), 0),
                ),
            }
            for p in self.patterns_raw
        ]

    # ------------------------------------------------------------------
    # Serialisation for multiprocessing workers
    # ------------------------------------------------------------------

    def worker_config(self) -> dict:
        """Return a JSON-serialisable dict for passing to subprocess workers."""
        return {
            "patterns_raw":         self.patterns_raw,
            "results_dir":          str(self.results_dir),
            "analysis_extensions":  list(ANALYSIS_EXTENSIONS),
            "skip_dirs":            list(SKIP_DIRS),
            "skip_extensions":      list(SKIP_EXTENSIONS),
            "lemma_trigger":        self.lemma_trigger,
            "concept_lemmas":       self.concept_lemmas,
            "classification_strong": self.classification_strong,
            "classification_weak":   self.classification_weak,
        }

    def __repr__(self) -> str:
        return f"TechniqueProfile({self.name!r}, slug={self.slug!r})"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_technique(yaml_path: str | Path) -> TechniqueProfile:
    """
    Load a technique profile from a YAML file.

    Example:
        profile = load_technique("techniques/metamorphic_testing.yaml")
        search.run(..., profile=profile)
    """
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required: pip install pyyaml"
        ) from exc

    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Technique file not found: {path}")

    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    return TechniqueProfile(data)
