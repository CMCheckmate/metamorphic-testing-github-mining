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
# ---------------------------------------------------------------------------
STANDARD_SEARCH_DELAY = 2.2
CODE_SEARCH_DELAY     = 7.0
GRAPHQL_DELAY         = 1.5

# ---------------------------------------------------------------------------
# Adaptive date-range slicing
# ---------------------------------------------------------------------------
SLICE_THRESHOLD  = 900
SLICE_MAX_DEPTH  = 6
SLICE_MIN_DAYS   = 7

SLICE_START_DATE = "2010-01-01"
SLICE_END_DATE   = "2026-06-30"

# ---------------------------------------------------------------------------
# File-extension filter for local analysis (Phase 3)
# ---------------------------------------------------------------------------
ANALYSIS_EXTENSIONS: set[str] = set()   # empty = accept all source-like files

SKIP_DIRS: set[str] = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "target", ".tox", ".pytest_cache", ".eggs",
    "coverage", ".coverage", "htmlcov",
}

SKIP_EXTENSIONS: set[str] = {
    # Compiled / binary outputs
    ".out", ".bin", ".pkl", ".npz", ".npy", ".h5", ".hdf5", ".parquet",
    ".wasm", ".so", ".dylib", ".dll", ".exe", ".class", ".pyc", ".pyo",
    ".obj", ".o", ".a", ".lib", ".pdb",
    # Images — binary files; MT/MR abbreviation patterns match random bytes
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".tiff", ".tif",
    ".webp", ".eps", ".raw", ".heic", ".heif",
    # Archives / compressed
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z", ".lz4", ".zst",
    ".cab", ".iso", ".img", ".dmg",
    # ML model / data blobs
    ".pth", ".pt", ".onnx", ".safetensors", ".mat", ".keras", ".pb",
    ".tflite", ".mlmodel", ".ckpt", ".msgpack",
    # Audio / video
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv",
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a",
    # JVM / package artifacts
    ".jar", ".war", ".ear", ".apk", ".ipa", ".deb", ".rpm",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # Databases
    ".db", ".sqlite", ".sqlite3", ".mdb",
}

# Extensions treated as documentation (not source code)
DOC_EXTENSIONS: set[str] = {
    ".md", ".rst", ".txt", ".tex", ".adoc", ".pdf", ".html", ".htm",
}

# Extensions treated as configuration (build/packaging)
CONFIG_EXTENSIONS: set[str] = {
    ".toml", ".cfg", ".ini", ".yaml", ".yml", ".xml", ".json",
    ".gradle", ".properties", ".lock",
}

# ---------------------------------------------------------------------------
# Clone settings
# ---------------------------------------------------------------------------
MAX_REPO_SIZE_KB    = 5_000_000   # 5 GB
CLONE_DEPTH         = 500        # fetch last N commits for commit history analysis
                                  # set to 0 for full history (slow, high disk usage)
CLONE_DELAY_SECONDS = 0.3

