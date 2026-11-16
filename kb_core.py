"""Application logic: sources, indexing, search, answers, and background work."""
import os
import sys
import re
import json
import time
import math
import threading
import zipfile
import subprocess
import traceback
import shutil
import importlib
import urllib.request, urllib.error, urllib.parse
from kb_config import ANSWER_SENTENCES, MIN_MEANING_SIM, lower_priority, watch_seconds, snapshot_seconds, RERANK_TOP, RERANK_MIN
from kb_text import norm as text_norm
from kb_engine import *
from kb_chat import ChatStore, build_messages
from kb_text import query_terms
from kb_log import log, error, install_hooks, qhash, set_qid

T_NET = ("Could not reach the Python package server. Check the connection, or set a proxy in "
         "Downloads & models, or install offline with: python3 kb.py --wheels <folder>")


MOD_CACHE = {}


def have_mod(name):
    """True only if the package imports. A broken package counts as missing."""
    v = MOD_CACHE.get(name)
    if v is None or time.time() - v[0] > 5:
        ok = False
        try:
            if importlib.util.find_spec(name) is not None:
                importlib.import_module(name)
                ok = True
        except Exception as e:
            MOD_ERR[name] = "%s: %s" % (type(e).__name__, str(e)[:120])
        v = MOD_CACHE[name] = (time.time(), ok)
    return v[1]


MOD_ERR = {}

# Meaning similarity a sentence needs to be linked to a passage (see link_sentences).
# UNCALIBRATED: cited sentences in the logs scored 0.80 to 0.83. Set it from the 'cite.link' lines in kb.log.
LINK_SEM_MIN = MIN_MEANING_SIM          # Stage 4: a citation needs the same meaning floor as a passage
# Bonus for words a sentence shares with a passage. Sentences in another language get no bonus, so meaning decides.
LEX_BONUS = 0.15

# Share of the question's weighted words that the passages must contain before the model is asked.
# UNCALIBRATED: set from the 'coverage' lines in kb.log, using answerable and unanswerable questions.
COVERAGE_MIN = 0.75

# Characters of passage text sent to the model per answer (about half the answer model's prompt room).
# UNCALIBRATED: a speed and quality trade-off; each extra 1000 characters adds prompt time on CPU.
PASSAGE_CHAR_BUDGET = 2400
PASSAGE_CHARS = 450                      # the text length each passage is shown with (see ask)
MAX_PASSAGES = 6                         # Stage 1: never send more than this many passages, however short they are

# System prompts: deliberately minimal. The model is not told how long to be, how to format, or what to refuse.
SYS_PLAIN = "Answer the user's question."
SYS_EXCERPTS = "Answer the user's question. The numbered excerpts below may help; use them where they are relevant."


def cite_sentence(sent, ns):
    """'fact.' with citations -> 'fact [1][2].': the numbers go before the sentence's own final punctuation, as the prompt asks."""
    end = sent[-1] if sent and sent[-1] in ".!?\u061f\u06d4" else ""
    body = sent[:-1] if end else sent
    return body + (" " + "".join("[%d]" % n for n in ns) if ns else "") + end


