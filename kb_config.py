"""Paths, the model catalog and shared constants."""
import os
import sys

"""
Knowledge Bank (بانک دانش) — native Python desktop app, one file.

Run:    python kb.py
Setup:  python kb.py --install      (optional; the app also offers to install what it needs)

* A real desktop window (Qt via PySide6), not a browser page.
* Reads your folders/files straight from disk, so there are no browser permission prompts.
* Word search and cited answers need nothing beyond Python + PySide6.
* Optional extras (plain pip wheels, no compiler, installable from the app's sidebar):
    pypdf                          better PDF text
    numpy                          vector math for meaning search
    llama.cpp (llama-server)       the answer model and the embedding model, run as child processes
* Heavy native code (llama.cpp) runs in a separate process,
  so a native crash can never take the window down.
* Reuses the ./data folder from the old HTML version (data/models/...).
"""


VERSION = "1.0"


NOWIN = {"creationflags": 0x08000000} if os.name == "nt" else {}


PIP_EXTRA = []  # set by the --pip-index and --wheels options


# When packaged (PyInstaller), __file__ points into a temporary folder that is cleared on exit,
# so the data folder must sit next to the .exe instead.
BASE = (os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__)))


DATA = os.environ.get("KB_DATA") or os.path.join(BASE, "data")   # KB_DATA lets the tests use another folder


BANK = os.path.join(DATA, "bank")


TEXTDIR = os.path.join(BANK, "text")


MODELS = os.path.join(DATA, "models")


ENGINE_DIR = os.path.join(DATA, "engine")


VENDOR = os.path.join(DATA, "vendor")              # downloaded wheels are unpacked here


VENDOR_SITE = os.path.join(VENDOR, "site")


PYPI_BASE = "https://pypi.org"


PYPI_FILES = "https://files.pythonhosted.org"


WHEEL_PACKAGES = ("pypdf", "numpy")               # PySide6 is installed with pip: it is too big to fetch like the others


if os.path.isdir(VENDOR_SITE):
    sys.path.insert(0, VENDOR_SITE)


ENGINE_REPO = "ggml-org/llama.cpp"


ENGINE_PINNED = "b11146"          # used if the GitHub API cannot be reached


HF_HOSTS = ["https://huggingface.co", "https://hf-mirror.com"]


def engine_asset_suffix():
    import platform
    arm = platform.machine().lower() in ("arm64", "aarch64")
    if sys.platform.startswith("win"):
        return "-bin-win-cpu-arm64.zip" if arm else "-bin-win-cpu-x64.zip"
    if sys.platform == "darwin":
        return "-bin-macos-arm64.tar.gz" if arm else "-bin-macos-x64.tar.gz"
    return "-bin-ubuntu-arm64.tar.gz" if arm else "-bin-ubuntu-x64.tar.gz"


def engine_os_token():
    """The OS word in llama.cpp's release file names: win, ubuntu or macos."""
    if sys.platform.startswith("win"):
        return "win"
    if sys.platform == "darwin":
        return "macos"
    return "ubuntu"


_GPU = {"checked": False, "backend": None}


def gpu_backend():
    """Returns 'vulkan' only when the user opts in with KB_GPU=vulkan. By default the CPU build is used and only that
    build is downloaded: in the logs the Vulkan build gave no speed gain, and it added start-up delays and empty replies.
    macOS builds use Metal on their own, so None there."""
    if os.environ.get("KB_GPU", "off").lower() != "vulkan":
        return None
    if not _GPU["checked"]:
        found = None
        try:
            if sys.platform.startswith("linux"):
                found = "vulkan"
            elif sys.platform.startswith("win"):
                found = "vulkan"
        except OSError:
            found = None
        _GPU["backend"], _GPU["checked"] = found, True
    return _GPU["backend"]


# GGUF model files, served by llama-server.
# size is a rough byte count, used only to check a download.
# one model per task
# embed: Multilingual E5 Small (about 126 MB), for meaning search.
# gen: Qwen3.5 2B instruct (about 1.28 GB), writes the answers with citations
# CPU use, as the user sees it: how many processors the work may use
RESOURCE_LEVELS = ("light", "balanced", "full")