# ---------------------------------------------------------------------------
# Domain keyword sets for project domain inference
# Checked against repo name + description + topics (all lowercased).
# ---------------------------------------------------------------------------
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "machine_learning": [
        "machine learning", "neural network", "deep learning", "ml model",
        "sklearn", "scikit-learn", "tensorflow", "pytorch", "keras",
        "model training", "classification", "regression", "llm",
        "large language model", "transformer", "computer vision", "nlp",
        "natural language processing",
    ],
    "compiler": [
        "compiler", "transpiler", "parser", "abstract syntax tree", "ast",
        "bytecode", "llvm", "codegen", "syntax", "code generation",
        "interpreter", "jit", "optimization pass",
    ],
    "database": [
        "database", "sql", "query", "orm", "datalog", "nosql", "mongodb",
        "elasticsearch", "query optimizer", "storage engine", "relational",
        "key-value store",
    ],
    "scientific": [
        "simulation", "numerical", "scientific computing", "physics",
        "computational", "differential equation", "monte carlo",
        "optimization algorithm", "finite element", "fluid dynamics",
        "signal processing",
    ],
    "bioinformatics": [
        "bioinformatics", "genome", "dna", "rna", "protein", "sequence alignment",
        "blast", "genomics", "proteomics", "phylogenetic", "metagenomics",
    ],
    "security": [
        "security", "vulnerability", "exploit", "penetration test",
        "cryptograph", "authentication", "authorization", "injection",
        "fuzzing", "malware", "reverse engineering",
    ],
    "web": [
        "api", "rest", "http", "web server", "django", "flask", "fastapi",
        "microservice", "frontend", "backend", "graphql", "web application",
        "react", "angular", "vue",
    ],
    "autonomous_systems": [
        "autonomous", "self-driving", "driverless", "robotics",
        "perception module", "path planning", "lidar", "drone",
    ],
    "testing_infrastructure": [
        "testing framework", "test runner", "test suite", "assertion library",
        "mock", "stub", "fuzz", "property-based", "mutation testing",
    ],
}


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

        # Commit keywords for Phase 3 git log analysis — always the search phrases.
        self.commit_keywords: list[str] = self.search_phrases

        # Analysis patterns (serialisable dicts — regex compiled separately)
        self.patterns_raw: list[dict] = data.get("patterns", [])

        # Lemmatization
        lem = data.get("lemmatization", {})
        self.lemma_trigger:  str  = lem.get("trigger", "")
        self.concept_lemmas: dict = lem.get("concept_lemmas", {})

        # Optional per-technique domain hints (e.g. ["machine_learning"] for MT)
        self.domain_hints: list[str] = data.get("domain_hints", [])

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
            q = [{"query": t, "label": self._label(prefix, t)} for t in terms]
            if kind:
                for entry in q:
                    entry["kind"] = kind
            return q

        self.repo_queries: list[dict] = (
            make("repo", phrases + idents) + self.extra_queries["repos"]
        )
        self.code_queries: list[dict] = (
            make("code", idents + phrases) + self.extra_queries["code"]
        )
        self.issue_queries: list[dict] = (
            make("issue", phrases + idents, kind="issue")
            + make("pr",    phrases + idents, kind="pr")
            + self.extra_queries["issues"]
        )
        self.commit_queries: list[dict] = (
            make("commit", phrases + idents) + self.extra_queries["commits"]
        )
        disc_extras = [
            e if isinstance(e, str) else e.get("query", "")
            for e in self.extra_queries["discussions"]
        ]
        self.discussion_queries: list[str] = phrases + idents + disc_extras

    def _compile_patterns(self) -> None:
        flag_map = {"IGNORECASE": re.IGNORECASE, "MULTILINE": re.MULTILINE}
        self.patterns: list[dict] = [
            {
                "id":    p["id"],
                "label": p["label"],
                "regex": re.compile(p["regex"], flag_map.get(p.get("flags", ""), 0)),
            }
            for p in self.patterns_raw
        ]

    # ------------------------------------------------------------------
    # Serialisation for multiprocessing workers
    # ------------------------------------------------------------------

    def worker_config(self) -> dict:
        """Return a JSON-serialisable dict for passing to subprocess workers."""
        return {
            "patterns_raw":          self.patterns_raw,
            "results_dir":           str(self.results_dir),
            "analysis_extensions":   list(ANALYSIS_EXTENSIONS),
            "skip_dirs":             list(SKIP_DIRS),
            "skip_extensions":       list(SKIP_EXTENSIONS),
            "doc_extensions":        list(DOC_EXTENSIONS),
            "config_extensions":     list(CONFIG_EXTENSIONS),
            "lemma_trigger":         self.lemma_trigger,
            "concept_lemmas":        self.concept_lemmas,
            "commit_keywords":       self.commit_keywords,
            "domain_keywords":       DOMAIN_KEYWORDS,
            "short_name":            self.short_name,
        }

    def __repr__(self) -> str:
        return f"TechniqueProfile({self.name!r}, slug={self.slug!r})"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_technique(yaml_path: str | Path) -> TechniqueProfile:
    """Load a technique profile from a YAML file."""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML is required: pip install pyyaml") from exc

    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Technique file not found: {path}")

    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    return TechniqueProfile(data)