class App:
    def __init__(self):
        for d in (DATA, BANK, TEXTDIR, MODELS, ENGINE_DIR):
            os.makedirs(d, exist_ok=True)
        install_hooks()
        self.st = Store()
        self.ix = Index(self.st)
        self.chats = ChatStore(self.st)
        self.np = None
        self.sync_lock = threading.Lock()
        self.closing = False
        self.warm_lock = threading.Lock()
        self.prog = {"sync": {"busy": False, "msg": "", "done": 0, "total": 0, "err": ""},
                     "meaning": {"busy": False, "paused": False, "done": 0, "total": 0, "err": "", "eta": None},
                     "pip": {"busy": False, "msg": "", "err": "", "done": 0, "total": 0, "log": ""}}
        self.stop_meaning = False
        self.off = self._load("off", list, [])
        self.off = set(self.off) if isinstance(self.off, list) else set()
        self.removed = set(self._load("removed", list, []))   # files wiped from the bank; scans skip them until switched back on
        self.sources = self._load("sources", list, [])
        defaults = {"ai": True, "answer_length": "normal", "results": "standard", "use_meaning": True, "show_match": True,
                    "grounded": True,
                    "resources": "balanced",
                    "lang": "en", "theme": "system", "accent": "blue", "hf_host": "auto", "auto_meaning": True,
                    "auto_setup": True,
                    "precise_bullets": False, "proxy": "", "models": {}, "custom_urls": {}, "engine_path": ""}
        self.settings = dict(defaults, **self._load("settings", dict, {}))
        log("start", version=VERSION, data=DATA, sources=[(x.get("kind"), x.get("path")) for x in self.sources],
            off=sorted(self.off), settings={k: self.settings.get(k) for k in ("lang", "use_meaning", "results", "ai", "resources")})
        if self.settings.get("ai_default") != 2:          # AI answers are on by default, one time
            self.settings["ai"] = True
            self.settings["ai_default"] = 2
            self.st.put("settings", self.settings)
        self.tree_cache = {}
        self.dirty = 0
        self._cs = {}
        self.engine = Engine(self)
        self.dm = DownloadManager(self)
        self.apply_vec_model()
        self.booted = False
        self.snap = None
        self.update_snapshot()
        threading.Thread(target=self.boot, daemon=True).start()
        if os.environ.get("KB_TEST"):
            # test mode: no folder watcher, downloads, or engine start, so tests run fast and offline
            return
        self.stop_evt = threading.Event()
        self.gen_abort = threading.Event()     # set by the Stop button; the engine stops reading the reply when it is set
        self.question_busy = threading.Event() # set while a question is being answered; background indexing waits for it
        self.watch_thread = threading.Thread(target=self.watch_loop, daemon=True)
        self.watch_thread.start()
        threading.Thread(target=self.snap_loop, daemon=True).start()
        self.start_prewarm()
        threading.Thread(target=self.ensure_defaults, daemon=True).start()
        threading.Thread(target=self.font_loop, daemon=True).start()
        threading.Thread(target=self.auto_setup_loop, daemon=True).start()
        threading.Thread(target=self.auto_meaning_loop, daemon=True).start()

    # --- settings and catalog
    def _load(self, key, kind, default):
        """A saved value of the wrong type (for example, from a damaged file) falls back to its default."""
        value = self.st.get(key, default)
        return value if isinstance(value, kind) else default

    def save_settings(self):
        log("settings.save", settings={k: self.settings.get(k) for k in sorted(self.settings)})
        self.st.put("settings", self.settings)
        self._cs.clear()

    def sel(self, role):
        s = (self.settings.get("models") or {}).get(role)
        return s if s in CATALOG[role] else DEFAULT_MODELS[role]

    def model_entry(self, role):
        return CATALOG[role][self.sel(role)]

    def model_path(self, role):
        e = self.model_entry(role)
        p = os.path.join(MODELS, role, e["file"])
        legacy = os.path.join(MODELS, e["repo"].split("/")[-1], e["file"])   # where the old HTML version kept the model
        if not os.path.isfile(p) and os.path.isfile(legacy):
            return legacy
        return p

    def apply_vec_model(self):
        # Every setting that changes the vectors is part of the tag. Vectors made with another prefix, pooling or
        # context length live in another space; comparing them with new question vectors gives wrong scores.
        e = self.model_entry("embed")
        ident = "emb:" + "|".join(str(e.get(k)) for k in ("file", "pooling", "ctx", "qpre", "dpre"))
        if self.st.get("vec_model") != ident:
            self.st.x("DELETE FROM vecs")
            self.st.put("vec_model", ident)

    def opener(self):
        p = (self.settings.get("proxy") or "").strip()
        if p:                                             # a proxy set by hand wins over the system one
            return urllib.request.build_opener(urllib.request.ProxyHandler({"http": p, "https": p}))
        return urllib.request.build_opener(urllib.request.ProxyHandler(system_proxies()))

    def hosts(self):
        h = (self.settings.get("hf_host") or "auto").strip()
        return [h.rstrip("/")] if h and h != "auto" else list(HF_HOSTS)

    def model_urls(self, role):
        e = self.model_entry(role)
        key = "%s:%s" % (role, self.sel(role))
        out = []
        c = (self.settings.get("custom_urls") or {}).get(key)
        if c:
            out.append(c)
        out += ["%s/%s/resolve/main/%s" % (h, e["repo"], e["file"]) for h in self.hosts()]
        return out

    def engine_urls(self, variant="gpu"):
        """Download sources for one engine build: 'gpu' (Vulkan) or 'cpu'. Each build is installed on its own."""
        tag, assets = None, {}
        c = (self.settings.get("custom_urls") or {}).get("engine")
        urls = [c] if (c and variant == "cpu") else []
        try:
            req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % ENGINE_REPO,
                                         headers={"User-Agent": "KnowledgeBank/4", "Accept": "application/vnd.github+json"})
            with self.opener().open(req, timeout=15) as r:
                j = json.loads(r.read().decode("utf-8"))
            tag = j.get("tag_name")
            assets = {a["name"]: a["browser_download_url"] for a in j.get("assets", [])}
        except Exception:
            pass
        want = engine_asset_suffix()
        backend = gpu_backend()
        if variant == "gpu":
            if not backend:
                return []
            arch = "arm64" if "arm64" in want else "x64"
            ext = ".zip" if want.endswith(".zip") else ".tar.gz"
            gpu = [(n, u) for n, u in assets.items() if "-bin-%s-%s" % (engine_os_token(), backend) in n
                   and n.endswith(ext) and arch in n and "cudart" not in n]
            if gpu:
                log("engine.choice", variant="gpu", backend=backend, asset=gpu[0][0])
                urls.append(gpu[0][1])
            return list(dict.fromkeys(urls))
        # CPU build: the release asset for this platform, then the pinned release file
        for n, u in assets.items():
            if n.endswith(want) and "cudart" not in n:
                urls.append(u)
                break
        tag = tag or ENGINE_PINNED
        urls.append("https://github.com/%s/releases/download/%s/llama-%s%s" % (ENGINE_REPO, ENGINE_PINNED, ENGINE_PINNED, want))
        return list(dict.fromkeys(urls))

    def assets(self):
        """Two engine downloads: the GPU (Vulkan) build when the platform has one, and always the CPU build as fallback.
        Each is installed into its own folder (llama-gpu-… / llama-cpu-…)."""
        ext = ".zip" if os.name == "nt" else ".tar.gz"
        out = []
        if gpu_backend():
            out.append({"key": "engine", "role": "engine", "title": "llama.cpp engine (GPU)", "kind": "engine",
                        "variant": "gpu", "est": 18_000_000,
                        "dest": os.path.join(ENGINE_DIR, "engine-download-gpu" + ext),
                        "urls_fn": (lambda: self.engine_urls("gpu"))})
        out.append({"key": "engine-cpu", "role": "engine", "title": "llama.cpp engine (CPU)", "kind": "engine",
                    "variant": "cpu", "est": 18_000_000,
                    "dest": os.path.join(ENGINE_DIR, "engine-download-cpu" + ext),
                    "urls_fn": (lambda: self.engine_urls("cpu"))})
        for pkg in WHEEL_PACKAGES:
            out.append({"key": "pkg:" + pkg, "role": "pkg", "title": "Python package " + pkg, "kind": "wheel",
                        "est": 12_000_000 if pkg == "numpy" else 400_000,
                        "dest": self.wheel_dest(pkg), "urls_fn": (lambda p=pkg: self.wheel_urls(p))})
        for role in ("embed", "gen", "rerank"):
            e = self.model_entry(role)
            out.append({"key": "%s:%s" % (role, self.sel(role)), "role": role, "title": e["name"], "kind": "file",
                        "est": e["size"], "dest": self.model_path(role), "urls_fn": (lambda r=role: self.model_urls(r))})
        return out

    def asset_ok(self, a):
        if a["kind"] == "engine":
            return self.engine.installed(a.get("variant", "cpu"))
        if a["kind"] == "wheel":
            return have_mod(a["key"].split(":", 1)[1])
        return self.file_ok(a["dest"], a["est"])

    def install_engine_from(self, path, variant="cpu"):
        """Accepts the official release archive (.tar.gz or .zip), or a bare llama-server binary.
        variant 'gpu' or 'cpu': the build goes into its own folder, and only older folders of that variant are removed."""
        import tarfile
        os.makedirs(ENGINE_DIR, exist_ok=True)
        dest = os.path.join(ENGINE_DIR, "llama-%s-%s" % (variant, time.strftime("%Y%m%d-%H%M%S")))
        os.makedirs(dest, exist_ok=True)
        base = os.path.realpath(dest)
        if tarfile.is_tarfile(path):
            with tarfile.open(path) as t:
                for m in t.getmembers():
                    if not os.path.realpath(os.path.join(dest, m.name)).startswith(base):
                        raise ValueError("unsafe path in archive")
                t.extractall(dest)
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                for n in z.namelist():
                    if not os.path.realpath(os.path.join(dest, n)).startswith(base):
                        raise ValueError("unsafe path in archive")
                z.extractall(dest)
        else:
            shutil.copyfile(path, os.path.join(dest, "llama-server.exe" if os.name == "nt" else "llama-server"))
        want = "llama-server.exe" if os.name == "nt" else "llama-server"
        found = None
        for root, _d, files in os.walk(dest):
            if want in files:
                found = os.path.join(root, want)
                break
        if not found:
            shutil.rmtree(dest, ignore_errors=True)
            raise ValueError("No llama-server found in that file.")
        if os.name != "nt":
            for root, _d, files in os.walk(dest):
                for n in files:
                    if n.startswith("llama") or n.endswith(".so") or ".so." in n:
                        try:
                            os.chmod(os.path.join(root, n), 0o755)
                        except OSError:
                            pass
        # remove older folders of this same build (and folders from the single-build installs of earlier versions)
        for d in os.listdir(ENGINE_DIR):
            p = os.path.join(ENGINE_DIR, d)
            old = d.startswith("llama-%s-" % variant) or re.match(r"llama-\d{8}-", d)
            if os.path.isdir(p) and p != dest and old:
                shutil.rmtree(p, ignore_errors=True)
        self.engine.stop()
        self.engine.forget_binary()
        self._cs.clear()
        log("engine.installed", variant=variant, folder=os.path.basename(dest))

    # --- helpers
    def try_numpy(self):
        if self.np is None:
            try:
                import numpy
                self.np = numpy
            except Exception:
                self.np = False
        return self.np or None

    def file_ok(self, p, est, strict_name=None):
        try:
            sz = os.path.getsize(p)
        except OSError:
            return False
        if sz < 1:
            return False
        name = strict_name or p
        if name.endswith(".gguf"):
            try:
                with open(p, "rb") as f:
                    return f.read(4) == b"GGUF" and sz > est * 0.5
            except OSError:
                return False
        return True

    def comp_state(self, role):
        c = self._cs.get(role)
        if c and time.time() - c[0] < 2.0:
            return c[1]
        e = self.model_entry(role)
        eng = self.engine.binary() is not None
        fok = self.file_ok(self.model_path(role), e["size"])
        pips = ["numpy"] if role == "embed" else []
        miss = [m for m in pips if not have_mod(m)]
        v = {"files_ok": fok, "engine_ok": eng, "pip_missing": miss, "model": e["name"],
             "ready": eng and fok and not miss, "enabled": True}
        self._cs[role] = (time.time(), v)
        return v

    def on_files_changed(self):
        self._cs.clear()
        self.dirty += 1

    def is_on(self, path):
        for o in self.off:
            if path == o or path.startswith(o.rstrip("/") + "/"):
                return False
        return True

    # --- index
    def reload_index(self):
        self.ix.reload(self.try_numpy())

    # --- sources
    def add_source(self, path):
        path = os.path.abspath(os.path.expanduser(path.strip().strip('"')))
        if not os.path.exists(path):
            raise ValueError("Path not found: " + path)
        for s in self.sources:
            if s["path"] == path:
                return s
        sid = max([s["id"] for s in self.sources] + [0]) + 1
        s = {"id": sid, "path": path, "kind": "dir" if os.path.isdir(path) else "file",
             "name": os.path.basename(path.rstrip("/\\")) or path}
        self.sources.append(s)
        self.st.put("sources", self.sources)
        return s

    def remove_source(self, sid):
        self.sources = [s for s in self.sources if s["id"] != sid]
        self.st.put("sources", self.sources)

    def forget_file(self, p):
        """Wipes one file from the bank: its text, chunks, keyword index and meaning vectors, and its entry in the list.
        It stays out of later scans until it is switched back on. The file on disk is not touched."""
        p = posix(p).rstrip("/")
        self.drop_file(p)
        with self.st.lock:
            # only vectors no chunk uses any more; a passage with the same text in another file keeps its vector
            self.st.db.execute("DELETE FROM vecs WHERE h NOT IN (SELECT h FROM chunks)")
            self.st.db.commit()
        self.removed.add(p)
        self.off.discard(p)
        for s in list(self.sources):
            if s["kind"] == "file" and posix(s["path"]).rstrip("/") == p:
                self.sources = [x for x in self.sources if x["id"] != s["id"]]
                self.st.put("sources", self.sources)
        self.st.put("removed", sorted(self.removed))
        self.st.put("off", sorted(self.off))
        self._cs.clear()
        log("file.forget", path=p)

    def scan(self):
        out = []
        for s in self.sources:
            p = s["path"]
            if s["kind"] == "file":
                if os.path.isfile(p) and posix(p) not in self.removed:
                    try:
                        stt = os.stat(p)
                        out.append((posix(p), s["id"], os.path.basename(p), stt.st_size, int(stt.st_mtime)))
                    except OSError:
                        pass
                continue
            if not os.path.isdir(p):
                continue
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
                for fn in files:
                    ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
                    if ext not in READ_EXT or fn.startswith(("~$", ".")):
                        continue
                    fp = os.path.join(root, fn)
                    if posix(fp) in self.removed:
                        continue
                    try:
                        stt = os.stat(fp)
                    except OSError:
                        continue
                    out.append((posix(fp), s["id"], posix(os.path.relpath(fp, p)), stt.st_size, int(stt.st_mtime)))
        return out

    def changes(self):
        cur = {r[0]: (r[1], r[2], r[3], r[4], r[5]) for r in
               self.st.q("SELECT path, src, rel, size, mtime, status FROM files")}
        found = self.scan()
        seen, todo = set(), []
        for (p, sid, rel, size, mt) in found:
            seen.add(p)
            c = cur.get(p)
            if c is None or c[2] != size or c[3] != mt or c[0] != sid or c[1] != rel:
                todo.append((p, sid, rel, size, mt))
        gone = [p for p in cur if p not in seen]
        return todo, gone

    def _extract_all(self, todo):
        """Yields (item, text, note) for each file. Uses worker processes, since Qt is running in the main one."""
        level = self.settings.get("resources", "balanced")
        n = workers_for(level)
        light = lower_priority(level)
        # Light reads in a single worker process at the lowest priority. Reading inline would run the heavy parsing
        # in the window's own process at normal priority, which is what made Light use a full processor.
        if (n > 1 or light) and (todo if light else len(todo) > 3):
            try:
                import multiprocessing as mp
                from concurrent.futures import ProcessPoolExecutor
                nice = 15 if light else 5
                with ProcessPoolExecutor(max_workers=max(1, n), mp_context=mp.get_context("spawn")) as ex:
                    for item, (text, note) in zip(todo, ex.map(extract_job, [t[0] for t in todo], [nice] * len(todo), chunksize=2)):
                        yield item, text, note
                return
            except Exception:
                traceback.print_exc()
        for item in todo:
            text, note = extract_file(item[0])
            log("extract.reader", path=os.path.basename(item[0]), reader=note, chars=len(text or ""))
            yield item, text, note

    def sync(self, force=False):
        log("sync.start", force=force)
        t_sync = time.time()
        if not self.sync_lock.acquire(blocking=False):
            return
        P = self.prog["sync"]
        todo, gone = [], []
        try:
            P.update(busy=True, msg="scan", done=0, total=0, err="")
            todo, gone = self.changes()
            P["total"] = len(todo) + len(gone)
            for p in gone:
                self.drop_file(p)
                P["done"] += 1
            for item, text, note in self._extract_all(todo):
                self.store_file(item, text, note)
                P["done"] += 1
                P["msg"] = os.path.basename(item[0])
            self.prune_text()
            if todo or gone or force:
                self.tree_cache.clear()
                self.reload_index()
                self.dirty += 1
        except Exception as e:
            P["err"] = "%s: %s" % (type(e).__name__, e)
            error("sync", e)
            traceback.print_exc()
        finally:
            P.update(busy=False, msg="")
            self.sync_lock.release()
            log("sync.done", seconds=round(time.time() - t_sync, 2), changed=len(todo), removed=len(gone), error=P.get("err") or "", chunks=self.st.q("SELECT COUNT(*) FROM chunks")[0][0])

    def recheck_quality(self):
        """Re-checks files that an older version indexed."""
        if self.st.get("quality_v") == 4:
            return
        # first run of this version: re-read every file so the new normalising applies
        self.st.x("UPDATE files SET size=-1")
        self.st.put("quality_v", 4)
        return
        for path, th in self.st.q("SELECT path, th FROM files WHERE status='ok'"):
            try:
                with open(os.path.join(TEXTDIR, th + ".txt"), encoding="utf-8") as f:
                    t = f.read()
            except OSError:
                continue
            if text_quality(t) < QUALITY_MIN:
                with self.st.lock:
                    self.st.db.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM chunks WHERE path=?)", (path,))
                    self.st.db.execute("DELETE FROM chunks WHERE path=?", (path,))
                    self.st.db.execute("UPDATE files SET status='empty', nchunks=0, note=? WHERE path=?",
                                       ("unreadable: broken text encoding in this file", path))
                    self.st.db.commit()
                try:
                    os.remove(os.path.join(TEXTDIR, th + ".txt"))
                except OSError:
                    pass
        self.st.put("quality_v", 4)

    def drop_file(self, p):
        th = thash(p)
        with self.st.lock:
            self.st.db.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM chunks WHERE path=?)", (p,))
            self.st.db.execute("DELETE FROM chunks WHERE path=?", (p,))
            self.st.db.execute("DELETE FROM files WHERE path=?", (p,))
            self.st.db.commit()
        try:
            os.remove(os.path.join(TEXTDIR, th + ".txt"))
        except OSError:
            pass

    def store_file(self, item, text, note):
        p, sid, rel, size, mt = item
        if text and text_quality(text) < QUALITY_MIN:       # skip text whose encoding is broken
            text, note = "", "unreadable: broken text encoding in this file"
        th = thash(p)
        tp = os.path.join(TEXTDIR, th + ".txt")
        with self.st.lock:
            db = self.st.db
            db.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM chunks WHERE path=?)", (p,))
            db.execute("DELETE FROM chunks WHERE path=?", (p,))
            if len(text.strip()) < 3:
                try:
                    os.remove(tp)
                except OSError:
                    pass
                db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?)",
                           (p, sid, rel, size, mt, "empty", note or "no text", 0, th))
            else:
                with open(tp, "w", encoding="utf-8") as f:
                    f.write(text)
                cks = chunk_text(text)
                for i, c in enumerate(cks):
                    cur = db.execute("INSERT INTO chunks(path, idx, h, text) VALUES(?,?,?,?)", (p, i, chash(c), c))
                    db.execute("INSERT INTO fts(rowid, tok) VALUES(?,?)", (cur.lastrowid, " ".join(tokens(c))))
                db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?)",
                           (p, sid, rel, size, mt, "ok", note, len(cks), th))
            db.commit()

    def prune_text(self):
        keep = {r[0] + ".txt" for r in self.st.q("SELECT th FROM files WHERE status='ok'")}
        try:
            for fn in os.listdir(TEXTDIR):
                fp = os.path.join(TEXTDIR, fn)
                if fn not in keep or os.path.getsize(fp) == 0:
                    os.remove(fp)
        except OSError:
            pass
        with self.st.lock:
            self.st.db.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM chunks WHERE path NOT IN (SELECT path FROM files))")
            self.st.db.execute("DELETE FROM chunks WHERE path NOT IN (SELECT path FROM files)")
            self.st.db.execute("DELETE FROM vecs WHERE h NOT IN (SELECT h FROM chunks)")
            self.st.db.commit()

    def close(self):
        """Stops the background work and waits for a running index build, so the database closes cleanly."""
        self.closing = True
        self.stop_meaning = True
        self.stop_evt.set()                       # wake the watcher now, not after its 15-second sleep
        if self.watch_thread is not threading.current_thread():
            self.watch_thread.join(timeout=10)    # the watcher must not touch the database after this point
        t = time.time()
        try:
            while (self.prog["meaning"]["busy"] or self.sync_lock.locked() or getattr(self, "_snap_busy", False)) \
                    and time.time() - t < 5:           # the window waits here; a running index batch finishes in the background
                time.sleep(0.1)
        except KeyboardInterrupt:                 # Ctrl+C during shutdown: stop waiting and close anyway
            pass
        try:
            self.engine.stop()
        except Exception:
            pass
        try:
            self.st.close()
        except Exception:
            pass

    def watch_loop(self):
        while not self.closing:
            self.stop_evt.wait(watch_seconds(self.settings.get("resources", "balanced")))
            if self.closing:                      # checked again after waking: the database may be closing
                return
            try:
                if self.sources and not self.prog["sync"]["busy"] and not self.closing:
                    todo, gone = self.changes()
                    if todo or gone:
                        self.sync()
                        if self.settings.get("auto_meaning", True) and self.comp_state("embed")["ready"]:
                            self.start_meaning()
            except Exception:
                if not self.closing:              # errors during shutdown are expected, not reported
                    traceback.print_exc()

    FONT_TAG = "v33.003"          # the release tag that ships the fonts
    font_err = ""
    FONT_NAME = "Vazirmatn-Regular.ttf"

    def font_path(self):
        return os.path.join(DATA, "fonts", self.FONT_NAME)

    def ensure_font(self):
        """Downloads Vazirmatn once and caches it. Only a real TrueType or OpenType file is kept."""
        dest = self.font_path()
        if os.path.isfile(dest) and os.path.getsize(dest) > 50_000:
            return
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        name = self.FONT_NAME
        try:
            req = urllib.request.Request("https://api.github.com/repos/rastikerdar/vazirmatn/contents/fonts/ttf?ref=" + self.FONT_TAG,
                                         headers={"User-Agent": "KnowledgeBank/4", "Accept": "application/vnd.github+json"})
            with self.opener().open(req, timeout=15) as r:
                names = [x["name"] for x in json.loads(r.read().decode("utf-8"))]
            name = next((n for n in names if n.lower() == "vazirmatn-regular.ttf"), name)
        except Exception:
            pass                                       # otherwise use the usual file name
        urls = ["https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@%s/fonts/ttf/%s" % (self.FONT_TAG, name),
                "https://github.com/rastikerdar/vazirmatn/raw/%s/fonts/ttf/%s" % (self.FONT_TAG, name)]
        reasons = []
        for url in urls:
            try:
                with self.opener().open(urllib.request.Request(url, headers={"User-Agent": "KnowledgeBank/4"}), timeout=60) as r:
                    data = r.read()
                head = data[:4]
                if len(data) > 50_000 and head in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
                    tmp = dest + ".part"
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, dest)
                    self.font_err = ""
                    return
                ctype = (r.headers.get("Content-Type") or "?").split(";")[0]
                if data[:1] == b"<" or b"<html" in data[:300].lower():
                    what = "a web page (likely a network filter or proxy block)"
                else:
                    what = "%d bytes starting %s (%s)" % (len(data), data[:4].hex(), ctype)
                reasons.append("%s returned %s" % (urllib.parse.urlparse(url).netloc, what))
            except Exception as e:
                reasons.append("%s: %s" % (urllib.parse.urlparse(url).netloc, why(e)))
        self.font_err = "; ".join(reasons) or "download failed"
        print("Font not downloaded yet (%s). Retrying automatically every minute." % self.font_err)

    def boot(self):
        """Slow startup work (re-checking, loading the index) runs in the background."""
        try:
            self.recheck_quality()
            self.reload_index()
            self.on_files_changed()
            if self.settings.get("auto_meaning", True) and self.comp_state("embed")["ready"]:
                self.start_meaning()
        except Exception:
            traceback.print_exc()
        finally:
            self.booted = True

    FONT_RETRY_SECONDS = 60

    def wheel_urls(self, pkg):
        """Download URL for a package, from the package index."""
        mirror = (self.settings.get("pypi_mirror") or "").strip().rstrip("/")
        base = mirror or PYPI_BASE
        req = urllib.request.Request("%s/pypi/%s/json" % (base, pkg), headers={"User-Agent": "KnowledgeBank/4"})
        with self.opener().open(req, timeout=20) as r:
            info = json.loads(r.read().decode("utf-8"))
        f = pick_wheel(info.get("urls", []), (str(sys.version_info.major), str(sys.version_info.minor)), wheel_platform_tags())
        if not f:
            raise RuntimeError("no %s wheel for Python %s on this platform" % (pkg, sys.version.split()[0]))
        url = f["url"]
        if mirror:
            url = url.replace(PYPI_FILES, mirror + "/packages")
        return [url]

    def wheel_dest(self, pkg):
        return os.path.join(VENDOR, "_wheels", pkg + ".whl")

    def install_wheel(self, pkg, path):
        """Unpacks a wheel (a zip file) into the vendor folder."""
        import zipfile as _zf
        if not _zf.is_zipfile(path):
            raise ValueError("the downloaded %s is not a wheel archive" % pkg)
        os.makedirs(VENDOR_SITE, exist_ok=True)
        root = os.path.realpath(VENDOR_SITE)
        with _zf.ZipFile(path) as z:
            for n in z.namelist():
                if not os.path.realpath(os.path.join(root, n)).startswith(root + os.sep):
                    raise ValueError("unsafe path in wheel")
            z.extractall(root)
        if root not in sys.path:
            sys.path.insert(0, root)
        importlib.invalidate_caches()
        MOD_CACHE.clear()

    def font_present(self):
        p = self.font_path()
        return os.path.isfile(p) and os.path.getsize(p) > 50_000

    def font_loop(self):
        """Downloads the Persian font whenever it is missing, retrying in the background."""
        while not self.font_present() and not self.closing:
            self.ensure_font()
            if self.font_present():
                break
            time.sleep(self.FONT_RETRY_SECONDS)

    def ensure_defaults(self):
        """Installs pypdf and numpy if they are missing."""
        try:
            time.sleep(0.5)
            missing = [m for m in WHEEL_PACKAGES if not have_mod(m)]
            if missing:
                # same resume, sources, and proxy as the models
                self.dm.start(["pkg:" + m for m in missing])
        except Exception:
            pass

    def auto_setup_loop(self):
        """Keeps meaning search ready without any clicks: fetches the engine and the search model when they are missing."""
        wait = 30
        while not self.closing:
            time.sleep(wait)
            try:
                if not self.settings.get("auto_setup", True):
                    wait = 60
                    continue
                need = []
                if not all(self.asset_ok(a) for a in self.assets() if a["kind"] == "engine"):
                    need.append("engine")
                if not self.file_ok(self.model_path("embed"), self.model_entry("embed")["size"]):
                    need.append("embed:" + self.sel("embed"))
                if not need:
                    wait = 60
                    continue
                snap = {i["key"]: i for i in self.dm.snapshot()}
                if any(snap.get(k, {}).get("state") == "paused" for k in need):
                    wait = 60
                    continue
                if any(snap.get(k, {}).get("state") in ("running", "queued") for k in need):
                    wait = 30
                    continue
                failed = any(snap.get(k, {}).get("state") == "error" for k in need)
                wait = min(600, wait * 2) if failed else 30
                self.dm.start(need)
            except Exception:
                traceback.print_exc()
                wait = 120

    def auto_meaning_loop(self):
        """Builds the meaning index by itself, once the search model is ready and passages are not yet embedded."""
        last_try = 0.0
        while not self.closing:
            time.sleep(10)
            try:
                if not self.booted or not self.settings.get("auto_meaning", True):
                    continue
                P = self.prog["meaning"]
                if P["busy"] or P["paused"] or not self.comp_state("embed")["ready"]:
                    continue
                nvec = int(self.ix.have.sum()) if self.ix.have is not None else 0
                if self.ix.N == 0 or nvec >= self.ix.N:
                    continue
                if P.get("err") and time.time() - last_try < 300:
                    continue
                last_try = time.time()
                self.start_meaning()
            except Exception:
                traceback.print_exc()

    def prewarm(self):
        """Loads both models into memory as soon as they are on disk, so the first question does not wait."""
        with self.warm_lock:
            for role in ("embed", "gen", "rerank"):
                if role == "rerank" and not self.settings.get("use_rerank", False):
                    continue                  # the reranker is off by default: do not start it at launch
                try:
                    if self.engine.binary() is None or not self.file_ok(self.model_path(role), self.model_entry(role)["size"]):
                        continue
                    if not self.engine.is_running(role):
                        self.engine.ensure(role)
                except Exception:
                    traceback.print_exc()

    def start_prewarm(self):
        threading.Thread(target=self.prewarm, daemon=True).start()

    def restart_engines(self):
        """Stops both models and loads them again in the background, after the current load finishes."""
        def run():
            with self.warm_lock:
                self.engine.stop()
            self.prewarm()
        threading.Thread(target=run, daemon=True).start()

    def snap_loop(self):
        while not self.closing:
            time.sleep(snapshot_seconds(self.settings.get("resources", "balanced")))
            if self.closing:                       # closing started during the sleep: do not touch the database
                break
            self._snap_busy = True
            try:
                self.update_snapshot()
            except Exception as e:
                error("snapshot", e)
                traceback.print_exc()
            finally:
                self._snap_busy = False

    # --- tree
    def tree(self, sid, d):
        rows = self.tree_cache.get(sid)
        if rows is None:
            rows = self.tree_cache[sid] = [(r[0], r[1], r[2], r[3]) for r in
                                           self.st.q("SELECT path, rel, status, nchunks FROM files WHERE src=? ORDER BY rel", (sid,))]
        pre = (d + "/") if d else ""
        dirs, files = {}, []
        src = next((s for s in self.sources if s["id"] == sid), None)
        for (path, rel, status, nch) in rows:
            if not rel.startswith(pre):
                continue
            rest = rel[len(pre):]
            if "/" in rest:
                name = rest.split("/", 1)[0]
                dd = dirs.setdefault(name, {"n": 0, "on": 0})
                dd["n"] += 1
                dd["on"] += 1 if self.is_on(path) else 0
            else:
                files.append({"name": rest, "path": path, "status": status, "chunks": nch, "on": self.is_on(path)})
        dl = []
        for name, v in sorted(dirs.items(), key=lambda x: x[0].lower()):
            base = src["path"] if src else ""
            dl.append({"name": name, "dir": (pre + name), "path": posix(os.path.join(base, pre + name)), "count": v["n"],
                       "on": v["on"] == v["n"], "partial": 0 < v["on"] < v["n"]})
        files.sort(key=lambda x: x["name"].lower())
        return {"dirs": dl, "files": files[:2000], "more": max(0, len(files) - 2000)}

    def set_sel(self, path, on):
        """Turns a file or folder on or off. Turning one item on inside an excluded folder keeps its
        siblings excluded: the folder's exclusion is replaced by one exclusion per file it contains."""
        import traceback
        callers = ["%s:%s" % (f.name, f.lineno) for f in traceback.extract_stack()[-6:-1]]
        log("set_sel", path=path, on=on, off_before=len(self.off), callers=callers)
        path = posix(path).rstrip("/")
        if on:
            if path in self.removed:                  # switching a wiped file back on lets it come back
                self.removed.discard(path)
                self.st.put("removed", sorted(self.removed))
            ancestors = [o for o in self.off if path.startswith(o + "/")]
            for a in ancestors:
                self.off.discard(a)
                for (fp,) in self.st.q("SELECT path FROM files"):
                    fp = posix(fp)
                    if (fp.startswith(a + "/") and not (fp == path or fp.startswith(path + "/"))):
                        self.off.add(fp)
            self.off = {o for o in self.off if not (o == path or o.startswith(path + "/"))}
        else:
            self.off = {o for o in self.off if not o.startswith(path + "/")}
            self.off.add(path)
        self.st.put("off", sorted(self.off))
        self._cs.clear()
        log("set_sel.done", off_after=len(self.off))

    # --- retrieval
    def embed_texts(self, texts, kind):
        return self.engine.embed(texts, kind)

    def meaning_note(self, q):
        """Why a search used words only, in the language of the question. Empty when meaning search ran."""
        fa = answer_language(q) == "fa"
        if not self.settings.get("use_meaning", True):
            return ("جست‌وجوی معنایی در تنظیمات خاموش است؛ فقط واژه‌ها جست‌وجو شدند." if fa
                    else "Meaning search is off in Answer settings; only words were searched.")
        if not self.comp_state("embed")["ready"]:
            return ("مدل جست‌وجوی معنایی هنوز آماده نیست؛ فقط واژه‌ها جست‌وجو شدند." if fa
                    else "The meaning model is not ready yet; only words were searched.")
        if self.ix.have is None or not self.ix.have.any():
            return ("فهرست معنایی هنوز ساخته نشده؛ فقط واژه‌ها جست‌وجو شدند." if fa
                    else "The meaning index is not built yet; only words were searched.")
        return ""

    def meaning_ready(self):
        return bool(self.ix.mat is not None and self.ix.have is not None and self.ix.have.any()
                    and self.comp_state("embed")["ready"])

    def abort_generation(self):
        """The Stop button: the answer being written is stopped. The passages stay; no AI answer is saved."""
        self.gen_abort.set()
        log("gen.abort_requested")
        try:
            self.engine.stop("gen")               # ends the blocked stream read now, instead of after the next token
        except Exception as e:
            error("gen.abort", e)

    def gen_ready(self):
        return self.comp_state("gen")["ready"]

    def chunks_by_id(self, ids):
        out = {}
        ids = list(ids)
        for s in range(0, len(ids), 500):
            part = ids[s:s + 500]
            for (i, path, idx, text) in self.st.q("SELECT id, path, idx, text FROM chunks WHERE id IN (%s)" % ",".join("?" * len(part)), part):
                out[i] = (path, idx, text)
        return out

    def is_followup_question(self, q):
        """True when the question has no topic of its own ("continue"): it refers to the previous answer."""
        terms = query_terms(q)
        return bool(terms) and all(self.ix.doc_freq(t_) == 0 for t_ in terms)   # no word of the question is in the bank

    def rerank_ready(self):
        return self.comp_state("rerank")["ready"]

    def rerank_order(self, q, order, info):
        """Second stage of search. A cross-encoder reads the question together with each candidate passage and scores the pair,
        which separates a real match from a passage that only shares a few words. Returns the candidates best first, and the
        reranked flag (None when the reranker did not run, so the older order rules apply)."""
        if (not order or not self.settings.get("use_rerank", False) or getattr(self, "_rerank_failed", False)
                or not self.rerank_ready()):
            return order, None
        cand = order[:RERANK_TOP]                  # Stage 2: few candidates, short passages, to keep the answer fast on CPU
        t0 = time.time()
        try:
            scores = self.engine.rerank(q, [info[i][2][:600] for i in cand])
        except Exception as e:
            # stop for this session: a reranker that cannot start must not delay every question. Search still works without it.
            self._rerank_failed = True
            error("retrieve.rerank", e)
            return order, None
        pairs = sorted(zip(cand, scores), key=lambda x: -x[1])
        log("retrieve.rerank", candidates=len(cand), seconds=round(time.time() - t0, 3), gate=RERANK_MIN, top=[
            {"chunk": int(i), "file": os.path.basename(info[i][0]), "score": round(float(s), 4)} for i, s in pairs[:8]])
        if RERANK_MIN is not None:
            pairs = [(i, s) for i, s in pairs if s >= RERANK_MIN]
        return [i for i, _ in pairs], True

    def retrieve(self, q, k=12):
        all_terms = self.ix.content_terms(query_terms(q))
        if not all_terms:
            # Only stop words ("How are you?"): no search at all, so no passage is attached to a greeting.
            log("retrieve.skipped", reason="no_content_terms", chars=len(q or ""))
            return {"ids": [], "terms": [], "mode": "words", "qv": None, "info": {}, "note": ""}
        if self.is_followup_question(q):
            # Stage 1: a reply with no topic ("continue") has nothing to search for, so no unrelated passage is attached
            log("retrieve.skipped", reason="no_topic", chars=len(q or ""))
            return {"ids": [], "terms": [], "mode": "words", "qv": None, "info": {}, "note": ""}
        terms = all_terms
        ix = self.ix
        NT = max(30, int(k * 2.5))
        lim = NT * (40 if self.off else 3)
        raw_bm = ix.bm25_hits(terms, lim)
        log("retrieve.word_order", terms=terms, top=[{"chunk": int(i), "file": os.path.basename(ix.paths[ix.row_of[i]]),
            "score": round(float(s), 3)} for i, s in raw_bm[:8] if i in ix.row_of])
        bm = [(i, s) for (i, s) in raw_bm if i in ix.row_of and self.is_on(ix.paths[ix.row_of[i]])]
        excluded_files = sorted({os.path.basename(ix.paths[ix.row_of[i]]) for i, _ in raw_bm
                                 if i in ix.row_of and not self.is_on(ix.paths[ix.row_of[i]])})
        if raw_bm and not bm and excluded_files:
            log("retrieve.only_excluded", files=excluded_files, matches=len(raw_bm))
        wr = [i for i, _ in bm[:NT]]
        # some PDFs lose spaces ("جریانشناسی"), so also match the query inside longer strings
        if not wr:                       # rescue only when word search finds nothing, since these matches have no score
            seen = set(wr)
            for t_ in terms:
                if len(t_) < 3:
                    continue
                for (i,) in self.st.q("SELECT id FROM chunks WHERE text LIKE ? LIMIT ?", ("%" + t_ + "%", NT)):
                    if i in ix.row_of and i not in seen and self.is_on(ix.paths[ix.row_of[i]]):
                        seen.add(i)
                        wr.append(i)
        sr, qv = [], None
        mode = "words"
        note = ""
        log("retrieve.words", terms=terms, bm25_hits=len(bm), word_rescue=(not wr), kept_for_meaning=len(wr),
            top_scores=[round(s, 6) for _, s in bm[:5]], bank_chunks=ix.N, off_sources=len(self.off))
        if self.meaning_ready() and self.settings.get("use_meaning", True):
            try:
                np = self.np
                qv = self.embed_texts([q], "query")[0]
                # passages within MEANING_MARGIN of the best score, and at or above the absolute floor (Stage 1)
                sr = [ix.ids[row] for row, s_ in ix.vector_hits(np, qv, NT, self) if s_ >= MIN_MEANING_SIM]
                floor = ix.last_floor if ix.last_floor is not None else MIN_MEANING_SIM
                self.log_similarity(q, ix.last_top, len(sr), floor)
                log("retrieve.meaning", best=ix.last_top, cutoff=floor, passed=len(sr),
                    top_files=[os.path.basename(ix.paths[ix.row_of[i]]) for i in sr[:5] if i in ix.row_of])
                try:                                  # near misses: the best scores even when they fall below the cutoff
                    if ix.mat is not None and qv is not None and ix.mat.shape[1] == qv.shape[-1]:
                        allsims = np.where(ix.have, ix.mat @ qv, -1.0)
                        mask = ix.allowed_mask(np, self)          # the same on/off filter the real search uses
                        if mask is not None:
                            allsims = np.where(mask, allsims, -1.0)
                        best = np.argsort(-allsims)[:10]
                        log("retrieve.near_misses", cutoff=floor, passages_searchable=int((allsims >= -0.5).sum()), top10=[
                            {"file": os.path.basename(ix.paths[int(j)]), "chunk": int(ix.ids[int(j)]), "sim": round(float(allsims[j]), 4),
                             "kept": bool(allsims[j] >= floor)} for j in best])
                except Exception as e:
                    error("retrieve.near_misses", e)
                mode = "meaning"
            except Exception as e:
                error("retrieve.meaning", e)
                self.prog["meaning"]["err"] = "Search engine: %s" % e
                note = ("جست‌وجوی معنایی انجام نشد (%s) — از جست‌وجوی واژه‌ها استفاده شد" % str(e)[:140] if self.ui_lang() == "fa"
                        else "meaning search failed (%s) — used word search" % str(e)[:140])
                qv, sr = None, []
        if mode == "words" and not note:
            note = self.meaning_note(q)
        fused = {}
        for r, w in ((wr, 2.0), (sr, 1.2)):
            for n, i in enumerate(r):
                fused[i] = fused.get(i, 0) + w / (60 + n)
        order = [i for i, _ in sorted(fused.items(), key=lambda x: -x[1])][:max(18, k * 2)]
        info = self.chunks_by_id(order)
        order = [i for i in order if i in info]
        order, reranked = self.rerank_order(q, order, info)
        per, out = {}, []

        def take(i):
            p = info[i][0]
            if per.get(p, 0) >= 4 or i in out or i not in info:
                return False
            per[p] = per.get(p, 0) + 1
            out.append(i)
            return True
        # keep the strongest word matches (exact terms such as a name) and the best meaning matches
        word_top = [i for i in wr if i in info][:2] if mode == "meaning" and not reranked else []
        meaning_top = [i for i in sr if i in info][:3] if mode == "meaning" and not reranked else []
        for i in word_top + meaning_top:
            take(i)
        for i in order:
            if len(out) >= max(k, 6):
                break
            take(i)
        per_file = {}
        for i in out:
            n_ = os.path.basename(info[i][0])
            per_file[n_] = per_file.get(n_, 0) + 1
        if not out and excluded_files:
            note = ("Matches were found only in sources that are unticked in the sidebar: %s. Tick them to search them."
                    % ", ".join(excluded_files)) if self.ui_lang() == "en" else \
                   ("بند مرتبط فقط در منابعی بود که در کناره انتخاب نشده‌اند: %s. برای جست‌وجو تیک بزنید."
                    % "، ".join(excluded_files))
        log("retrieve.done", mode=mode, fused=len(fused), final=len(out), per_file=per_file, reranked=bool(reranked),
            rerank_failed=bool(getattr(self, "_rerank_failed", False)))
        return {"ids": out, "terms": terms, "mode": mode, "qv": qv, "info": info, "note": note}

    def hit_json(self, i, info):
        path, idx, text = info[i]
        return {"id": i, "path": path, "name": os.path.basename(path), "idx": idx, "text": text}

    def ask(self, q):
        self.question_busy.set()               # background indexing yields to the answer while this is set
        try:
            return self._ask(q)
        finally:
            self.question_busy.clear()

    def _ask(self, q):
        set_qid(qhash(q))
        log("question", question=q, sources_state=[{"name": os.path.basename(s.get("path", "")), "kind": s.get("kind"),
            "on": self.is_on(posix(s.get("path", "")))} for s in self.sources])
        log("settings.at_question", grounded=self.settings.get("grounded"), use_meaning=self.settings.get("use_meaning"),
            results=self.settings.get("results"), ai=self.settings.get("ai"), answer_length=self.answer_length(),
            resources=self.settings.get("resources"))
        if not self.grounded_mode():
            # 'Based on sources' is off: the documents are not searched, so no passage is sent or shown
            log("ask.free", reason="based_on_sources_off", question_chars=len(q or ""))
            note = ("پاسخ از دانش عمومی مدل است؛ جست‌وجوی اسناد خاموش است." if self.ui_lang() == "fa"
                    else "Answered from general knowledge: document search is off.")
            return {"mode": "words", "terms": [], "note": note, "bullets": [], "sources": [], "hits": [], "context": []}
        r = self.retrieve(q, self.result_count())
        ids, terms, info = r["ids"], r["terms"], r["info"]
        log("ask", question=q, terms=terms, mode=r["mode"], note=r["note"], returned=len(ids),
            files=[os.path.basename(info[i][0]) for i in ids])
        base = {"mode": r["mode"], "terms": terms, "note": r["note"]}
        if not ids:
            return dict(base, bullets=[], sources=[], hits=[], context=[])
        tset = set(terms)
        cands = []
        for rank, i in enumerate(ids):
            path, idx, text = info[i]
            ss = sentences(text) or [re.sub(r"\s+", " ", text)[:260]]
            for si, s in enumerate(ss):
                tk = set(tokens(s))
                lex = sum(self.ix.idf(t) for t in tk if t in tset) / math.sqrt(len(tk) + 4)
                cands.append({"text": s, "path": path, "ci": i, "idx": idx, "si": si, "lex": lex + (0.05 if si == 0 else 0) - rank * 0.01,
                              "rank": rank, "tk": tk})
        # an extracted sentence must share a word with the question, or it does not answer it
        cands = [c for c in cands if c["lex"] > 0]
        cands.sort(key=lambda c: (-c["lex"], c["rank"]))
        cands = cands[:40]
        mx = max((c["lex"] for c in cands), default=0) or 1
        for c in cands:
            c["score"] = max(0.0, c["lex"] / mx)
        if r["qv"] is not None and cands and self.settings.get("precise_bullets", False):
            try:
                sv = self.embed_texts([c["text"] for c in cands], "passage")
                sims = sv @ r["qv"]
                mu, sd = float(sims.mean()), float(sims.std())
                lo, hi = float(sims.min()), float(sims.max())
                span = (hi - lo) or 1.0
                for c, s in zip(cands, sims):
                    c["sem"] = float(s)
                    c["score"] = 0.75 * (float(s) - lo) / span + 0.25 * c["score"]
                # keep a sentence if it shares a word with the question or clearly stands out from the rest
                cands = [c for c in cands if c["lex"] > 0 or (sd > 0 and c["sem"] >= mu + 1.5 * sd)]
                cands = sorted(cands, key=lambda c: -c["sem"])[:12]
            except Exception as e:
                base["note"] = (base["note"] + " · " if base["note"] else "") + "sentence ranking failed (%s)" % str(e)[:100]
        picked, per = [], {}
        for c in sorted(cands, key=lambda c: -c["score"]):
            if len(picked) >= 6:
                break
            if per.get(c["path"], 0) >= 3:
                continue
            red = max((len(c["tk"] & p["tk"]) / max(1, min(len(c["tk"]), len(p["tk"]))) for p in picked), default=0)
            if red > 0.7:
                continue
            picked.append(c)
            per[c["path"]] = per.get(c["path"], 0) + 1
        # the numbers follow the ranking: [1] is the strongest source
        order = {}
        for i in ids:
            order.setdefault(info[i][0], len(order) + 1)
        lead = picked[0] if picked else None
        rest = sorted(picked[1:], key=lambda c: (order[c["path"]], c["idx"], c["si"]))
        final = ([lead] if lead else []) + rest
        bullets = [{"text": c["text"], "n": order[c["path"]], "ci": c["ci"], "lead": c is lead,
                    "path": c["path"], "idx": c["idx"]} for c in final]
        # each source opens on its best-ranked passage
        first_idx = {}
        for c in sorted(picked, key=lambda c: -c["score"]):
            first_idx.setdefault(c["path"], c["idx"])
        sources = [{"n": n, "path": p, "name": os.path.basename(p), "idx": first_idx.get(p, 0)}
                   for p, n in sorted(order.items(), key=lambda x: x[1])]
        context = []
        for pos, i in enumerate(ids[:self.context_count(ids, info)], 1):              # one number per passage, so [2] is the second passage the model sees
            path, idx, text = info[i]
            context.append({"n": pos, "name": os.path.basename(path), "path": path, "idx": idx, "ci": int(i),
                            "text": re.sub(r"\s+", " ", text)[:450]})
        return dict(base, bullets=bullets, sources=sources, hits=[self.hit_json(i, info) for i in ids], context=context)

    def context_count(self, ids, info):
        """How many ranked passages go to the model: as many as fit PASSAGE_CHAR_BUDGET, and never more than were retrieved.
        The first passage is always sent."""
        used, n = 0, 0
        for i in ids:
            size = min(len(re.sub(r"\s+", " ", info[i][2])), PASSAGE_CHARS)
            if n and (used + size > PASSAGE_CHAR_BUDGET or n >= MAX_PASSAGES):
                break
            used += size
            n += 1
        log("context.count", retrieved=len(ids), sent=n, chars=used, budget=PASSAGE_CHAR_BUDGET)
        return n

    def match_percent(self, score):
        """The percentage shown beside a citation, or None if the user has switched it off."""
        if not self.settings.get("show_match", True):
            return None
        return int(round((score or 0) * 100))

    def result_count(self):
        v = self.settings.get("results", "standard")
        return RESULT_COUNTS.get(v, RESULT_COUNTS["standard"])

    def answer_length(self):
        v = self.settings.get("answer_length", "normal")
        return v if v in ANSWER_LENGTHS else "normal"

    LANG_NAMES = {"fa": "Persian (فارسی)", "en": "English"}

    def log_similarity(self, q, top, kept, floor=MIN_MEANING_SIM):
        """Records the best meaning score for each question, so the cutoff can be set from real use."""
        try:
            os.makedirs(os.path.join(DATA, "logs"), exist_ok=True)
            with open(os.path.join(DATA, "logs", "similarity.txt"), "a", encoding="utf-8") as f:
                f.write("%s\t%s\t%s\tkept=%d\t%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                        "-" if top is None else "%.4f" % top, floor, kept, q.replace("\n", " ")[:200]))
        except OSError:
            pass

    def prompt_limits(self):
        """Context and output sizes of the answer model, so the whole prompt fits in the context."""
        return {"ctx_tokens": self.model_entry("gen").get("ctx", 4096),
                "max_tokens": ANSWER_LENGTHS[self.answer_length()][0]}

    def no_source_prompt(self, q, lang, history=None):
        """No passage matched: the model gets the question and the chat history."""
        return build_messages(SYS_PLAIN, history or [], None, q, **self.prompt_limits())

    def grounded_mode(self):
        """'Based on sources' (on by default). Off: the model may answer from its own knowledge."""
        return bool(self.settings.get("grounded", True))

    def free_prompt(self, q, context, lang, history=None):
        """Based on sources is off: the excerpts are offered, not required."""
        if context:
            blocks = ["[%d] (file: %s)\n%s" % (c_["n"], c_["name"], c_["text"]) for c_ in context]
            return build_messages(SYS_EXCERPTS, history or [], "\n\n".join(blocks), q, **self.prompt_limits())
        return build_messages(SYS_PLAIN, history or [], None, q, **self.prompt_limits())

    def answer_prompt(self, q, context, lang, history=None):
        """Messages for the model: a one-line instruction, the excerpts when there are any, and the question."""
        if not self.grounded_mode():
            return self.free_prompt(q, context, lang, history)
        if not context:
            return self.no_source_prompt(q, lang, history)
        blocks = ["[%d] (file: %s)\n%s" % (c_["n"], c_["name"], c_["text"]) for c_ in context]
        return build_messages(SYS_EXCERPTS, history or [], "\n\n".join(blocks), q, **self.prompt_limits())

    def engine_busy(self):
        return self.engine.busy()

    def chat_once(self, msgs, max_tokens, on_delta):
        """One model call. An engine failure is not shown to the user: it returns an empty reply, and the answer falls back to the passages."""
        try:
            t0 = time.time()
            out = self.engine.chat(msgs, max_tokens, on_delta)
            if not (out or "").strip() and self.gen_abort.is_set():
                return ""                                   # Stop was pressed: an empty reply is expected, do not restart the model
            if not (out or "").strip():                     # an empty reply: restart the answer model once and ask again
                log("chat.empty_retry")
                self.engine.stop("gen")
                out = self.engine.chat(msgs, max_tokens, on_delta)
            log("chat.ok", seconds=round(time.time() - t0, 2), messages=len(msgs), chars=len(out or ""))
            return out
        except (RuntimeError, OSError) as e:
            error("chat", e)
            try:
                os.makedirs(os.path.join(DATA, "logs"), exist_ok=True)
                with open(os.path.join(DATA, "logs", "engine_errors.txt"), "a", encoding="utf-8") as f:
                    f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), e))
            except OSError:
                pass
            return ""

    def light_clean(self, raw):
        """Formatting only. Used when the strict cleaning removes a reply that is still usable."""
        t = re.sub(r"\*\*|__|`", "", raw or "").strip()
        return " ".join(l.strip() for l in t.splitlines() if l.strip())

    def extractive_answer(self, q, context, lang):
        """When the model gives no usable reply: the opening sentences of the passage that best matches the question."""
        if not context:
            return ("پاسخی ساخته نشد. دوباره بپرسید." if lang == "fa"
                    else "The model did not produce an answer. Please ask again.")
        qt = set(tokens(q))
        best = max(context, key=lambda c: len(qt & set(tokens(c["text"]))))
        body = " ".join(sentences_plain(best["text"])[:2]) or best["text"][:300]
        return body[:400]

    NO_ANSWER_TEXT = {
        "fa": "در اسناد شما پاسخ این پرسش نیامده است. برای پاسخ از دانش عمومی مدل، «بر اساس منابع» را خاموش کنید؛ "
              "آن پاسخ به‌عنوان «از اسناد شما نیست» علامت می‌خورد. پاسخ‌های دانش عمومی بررسی نشده‌اند و ممکن است نادرست باشند.",
        "en": "The excerpts do not contain the answer to this question. To get an answer from the model's general knowledge, "
              "turn off \"Based on sources\"; that answer is labelled as not from your documents. General answers are not "
              "checked against any source and may be wrong.",
    }

    def ui_lang(self):
        """The language of the window, used for messages the app writes itself."""
        return "fa" if self.settings.get("lang", "en") == "fa" else "en"

    def coverage(self, q, context):
        """Share of the question's words that the passages contain, each word weighted by how rare it is in the bank.
        A word that no passage contains counts as a full miss, so a missing name or acronym lowers coverage on its own.
        Common words weigh little, so they cannot carry an answer."""
        present = set()
        for c in context:
            present |= set(tokens(c["text"]))
        total = got = 0.0
        # every word of the question counts, including words the bank does not contain: those are full misses
        # (their idf is the highest), so a question about something the documents never mention scores low.
        terms = query_terms(q)
        for t in terms:
            w = self.ix.idf(t)
            total += w
            if t in present:
                got += w
        cov = got / total if total else 0.0
        log("coverage", terms=terms, coverage=round(cov, 3), threshold=COVERAGE_MIN, passages=len(context))
        return cov

    def answerable(self, q, context):
        """True when the passages cover enough of the question (see coverage)."""
        return self.coverage(q, context) >= COVERAGE_MIN

    def gen_stream(self, q, context, on_delta, history=None):
        """Writes the answer. It always returns text: the model's answer when it gives one, otherwise the most relevant passage text (fallback=True).
        Empty replies are retried once."""
        lang = answer_language(q)
        set_qid(qhash(q))
        self.gen_abort.clear()                 # a new answer: a Stop from an earlier one does not apply
        if self.grounded_mode() and not context:
            # Stage 3: no passage cleared the relevance floor, so the answer is refused, not written from general knowledge
            log("answer.refused", reason="no_passage", question=q)
            text = ("هیچ بندی از اسناد شما به این سؤال مربوط نبود." if lang == "fa"
                    else "No passage in your documents matches this question.")
            return {"text": text, "grounded": True, "lang_ok": True, "spans": [], "fallback": False,
                    "no_answer": True, "verified": False}
        if history and not self.grounded_mode():
            # no excerpts in this answer: earlier [n] numbers would point at passages the model never saw
            history = [dict(m, content=re.sub(r"\s*\[\d+\]", "", m.get("content") or ""))
                       if isinstance(m, dict) and "content" in m else m for m in history]
        if self.grounded_mode() and context:
            # Coverage is logged for calibration only. It never stops the answer: the model is asked whenever a passage exists.
            self.coverage(q, context)
        msgs = self.answer_prompt(q, context, lang, history)
        max_tokens = ANSWER_LENGTHS[self.answer_length()][0]
        log("gen.start", question=q, lang=lang, grounded=self.grounded_mode(), passages=len(context), history_msgs=len(msgs) - 2, max_tokens=max_tokens,
            prompt_chars=sum(len(m["content"]) for m in msgs),
            passages_sent=[{"n": c_.get("n"), "file": os.path.basename(c_.get("path", c_.get("name", ""))), "chunk": c_.get("idx"), "db_id": c_.get("ci"),
                            "text": (c_.get("text") or "")[:80]} for c_ in context])
        raw = self.chat_once(msgs, max_tokens, on_delta)
        if self.gen_abort.is_set():
            log("gen.aborted", chars=len(raw or ""))
            # Stop keeps the text written so far. It is not checked, so it is shown without citations and marked as partial.
            partial = self.light_clean(raw) if (raw or "").strip() else ""
            return {"text": partial, "grounded": False, "lang_ok": True, "spans": [], "verified": False,
                    "fallback": False, "no_answer": False, "aborted": True}
        text = self.clean_answer(raw, q, None) or self.light_clean(raw)
        log("gen.raw", raw_chars=len(raw or ""), cleaned_chars=len(text or ""), raw=raw)
        if not text:                       # an empty reply is often a one-off, so ask once more
            raw = self.chat_once(msgs, max_tokens, None)
            text = self.clean_answer(raw, q, None) or self.light_clean(raw)
        fallback = False
        if not text:
            text = self.extractive_answer(q, context, lang)
            fallback = True
        log("gen.done", fallback=fallback, lang=lang, lang_ok=answer_language(text) == lang, chars=len(text or ""))
        lang_ok = answer_language(text) == lang
        try:                               # keep the last exchange, so problems can be checked
            os.makedirs(os.path.join(DATA, "logs"), exist_ok=True)
            with open(os.path.join(DATA, "logs", "last_answer.txt"), "w", encoding="utf-8") as f:
                f.write("QUESTION:\n%s\n\nPROMPT:\n%s\n\nRAW OUTPUT:\n%r\n\nCLEANED:\n%r\nFALLBACK: %s\n" % (
                    q, "\n---\n".join(m["content"] for m in msgs), raw, text, fallback))
        except OSError:
            pass
        ctx_texts = [c_["text"] for c_ in context]
        grounded = self.grounded_mode()
        # In free mode the model may write from its own knowledge, so the passages are not linked to its sentences.
        no_answer = False                  # set by the grounding check, when no passage supports the reply
        if no_answer:
            text = re.sub(r"\s*\[\d+\]", "", text).strip()    # no citations on a reply that found no answer
            log("cite.skipped", reason="no_answer_reply")
        if not grounded:
            # Keep only citation numbers for excerpts that were actually sent; any other number is invented.
            valid = {c_["n"] for c_ in context}
            text = re.sub(r"\s*\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in valid else "", text).strip()
            log("cite.skipped", reason="free_answer")
        spans = self.link_sentences(text, context) if context and grounded and not no_answer else []
        if spans and not fallback:
            # The numbers come from the passages the sentences were matched to, not from the model, so an invented
            # citation cannot appear, and copies and exports carry the same numbers as the window.
            unlinked = [sp["sent"] for sp in spans if not sp.get("path")]
            if unlinked:
                # A sentence no passage supports stays in the answer, without a citation, and the answer is marked as
                # only partly checked. The answer is not replaced and the model is not called again: the user gets the
                # answer, and the check shows which sentences are unsupported.
                log("grounding.partial", unsupported=len(unlinked), of=len(spans), sentences=[b[:120] for b in unlinked])
            text = " ".join(cite_sentence(sp["sent"], sp.get("ns") or []) for sp in spans)
        # Stage 4: an answer is grounded only if every sentence found a passage above the floor
        n_sents = len([x for x in sentences_plain(text) if set(tokens(x))]) if text else 0
        unsupported = bool(context) and grounded and not no_answer and bool(text) and len(spans) < n_sents
        return {"text": text, "grounded": self.is_grounded(text, ctx_texts) and not unsupported, "lang_ok": lang_ok,
                "spans": spans, "fallback": fallback, "no_answer": no_answer,
                "verified": bool(spans) and not fallback and not no_answer and all(sp.get("path") for sp in spans)}

    @staticmethod
    def move_markers(text):
        """The model writes '<fact>. [2]' but the citation belongs to the fact: this turns it into '<fact> [2].',
        so sentence splitting keeps each citation with its own sentence."""
        return re.sub(r"([.!?؟۔])\s*((?:\[\d+\]\s*)+)", lambda m: " " + m.group(2).strip() + m.group(1) + " ", text or "")

    @staticmethod
    def numbers_supported(sentence, passage):
        """Every number in the sentence must also appear in the passage (Persian and Arabic digits are normalised first)."""
        nums = re.findall(r"\d+", text_norm(sentence or ""))
        if not nums:
            return True
        ptxt = text_norm(passage or "")
        return all(n in ptxt for n in nums)

    def link_sentences(self, text, context, min_score=0.4):
        """Ties each sentence of an answer to the passage that supports it.

        Each sentence and each passage is scored by meaning (cosine similarity from the meaning model), with a small bonus
        for words shared with the passage. Meaning is what links a paraphrase, or a sentence in another language, to its passage. The model's own [k] is kept only when that passage is about as good as the best one;
        a number that is not a passage here is never kept. A sentence with no passage above min_score is left unlinked."""
        sents = [x for x in sentences_plain(self.move_markers(text)) if set(tokens(x))]
        if not sents or not context:
            return []
        sem = None
        if self.meaning_ready():
            try:
                sv = self.embed_texts(sents, "passage")
                pv = self.embed_texts([cx["text"] for cx in context], "passage")
                sem = sv @ pv.T                        # rows: sentences, columns: passages
            except Exception as e:
                error("cite.semantic", e)
        out = []
        for si, sent in enumerate(sents):
            st = set(tokens(sent))
            scores = []
            for ci, cx in enumerate(context):
                lex = len(st & set(tokens(cx["text"]))) / len(st)
                if sem is not None:
                    sim = max(0.0, min(1.0, float(sem[si][ci])))
                    score = sim + LEX_BONUS * lex           # meaning first; shared words add a little
                else:
                    sim = lex
                    score = lex
                scores.append((score, lex, sim, ci))
            best_score, best_lex, best_sim, best_ci = max(scores, key=lambda x: x[0])
            model_ns = [int(x) for x in re.findall(r"\[(\d+)\]", sent)]
            model_n = model_ns[0] if model_ns else None
            # Every number the model wrote is checked: it must name a real passage that scores nearly as well as the best one.
            kept = []
            for n_ in model_ns:
                mi = next((ci for ci, cx in enumerate(context) if cx["n"] == n_), None)
                if mi is not None and scores[mi][0] >= best_score - 0.1 and mi not in kept:
                    kept.append(mi)
            kept.sort(key=lambda ci: -scores[ci][0])
            pick = kept[0] if kept else best_ci
            chosen = scores[pick]
            # A sentence the model did not cite must be supported more strongly before it is linked to a passage.
            needed = LINK_SEM_MIN if sem is not None else min_score   # the same bar for model and uncited citations
            linked = chosen[0] >= needed
            picks = kept if kept else [best_ci]
            clean = re.sub(r"\s*\[\d+\]", "", sent).strip()
            if linked and not self.numbers_supported(clean, context[pick]["text"]):
                linked = False            # the sentence gives a number (a year, a figure) that the passage does not contain
            log("cite.link", sentence=clean[:120], model_n=model_n, model_ns=model_ns, chosen_n=context[pick]["n"] if linked else None,
                best_n=context[best_ci]["n"], score=round(chosen[0], 3), lexical=round(chosen[1], 3),
                semantic=round(chosen[2], 3), linked=linked)
            out.append({"sent": clean,
                        "path": context[pick]["path"] if linked else None,
                        "idx": context[pick]["idx"] if linked else None,
                        "n": context[pick]["n"] if linked else None,
                        "ns": [context[ci]["n"] for ci in picks] if linked else [],
                        "score": round(chosen[0], 2)})
        return out

    def is_grounded(self, text, context_texts):
        """True if most words in the answer also appear in the passages."""
        if not text:
            return False
        body_tokens = set(tokens(" ".join(context_texts)))
        ct = [w for w in tokens(re.sub(r"\[\d+\]", " ", text)) if len(w) > 1]
        return bool(ct) and sum(1 for w in ct if w in body_tokens) / len(ct) >= 0.5

    def clean_answer(self, text, q, context_texts=None):
        """Cleans up the model's answer:
        1. strips markdown markers and excerpt headers copied from the prompt;
        2. drops answers that restate the question;
        3. drops answers whose words do not appear in the passages (the small model invents them)."""
        t = (text or "").strip()
        t = re.sub(r"\*\*|__|`", "", t)
        keep = []
        for l in t.splitlines():
            # the model copied the prompt back: an excerpt header such as "[1] (file: IR.pdf)" or a line "Excerpts:".
            # A sentence that merely mentions excerpts is kept.
            if re.match(r"^\s*\[\d+\]\s*\(file", l, re.I):
                continue
            if l.strip():
                keep.append(l.strip())
        t = " ".join(keep).strip()
        qt = set(tokens(q))
        kept_s = []
        for s in sentences_plain(t):
            st = set(tokens(s))
            echo = s.rstrip().endswith(("?", "؟")) and bool(st) and len(st & qt) / len(st) >= 0.8
            if not echo:
                kept_s.append(s)
        t = " ".join(kept_s).strip()
        return self.limit_sentences(t)

    def limit_sentences(self, t):
        """No sentence cap: the answer is kept as the model wrote it. Length is set only by the token limit (ANSWER_LENGTHS)."""
        return t

    def doc(self, path):
        row = self.st.q("SELECT th, status, note FROM files WHERE path=?", (path,))
        if not row:
            raise ValueError("unknown file")
        chunks = [r[0] for r in self.st.q("SELECT text FROM chunks WHERE path=? ORDER BY idx", (path,))]
        return {"path": path, "name": os.path.basename(path), "chunks": chunks, "status": row[0][1], "note": row[0][2]}

    # --- meaning index
    def start_meaning(self):
        P = self.prog["meaning"]
        if P["busy"] or not self.comp_state("embed")["ready"]:
            return False
        P.update(busy=True, paused=False, err="", eta=None)
        self.stop_meaning = False
        threading.Thread(target=self._meaning_run, daemon=True).start()
        return True

    def _meaning_run(self):
        P = self.prog["meaning"]
        try:
            np = self.try_numpy()
            todo = self.st.q("SELECT DISTINCT h, text FROM chunks WHERE h NOT IN (SELECT h FROM vecs)")
            P["total"], P["done"] = len(todo), 0
            todo.sort(key=lambda x: len(x[1]))
            B = batch_for(self.settings.get("resources", "balanced"))
            total_chars = sum(len(t) for _, t in todo) or 1
            done_chars = 0
            samples = []                                  # (characters, seconds) for recent batches
            for s in range(0, len(todo), B):
                while P["paused"] and not self.stop_meaning:
                    time.sleep(.4)
                if self.stop_meaning:
                    break
                batch = todo[s:s + B]
                batch_chars = sum(len(t) for _, t in batch)
                t_batch = time.time()
                v = self.embed_texts([t for _, t in batch], "passage")
                if s > 0:                                 # the first batch includes starting the model, so it is not a speed sample
                    rest = pause_for(self.settings.get("resources", "balanced"))
                    samples = (samples + [(batch_chars, time.time() - t_batch + rest)])[-10:]   # includes the rest, so the estimate holds on Light
                done_chars += batch_chars
                with self.st.lock:
                    self.st.db.executemany("INSERT OR REPLACE INTO vecs VALUES(?,?)",
                                           [(h, v[j].astype(np.float16).tobytes()) for j, (h, _) in enumerate(batch)])
                    self.st.db.commit()
                P["done"] = min(len(todo), s + B)
                spent = sum(d for _, d in samples)
                if samples and spent > 0:
                    rate = sum(c_ for c_, _ in samples) / spent     # speed in characters per second, from recent batches
                    P["eta"] = (total_chars - done_chars) / rate
                time.sleep(pause_for(self.settings.get("resources", "balanced")))
            self.reload_index()
            self.dirty += 1
        except Exception as e:
            P["err"] = "%s: %s" % (type(e).__name__, e)
            traceback.print_exc()
        finally:
            P["busy"] = False

    # --- Python packages (pip fallback)
    def start_pip(self, pkgs):
        P = self.prog["pip"]
        if P["busy"]:
            return False
        P.update(busy=True, msg=", ".join(pkgs), err="", done=0, total=0, log="")
        threading.Thread(target=self._pip_run, args=(pkgs,), daemon=True).start()
        return True

    def _pip_run(self, pkgs):
        P = self.prog["pip"]
        try:
            base = [sys.executable, "-m", "pip", "install", "--user", "--disable-pip-version-check",
                    "--retries", "2", "--timeout", "20"] + PIP_EXTRA      # give up quickly when the network is blocked
            px = (self.settings.get("proxy") or "").strip()
            if px:
                base += ["--proxy", px]
            for k, v in system_proxies().items():         # pip reads these settings
                if k in ("http", "https") and not os.environ.get(k.upper() + "_PROXY"):
                    os.environ[k.upper() + "_PROXY"] = v
            variants = [["--progress-bar", "raw"], []]
            attempts = [["--break-system-packages"]] if externally_managed() else [[], ["--break-system-packages"]]
            ok, out = False, ""
            for extra in attempts:
                for prog_args in variants:
                    out = self._pip_once(base + prog_args + extra + pkgs, P)
                    if P.get("rc") == 0:
                        ok = True
                        break
                    if "invalid choice" in out and prog_args:
                        continue
                    break
                if ok or "externally-managed" not in out:
                    break
            if not ok:
                if re.search(r"name resolution|NewConnectionError|Connection(Error| refused| reset)|timed out|No matching distribution|Could not find a version", out):
                    P["err"] = T_NET   # a readable network error
                else:
                    P["err"] = out.strip().splitlines()[-1][:160] if out.strip() else "pip failed"
            try:
                import site
                sp = site.getusersitepackages()
                if sp not in sys.path:
                    sys.path.append(sp)
            except Exception:
                pass
            importlib.invalidate_caches()
            MOD_CACHE.clear()
            self.np = None
            self.reload_index()
            self.on_files_changed()
        except Exception as e:
            P["err"] = str(e)
        finally:
            P["busy"] = False

    def _pip_once(self, cmd, P):
        P["rc"] = None
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", **NOWIN)
        lines = []
        for line in p.stdout:
            line = line.strip()
            if not line:
                continue
            lines.append(line)
            m = re.match(r"Progress (\d+) of (\d+)", line)
            if m:
                P["done"], P["total"] = int(m.group(1)), int(m.group(2))
            elif not re.search(r"WARNING|Retrying|NewConnectionError|Traceback", line):
                P["log"] = line[:90]          # keep the status text short
        p.wait()
        P["rc"] = p.returncode
        return "\n".join(lines[-40:])

    # --- diagnostics
    def diagnose(self, hosts=None):
        import socket
        out = []
        for h in (hosts or ["huggingface.co", "hf-mirror.com", "github.com", "api.github.com", "pypi.org", "files.pythonhosted.org"]):
            t0 = time.time()
            res = {"host": h, "dns": "", "http": "", "ok": False, "ms": 0}
            try:
                socket.setdefaulttimeout(8)
                socket.getaddrinfo(h, 443)
                res["dns"] = "ok"
            except Exception as e:
                res["dns"] = why(e)
            try:
                req = urllib.request.Request("https://%s/" % h, method="HEAD", headers={"User-Agent": "KnowledgeBank/4"})
                with self.opener().open(req, timeout=8) as r:
                    res["http"] = "HTTP %s" % r.getcode()
                    res["ok"] = True
            except urllib.error.HTTPError as e:
                res["http"] = "HTTP %s" % e.code
                res["ok"] = e.code < 500
            except Exception as e:
                res["http"] = why(e)
            res["ms"] = int((time.time() - t0) * 1000)
            out.append(res)
        return out

    # --- status (computed off the UI thread; the window only reads self.snap)
    def update_snapshot(self):
        cnt = {k: v for k, v in self.st.q("SELECT status, COUNT(*) FROM files GROUP BY status")}
        nvec = int(self.ix.have.sum()) if self.ix.have is not None else 0
        self.snap = {
            "version": VERSION, "sources": list(self.sources), "settings": self.settings,
            "stats": {"files": cnt.get("ok", 0), "empty": cnt.get("empty", 0), "chunks": self.ix.N, "vec": nvec, "dim": self.ix.dim},
            "embed": self.comp_state("embed"), "gen": self.comp_state("gen"), "rerank": self.comp_state("rerank"),
            "engine": self.engine.binary(), "prog": self.prog,
            "meaning": {"ready": self.meaning_ready(), "complete": self.ix.N > 0 and nvec >= self.ix.N},
            "py": sys.version.split()[0], "downloads": self.dm.snapshot(),
        }
        return self.snap

    def state(self):
        return self.snap or self.update_snapshot()