def threads_for(level):
    cpu = os.cpu_count() or 4
    if level == "light":
        return 1
    if level == "full":
        return max(2, cpu - 1)
    return max(2, cpu // 2)


def workers_for(level):
    """How many documents are read in parallel."""
    return {"light": 1, "balanced": 2, "full": 3}.get(level, 2)


def pause_for(level):
    """Seconds to pause between indexing batches, so the computer stays responsive on Light."""
    return {"light": 1.0, "balanced": 0.05, "full": 0.0}.get(level, 0.05)


def duty_pause(level):
    """Indexing pause as a multiple of each embedding batch's own time. 1.0 means the indexer works about half the time
    (about half of one core on Balanced). Light is 0.667, so the indexer works about 60% of the time (60% of one core).
    0 means no pause (Full)."""
    return {"light": 0.667, "balanced": 1.0, "full": 0.0}.get(level, 1.0)


def batch_for(level):
    """Passages embedded per step. Smaller steps keep each burst of CPU use short."""
    return {"light": 2, "balanced": 8, "full": 16}.get(level, 8)


def watch_seconds(level):
    """Seconds between scans of the source folders for changed files. Each scan walks every folder, so Light scans rarely."""
    return {"light": 120, "balanced": 30, "full": 15}.get(level, 30)


def snapshot_seconds(level):
    """Seconds between refreshes of the window's state. Light refreshes less often."""
    return {"light": 2.0, "balanced": 1.0, "full": 0.6}.get(level, 1.0)


def lower_priority(level):
    """Light work gives way to everything else on the computer."""
    return level == "light"


def spawn_kwargs(level):
    """Extra arguments for starting the engine: lower priority on Light only."""
    if not lower_priority(level):
        return {}
    if os.name == "nt":
        return {"creationflags": 0x00004000}          # Windows priority class for low-priority engines
    return {"preexec_fn": lambda: os.nice(15)}


# sentences allowed per answer length: (minimum, maximum). Longer answers are trimmed to the maximum.
ANSWER_SENTENCES = {"short": (1, 2), "normal": (5, 7), "long": (8, 10)}

# how many passages a search returns
RESULT_COUNTS = {"few": 6, "standard": 12, "many": 25}

# answer length: (max tokens, instruction for the model)
ANSWER_LENGTHS = {
    "short":  (120, "one or two short sentences"),
    "normal": (400, "five to seven sentences"),
    "long":   (600, "eight to ten sentences that cover every relevant point in the excerpts; do not stop early"),
}

# Relevance cutoffs. Passages below these are dropped, so weak matches never show.
# Score ranges depend on the embedding model, so re-check these after switching models (E5 scores ran about 0.7 to 1.0).
# Off for now. In the logs an unrelated question scored 0.815 and a related one 0.839, so 0.85 would drop both.
# Set a cutoff only after checking many questions with data/logs/similarity.txt and kb_eval.py.
# Stage 1 (conservative): 0.83 sits between the logged unrelated (0.815) and related (0.839) scores.
# It is a first guess from two points; tune it from data/logs/similarity.txt after a week of use. -1.0 = off.
MIN_MEANING_SIM = 0.83
# Relative cutoff: keep passages scoring within MEANING_MARGIN of the best score. E5 scores sit in a narrow band,
# so a gap from the top score separates weak matches better than one fixed number. Set to 1.0 to turn it off.
MEANING_MARGIN = 0.02

# Chat context. The whole saved chat is sent to the model; the oldest turns are dropped only when
# the prompt would not fit the model's context window (see kb_chat.build_messages).
CHARS_PER_TOKEN = 2         # a safe guess for Persian and mixed text; real text is usually denser
PROMPT_RESERVE_TOKENS = 200 # space kept for the chat template and rounding

CATALOG = {
    "embed": {
        "e5-small": dict(name="Multilingual E5 Small", en="Small and fast multilingual meaning search", fa="جست‌وجوی معنایی چندزبانه، کوچک و سریع",
                         repo="phonology024/localllm-task-router", file="multilingual-e5-small-Q8_0.gguf", size=126_000_000,
                         pooling="mean", ctx=512, qpre="query: ", dpre="passage: "),  # keep 512: 511 made llama-server abort at start (GGML_ASSERT), see RELEASE_NOTES
    },
    "gen": {
        "qwen3.5-2b": dict(name="Qwen3.5 2B", en="Multilingual answer writer; reads and writes Persian well", fa="پاسخ‌نویس چندزبانه؛ فارسی را خوب می‌خواند و می‌نویسد",
                           repo="unsloth/Qwen3.5-2B-GGUF", file="Qwen3.5-2B-Q4_K_M.gguf", size=1_280_000_000, ctx=8192),
    },
    "rerank": {
        # UNVERIFIED: file name, size and licence are not confirmed, and llama.cpp b11146 loading it is not tested.
        "bge-reranker-base": dict(name="BGE reranker (base)",
                                   en="Reads the question with each passage and ranks them; second stage of search",
                                   fa="خواندن پرسش همراه با هر بند و رتبه‌بندی آن‌ها؛ مرحلهٔ دوم جست‌وجو",
                                   repo="jimi0209/bge-reranker-base-Q5_K_M-GGUF",
                                   file="bge-reranker-base-q5_k_m.gguf", size=200_000_000, ctx=512),
    },
}




DEFAULT_MODELS = {"embed": "e5-small", "gen": "qwen3.5-2b", "rerank": "bge-reranker-base"}

# Second stage of search: the reranker scores the best RERANK_TOP passages against the question.
# RERANK_MIN is the gate: passages scoring below it are dropped. It is off (None) until the
# 'retrieve.rerank' scores in kb.log have been checked on real questions; then set it there.
RERANK_TOP = 6
RERANK_MIN = None



READ_EXT = {
    "md", "mdx", "txt", "text", "log", "csv", "tsv", "json", "xml", "yml", "yaml", "srt", "tex", "rst", "org",
    "html", "htm", "xhtml", "rtf", "pdf", "docx", "pptx", "xlsx", "odt", "odp", "ods", "epub",
}


SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".svn", ".hg", ".venv", "venv"}


def externally_managed():
    """True on distros (Ubuntu 23.04+, Debian 12+, WSL...) that block system-wide pip installs."""
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return False  # a virtualenv is never blocked
    try:
        import sysconfig
        return os.path.exists(os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED"))
    except Exception:
        return False
