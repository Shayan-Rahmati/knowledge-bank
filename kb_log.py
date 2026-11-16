"""Deep logging for Knowledge Bank. Every event is one JSON line in data/logs/kb.log (rotated, 5 MB x 4).

Each line: {"t": time, "ev": event name, ...fields}. Long text is cut to 300 characters.
Uncaught errors in any thread are recorded with their traceback, so nothing fails silently.
Logging never raises: a logging problem must not break a search or an answer."""
import functools
import json
import logging
import os
import sys
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler
from kb_config import DATA, ENGINE_DIR

LOG_DIR = os.path.join(DATA, "logs")
LOG_FILE = os.path.join(LOG_DIR, "kb.log")
_lock = threading.Lock()
_logger = None


def _get():
    global _logger
    if _logger is None:
        os.makedirs(LOG_DIR, exist_ok=True)
        lg = logging.getLogger("kb")
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        h = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=4, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(message)s"))
        lg.addHandler(h)
        _logger = lg
    return _logger


# KB_REDACT=1 hides question text, answers and passage text in kb.log, so the log can be shared in a bug report.
REDACT = os.environ.get("KB_REDACT", "0") == "1"
REDACT_KEYS = {"question", "raw", "text", "sentences", "passages_sent", "tail", "sent"}


def _redact(k, v):
    if not REDACT or k not in REDACT_KEYS:
        return v
    if isinstance(v, str):
        return "[redacted %d chars]" % len(v)
    if isinstance(v, (list, tuple)):
        return "[redacted %d items]" % len(v)
    return "[redacted]"


def _clean(v, depth=0):
    if isinstance(v, str):
        return v if len(v) <= 300 else v[:300] + "...(%d chars)" % len(v)
    if isinstance(v, float):
        return round(v, 5)
    if isinstance(v, (list, tuple)):
        if depth > 2:
            return "[...]"
        return [_clean(x, depth + 1) for x in list(v)[:40]] + (["...(%d items)" % len(v)] if len(v) > 40 else [])
    if isinstance(v, dict):
        if depth > 2:
            return "{...}"
        return {str(k): _clean(x, depth + 1) for k, x in list(v.items())[:40]}
    if v is None or isinstance(v, (int, bool)):
        return v
    return _clean(str(v), depth)


_ctx = threading.local()


def qhash(text):
    """A short id for a question, so every line about one question can be found with grep."""
    import hashlib
    return hashlib.sha1((text or "").encode("utf-8", "replace")).hexdigest()[:8]


def set_qid(qid):
    _ctx.qid = qid


def log(event, **fields):
    try:
        rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S") + ("%.3f" % (time.time() % 1))[1:],
               "th": threading.current_thread().name, "ev": event}
        if getattr(_ctx, "qid", None):
            rec["qid"] = _ctx.qid
        rec.update({k: _clean(_redact(k, v)) for k, v in fields.items()})
        with _lock:
            _get().debug(json.dumps(rec, ensure_ascii=False, default=str))
    except Exception:
        pass


def error(where, exc=None):
    """Records an exception with its full traceback. Call it wherever an exception is caught and handled."""
    log("error", where=where, error=repr(exc) if exc is not None else "",
        trace=traceback.format_exc() if sys.exc_info()[0] else "")


