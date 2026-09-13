"""
Central configuration — tuneable constants only.
No business logic, no technique-specific data.
All technique vocabulary lives in inputs/*.txt and inputs/*.json.
"""
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR        = Path(__file__).parent
RESULTS_DIR     = Path(os.getenv("RESULTS_DIR", str(BASE_DIR / "results")))
INPUTS_DIR      = Path(os.getenv("INPUTS_DIR",  str(BASE_DIR / "inputs")))
CLONED_DIR_NAME = "cloned"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
INPUTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------
GITHUB_TOKEN        = os.getenv("GITHUB_TOKEN", "")
GITHUB_API_BASE     = "https://api.github.com"
GITHUB_GRAPHQL_URL  = "https://api.github.com/graphql"
GITHUB_API_PER_PAGE = 100   # max allowed by GitHub

# ---------------------------------------------------------------------------
# Rate limiting & retry
# ---------------------------------------------------------------------------
RATE_LIMIT_PAUSE     = 2.5   # base pause; ~24 req/min, headroom vs 30/min limit
CODE_SEARCH_PAUSE    = 7.0   # code search has a tighter rate limit bucket
GRAPHQL_PAUSE        = 1.5
RETRY_ATTEMPTS       = 5
RETRY_BACKOFF_BASE   = 2.0   # seconds; sleep = BASE^attempt + jitter
RETRY_BACKOFF_JITTER = 1.0   # max random jitter added to each backoff

# ---------------------------------------------------------------------------
# Adaptive date-range slicing (avoids GitHub's 1000-result hard cap)
# ---------------------------------------------------------------------------
SLICE_THRESHOLD  = 900
SLICE_MAX_DEPTH  = 6
SLICE_MIN_DAYS   = 7
SLICE_START_DATE = "2010-01-01"
SLICE_END_DATE   = "2026-09-01"

# ---------------------------------------------------------------------------
# Clone settings
# ---------------------------------------------------------------------------
CLONE_BATCH_MAX_BYTES = 5 * 1024 ** 3   # 5 GB per batch
CLONE_BATCH_MAX_REPOS = 20
CLONE_DEPTH           = 100             # 0 = full history (slow)

# ---------------------------------------------------------------------------
# File analysis
# ---------------------------------------------------------------------------
ANALYSIS_WORKERS    = 4
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024   # 5 MB — skip larger files
MAX_PATH_LENGTH     = 200               # Windows path limit workaround

IGNORED_EXTENSIONS: set[str] = {
    # Compiled / binary
    ".out", ".bin", ".pkl", ".npz", ".npy", ".h5", ".hdf5", ".parquet",
    ".wasm", ".so", ".dylib", ".dll", ".exe", ".class", ".pyc", ".pyo",
    ".obj", ".o", ".a", ".lib", ".pdb",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".tiff", ".tif",
    ".webp", ".eps", ".raw", ".heic", ".heif",
    # Archives
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

SKIP_DIRS: set[str] = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "target", ".tox", ".pytest_cache", ".eggs",
    "coverage", ".coverage", "htmlcov",
}

CODE_EXTENSIONS: set[str] = {
    ".py", ".java", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".cxx",
    ".cc", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift",
    ".kt", ".kts", ".scala", ".clj", ".cljs", ".hs", ".ml", ".mli",
    ".fs", ".fsx", ".erl", ".ex", ".exs", ".r", ".jl", ".lua",
    ".sh", ".bash", ".zsh", ".ps1", ".dart", ".m", ".mm",
}

DOC_EXTENSIONS: set[str] = {
    ".md", ".rst", ".txt", ".tex", ".adoc", ".html", ".htm",
}

CONFIG_EXTENSIONS: set[str] = {
    ".toml", ".cfg", ".ini", ".yaml", ".yml", ".xml", ".json",
    ".gradle", ".properties", ".lock",
}

# ---------------------------------------------------------------------------
# Search defaults (None = no filter applied to queries)
# ---------------------------------------------------------------------------
SEARCH_MIN_STARS       = None
SEARCH_LANGUAGE_FILTER = None
SEARCH_DATE_FILTER     = None

# ---------------------------------------------------------------------------
# Report settings
# ---------------------------------------------------------------------------
REPORT_TOP_N_KEYWORDS = 20
REPORT_TOP_N_REPOS    = 50
PLOT_FORMAT           = "png"
PLOT_DPI              = 150

# ---------------------------------------------------------------------------
# Technique name → canonical slug mapping
# ---------------------------------------------------------------------------
TECHNIQUE_SLUGS: dict[str, str] = {
    "mt":                     "metamorphic_testing",
    "metamorphic_testing":    "metamorphic_testing",
    "fuzz":                   "fuzz_testing",
    "fuzz_testing":           "fuzz_testing",
    "pbt":                    "property_based_testing",
    "property_based_testing": "property_based_testing",
}

TECHNIQUE_DISPLAY_NAMES: dict[str, str] = {
    "metamorphic_testing":    "Metamorphic Testing",
    "fuzz_testing":           "Fuzz Testing",
    "property_based_testing": "Property-Based Testing",
}

TECHNIQUE_SHORT_NAMES: dict[str, str] = {
    "metamorphic_testing":    "MT",
    "fuzz_testing":           "Fuzzing",
    "property_based_testing": "PBT",
}

TECHNIQUE_INPUT_PREFIXES: dict[str, str] = {
    "metamorphic_testing":    "mt",
    "fuzz_testing":           "fuzz",
    "property_based_testing": "pbt",
}

# ---------------------------------------------------------------------------
# Domain keywords — checked against repo name + description + topics
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