def install_hooks():
    """Records any uncaught exception, including ones raised in background threads."""
    old = sys.excepthook

    def hook(tp, val, tb):
        log("uncaught", type=tp.__name__, error=str(val), trace="".join(traceback.format_exception(tp, val, tb)))
        old(tp, val, tb)
    sys.excepthook = hook

    def thook(args):
        log("thread_uncaught", thread=args.thread.name if args.thread else "", type=args.exc_type.__name__,
            error=str(args.exc_value), trace="".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = thook


def install_qt_handler():
    """Qt prints errors from window handlers to the terminal only, where they are easy to miss. This writes them to the log too."""
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    except Exception:
        return
    names = {QtMsgType.QtDebugMsg: "debug", QtMsgType.QtInfoMsg: "info", QtMsgType.QtWarningMsg: "warning",
             QtMsgType.QtCriticalMsg: "critical", QtMsgType.QtFatalMsg: "fatal"}

    def handler(mode, ctx, msg):
        log("qt", level=names.get(mode, str(mode)), message=msg, file=getattr(ctx, "file", "") or "",
            line=getattr(ctx, "line", 0) or 0)
    qInstallMessageHandler(handler)


def snapshot(core, path=None):
    """Writes a full picture of the system to data/logs/diagnostic.txt: versions, files, index, models, engine, settings.
    Each part is guarded, so one broken part does not hide the rest. Returns the text."""
    import platform
    lines = ["Knowledge Bank diagnostic  %s" % time.strftime("%Y-%m-%d %H:%M:%S"), ""]

    def sec(title, fn):
        lines.append("== " + title)
        try:
            lines.extend(str(x) for x in fn())
        except Exception as e:
            lines.append("  (failed: %r)" % e)
        lines.append("")

    def env():
        out = ["python " + sys.version.replace("\n", " "), "platform " + platform.platform(), "data " + DATA]
        for mod in ("numpy", "PySide6", "pypdf"):
            try:
                m = __import__(mod)
                out.append("%s %s" % (mod, getattr(m, "__version__", "?")))
            except Exception as e:
                out.append("%s: not importable (%s)" % (mod, e.__class__.__name__))
        import sqlite3
        out.append("sqlite " + sqlite3.sqlite_version)
        return out

    def settings():
        return ["%s = %r" % (k, v) for k, v in sorted(core.settings.items())] + ["off-list: %r" % sorted(core.off)]

    def sources():
        out = []
        for s in core.sources:
            out.append("#%s %s %s" % (s.get("id"), s.get("kind"), s.get("path")))
        return out or ["(no sources)"]

    def files():
        rows = core.st.q("SELECT status, COUNT(*) FROM files GROUP BY status")
        out = ["files by status: %r" % dict(rows)]
        bad = core.st.q("SELECT path, status, note FROM files WHERE status != 'ok' LIMIT 30")
        out += ["  %s [%s] %s" % r for r in bad]
        return out

    def index():
        ix = core.ix
        nchunks = core.st.q("SELECT COUNT(*) FROM chunks")[0][0]
        nvec = core.st.q("SELECT COUNT(*) FROM chunks c JOIN vecs v ON v.h = c.h")[0][0]
        out = ["chunks %d, with vectors %d, index N=%d, dim=%d" % (nchunks, nvec, ix.N, ix.dim)]
        out.append("matrix ready: %s  have.any: %s" % (ix.mat is not None, bool(ix.have is not None and ix.have.any())))
        return out

    def models():
        out = []
        for role in ("embed", "gen"):
            try:
                e = core.model_entry(role)
                p = core.model_path(role)
                size = os.path.getsize(p) if os.path.exists(p) else None
                out.append("%s: %s file=%s size=%s expected=%s" % (role, e.get("name"), os.path.basename(p), size, e.get("size")))
            except Exception as ex:
                out.append("%s: %r" % (role, ex))
        return out

    def engine():
        out = []
        try:
            out.append("binary: %s" % core.engine.binary())
        except Exception as e:
            out.append("binary: %r" % e)
        out.append("running: %s" % {r: bool(core.engine.is_running(r)) for r in ("embed", "gen")})
        out.append("last exits: %r" % getattr(core.engine, "last_exit", {}))
        pidfile = os.path.join(ENGINE_DIR, "pids.json")
        if os.path.exists(pidfile):
            with open(pidfile, encoding="utf-8", errors="replace") as f:
                out.append("pids.json: %s" % f.read())
        else:
            out.append("pids.json: (none)")
        for role in ("embed", "gen"):
            lp = os.path.join(DATA, "logs", "%s.log" % role)
            if os.path.exists(lp):
                with open(lp, "rb") as f:
                    f.seek(0, 2)
                    f.seek(max(0, f.tell() - 1200))
                    out.append("%s.log tail: %s" % (role, f.read().decode("utf-8", "replace").strip()[-800:]))
        return out

    def last_logs():
        out = []
        for name in ("engine_exit.txt", "engine_errors.txt", "chat_errors.txt", "similarity.txt"):
            p = os.path.join(DATA, "logs", name)
            if os.path.exists(p):
                with open(p, encoding="utf-8", errors="replace") as f:
                    out.append("-- %s (last 15 lines):" % name)
                    out.extend(f.read().splitlines()[-15:])
        return out or ["(none)"]

    sec("environment", env)
    sec("settings and off-list", settings)
    sec("sources", sources)
    sec("files", files)
    sec("index", index)
    sec("models", models)
    sec("engine", engine)
    sec("recent error files", last_logs)
    text = "\n".join(lines)
    target = path or os.path.join(LOG_DIR, "diagnostic.txt")
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    log("diagnostic", path=target)
    return text


# ---------------------------------------------------------------- debug trace of every function
# One line per call in data/logs/debug.log: the function, its arguments (summarised), what it returned or raised,
# and how long it took. Off by default for users; set KB_DEBUG=1 to turn it on. Logging itself is never traced.

DEBUG_ON = os.environ.get("KB_DEBUG", "0") == "1"
_dbg_logger = None
_dbg_lock = threading.Lock()
TRACE_MODULES = ["kb_core", "kb_store", "kb_chat", "kb_engine", "kb_net", "kb_extract", "kb_text", "kb_ui", "kb_eval"]
# functions too frequent to be useful (called per token, per pixel, per paint)
SKIP_FUNCS = {"norm", "words", "stem", "tokens", "chash", "thash", "posix", "edit_distance", "word_root",
              "sentences_plain", "answer_language", "is_fa", "text_quality", "clean_think",
              # window helpers, called on every repaint (about half of all trace lines in the last run)
              "T", "fd", "rt", "dir_of", "esc", "svg_icon", "svg_file", "fmt_size",
              # per-call state checks that run many times a second
              "is_on", "comp_state", "model_entry", "model_path", "rconn", "q", "sel", "binary",
              "update_snapshot", "have_mod", "asset_ok", "meaning_ready", "_json_list", "_json_obj"}
SKIP_PREFIX = ("paint", "event", "eventFilter", "_detail", "sizeHint", "minimumSizeHint", "data", "rowCount",
               "columnCount", "index", "flags", "editorEvent", "mouse", "key", "wheel", "resize", "hover",
               "enter", "leave", "focus", "_on_", "__")
SKIP_SUFFIX = ("Event",)


def _dbg():
    global _dbg_logger
    if _dbg_logger is None:
        os.makedirs(LOG_DIR, exist_ok=True)
        lg = logging.getLogger("kbdbg")
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        h = RotatingFileHandler(os.path.join(LOG_DIR, "debug.log"), maxBytes=20_000_000, backupCount=5, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(message)s"))
        lg.addHandler(h)
        _dbg_logger = lg
    return _dbg_logger


def _short(v):
    """A short, safe description of a value for the debug line."""
    try:
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return round(v, 5) if isinstance(v, float) else v
        if isinstance(v, str):
            return v if len(v) <= 120 else v[:120] + "...(%d)" % len(v)
        if isinstance(v, bytes):
            return "bytes[%d]" % len(v)
        if isinstance(v, (list, tuple, set, frozenset)):
            return "%s[%d]" % (type(v).__name__, len(v))
        if isinstance(v, dict):
            return "dict[%d]{%s}" % (len(v), ",".join(str(k) for k in list(v)[:8]))
        shape = getattr(v, "shape", None)
        if shape is not None:
            return "%s%s" % (type(v).__name__, tuple(shape))
        return "<%s>" % type(v).__name__
    except Exception:
        return "<?>"


def dbg(event, **fields):
    if not DEBUG_ON:
        return
    try:
        rec = {"t": time.strftime("%H:%M:%S") + ("%.3f" % (time.time() % 1))[1:],
               "th": threading.current_thread().name[:14], "ev": event}
        rec.update({k: _short(v) for k, v in fields.items()})
        with _dbg_lock:
            _dbg().debug(json.dumps(rec, ensure_ascii=False, default=str))
    except Exception:
        pass


def _wrap(fn, qual):
    is_method = qual.count(".") >= 2                  # module.Class.method: the first argument is self
    @functools.wraps(fn)
    def traced(*a, **k):
        if not DEBUG_ON:
            return fn(*a, **k)
        t0 = time.time()
        shown = a[1:] if is_method else a
        try:
            r = fn(*a, **k)
        except BaseException as e:
            dbg("raise", fn=qual, sec=round(time.time() - t0, 4), args=[_short(x) for x in shown],
                kwargs={kk: _short(vv) for kk, vv in k.items()}, error=repr(e)[:200])
            raise
        dbg("call", fn=qual, sec=round(time.time() - t0, 4), args=[_short(x) for x in shown],
            kwargs={kk: _short(vv) for kk, vv in k.items()}, ret=_short(r))
        return r
    traced.__kb_traced__ = True
    return traced


def _skip(name):
    if name == "__init__":
        return False
    return name.startswith(SKIP_PREFIX) or name.endswith(SKIP_SUFFIX) or name in SKIP_FUNCS


def enable_debug_trace():
    """Wraps every function and method of the app's modules so each call is written to debug.log.
    Module-level references to a function (from x import f) are replaced too, so every call site is traced."""
    import importlib, inspect
    if not DEBUG_ON:
        return 0
    mods = []
    for name in TRACE_MODULES:
        try:
            mods.append(importlib.import_module(name))
        except Exception as e:
            dbg("trace.skip_module", module=name, error=repr(e)[:160])
    replace = {}                                         # id(original) -> wrapper
    n = 0
    for mod in mods:
        for name, obj in list(vars(mod).items()):
            if name.startswith("__"):
                continue
            if inspect.isfunction(obj) and obj.__module__ == mod.__name__ and not getattr(obj, "__kb_traced__", False):
                if _skip(name):
                    continue
                w = _wrap(obj, "%s.%s" % (mod.__name__, name))
                replace[id(obj)] = w
                setattr(mod, name, w)
                n += 1
            elif inspect.isclass(obj) and obj.__module__ == mod.__name__:
                for mname, m in list(vars(obj).items()):
                    if not inspect.isfunction(m) or getattr(m, "__kb_traced__", False) or _skip(mname):
                        continue
                    w = _wrap(m, "%s.%s.%s" % (mod.__name__, name, mname))
                    replace[id(m)] = w
                    setattr(obj, mname, w)
                    n += 1
    for mod in mods:                                     # module-level aliases created by "from x import f"
        for name, obj in list(vars(mod).items()):
            if id(obj) in replace and inspect.isfunction(obj):
                setattr(mod, name, replace[id(obj)])
    dbg("trace.enabled", functions=n, modules=[m.__name__ for m in mods])
    return n
