"""Downloads, proxies, and wheel selection."""
import os
import sys
import re
import time
import threading
import subprocess
import shutil
import urllib.request, urllib.error, urllib.parse
from kb_store import *

LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never send localhost traffic through a proxy


def wheel_platform_tags():
    import platform
    arm = platform.machine().lower() in ("arm64", "aarch64")
    if sys.platform.startswith("win"):
        return ["win_amd64"] if not arm else ["win_arm64"]
    if sys.platform == "darwin":
        return ["macosx_11_0_arm64", "macosx_12_0_arm64", "macosx_13_0_arm64", "macosx_14_0_arm64"] if arm else \
               ["macosx_10_9_x86_64", "macosx_11_0_x86_64", "macosx_12_0_x86_64"]
    return ["manylinux_2_28_aarch64", "manylinux2014_aarch64", "manylinux_2_17_aarch64"] if arm else \
           ["manylinux_2_34_x86_64", "manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64"]


def pick_wheel(files, py_major_minor, plats):
    """Best wheel for this Python and platform: an exact CPython match first, then abi3, then pure Python."""
    cp = "cp%s%s" % py_major_minor
    best = None
    for f in files:
        name = f.get("filename", "")
        if f.get("packagetype") != "bdist_wheel" or not name.endswith(".whl"):
            continue
        parts = name[:-4].split("-")
        if len(parts) < 5:
            continue
        pytag, abitag, plat = parts[-3], parts[-2], parts[-1]
        if plat == "any" and pytag.startswith("py"):
            rank = 2
        elif pytag == cp and any(p in plat for p in plats):
            rank = 0
        elif pytag.startswith("cp") and abitag == "abi3" and any(p in plat for p in plats) \
                and pytag[2:].isdigit() and int(pytag[2:]) <= int(cp[2:]):
            rank = 1
        else:
            continue
        if best is None or rank < best[0]:
            best = (rank, f)
    return best[1] if best else None


def system_proxies():
    """The system proxy. Environment variables come first (what pip and most tools use), then the GNOME settings on Linux.
    Windows and macOS are read by urllib itself."""
    found = dict(urllib.request.getproxies())
    if not found and sys.platform.startswith("linux"):
        try:
            def gs(schema, key):
                r = subprocess.run(["gsettings", "get", schema, key], capture_output=True, text=True, timeout=2)
                return (r.stdout or "").strip().strip("'\"")
            if gs("org.gnome.system.proxy", "mode") == "manual":
                for proto in ("http", "https"):
                    host = gs("org.gnome.system.proxy." + proto, "host")
                    port = gs("org.gnome.system.proxy." + proto, "port")
                    if host:
                        found[proto] = "http://%s:%s" % (host, port)
        except Exception:
            pass
    return found


def why(e):
    """A short, readable reason for a network failure."""
    import socket as _s
    import ssl as _ssl
    if isinstance(e, urllib.error.HTTPError):
        return "HTTP %s" % e.code + (" (blocked or not found)" if e.code in (401, 403, 404, 451) else "")
    r = getattr(e, "reason", e)
    if isinstance(r, _s.gaierror):
        return "DNS lookup failed (the name cannot be resolved)"
    if isinstance(r, (_s.timeout, TimeoutError)) or "timed out" in str(r).lower():
        return "timed out"
    if isinstance(r, ConnectionRefusedError):
        return "connection refused"
    if isinstance(r, ConnectionResetError):
        return "connection reset (often a filter or firewall)"
    if isinstance(r, _ssl.SSLError):
        return "TLS/SSL error"
    return (str(r) or type(e).__name__)[:120]


class Stop(Exception):
    pass


STALL_SECONDS = 60          # an attempt with no progress for this long is failed and retried
WEDGED_SECONDS = 180        # an item that has reported nothing for this long is marked failed, so Retry appears
PROGRESS_STEP = 1 << 16     # 64 KB of new data counts as progress


class DownloadManager:
    """Downloads that can be paused, resumed, and cancelled. Each file can have several sources, a proxy, a custom link, or a manual import.
    Items come from App.assets().

    Each download runs in its own worker thread. Every start gets a new generation number: a worker whose generation is no
    longer current does nothing more, so a worker that is stuck cannot block the next download or change its state.
    Watchdogs: an attempt with no progress for STALL_SECONDS is failed and retried; an item that has reported nothing for
    WEDGED_SECONDS is marked failed, so the window shows Retry."""

    def __init__(self, core):
        self.core = core
        self.items = {}
        self.lock = threading.RLock()

    # ---- public methods used by the window and the core

    def start(self, keys=None, force=False):
        with self.lock:
            for a in self.core.assets():
                if keys is not None and a["key"] not in keys:
                    continue
                it = self.items.get(a["key"])
                if self.core.asset_ok(a) and not (force and a["kind"] == "engine"):
                    if it:
                        it.update(state="done", done=it["total"])
                    continue
                if it and it["state"] in ("running", "queued"):
                    continue
                self.items[a["key"]] = self._new_item(a)
            self._pump()

    def start_role(self, role):
        self.start([a["key"] for a in self.core.assets() if a["role"] in (role, "engine")])

    def pause(self, key):
        with self.lock:
            it = self._get(key)
            if it and it["state"] == "running":
                it["ctl"] = "pause"
            elif it and it["state"] == "queued":
                it["state"] = "paused"

    def resume(self, key):
        with self.lock:
            it = self._get(key)
            if it and it["state"] in ("paused", "error", "cancelled"):
                self._refresh_sources(it)
                it.update(state="queued", err="", ctl=None, report=[], touched=time.time())
                log("dl.resume", key=key)
                self._pump()

    def cancel(self, key):
        with self.lock:
            it = self._get(key)
            if not it:
                return
            if it["state"] == "running":
                if self._wedged(it):
                    self._abandon(it, "cancelled", "")       # the worker is stuck: stop waiting for it
                else:
                    it["ctl"] = "cancel"
            else:
                it.update(state="cancelled", speed=0.0, eta=None, done=0)
                self._remove_part(it)
            self._pump()

    def reset(self, key):
        """Starts a download from the beginning: the partial file is removed and the item is queued again."""
        with self.lock:
            it = self._get(key)
            if not it:
                return
            it["gen"] += 1                                     # any running worker is no longer current
            self._refresh_sources(it)
            self._remove_part(it)
            it.update(state="queued", done=0, speed=0.0, eta=None, err="", report=[], ctl=None, samples=[],
                      touched=time.time())
            log("dl.reset", key=key)
            self._pump()

    def pause_all(self):
        for k in list(self.items):
            self.pause(k)

    def resume_all(self):
        for k in list(self.items):
            self.resume(k)

    def cancel_all(self):
        for k in list(self.items):
            if self.items[k]["state"] in ("running", "queued", "paused"):
                self.cancel(k)

    def import_file(self, key, src_path):
        """Uses a file downloaded elsewhere (browser, USB stick, another computer)."""
        a = next((x for x in self.core.assets() if x["key"] == key), None)
        if not a:
            raise ValueError("unknown file")
        os.makedirs(os.path.dirname(a["dest"]), exist_ok=True)
        if a["kind"] == "engine":
            self.core.install_engine_from(src_path, a.get("variant", "cpu"))
        else:
            tmp = a["dest"] + ".import"
            shutil.copyfile(src_path, tmp)
            if not self.core.file_ok(tmp, a["est"], strict_name=a["dest"]):
                os.remove(tmp)
                raise ValueError("This file does not look like the expected one (%s)." % os.path.basename(a["dest"]))
            os.replace(tmp, a["dest"])
        with self.lock:
            it = self._get(key)
            if it:
                it["gen"] += 1
                it.update(state="done", done=it["total"], err="", speed=0.0, eta=None, ctl=None)
        log("dl.import", key=key)
        self.core.on_files_changed()

    def active(self):
        with self.lock:
            return any(i["state"] in ("running", "queued") for i in self.items.values())

    def snapshot(self):
        with self.lock:
            self._reap_all()
            return [{k: v for k, v in it.items() if k not in ("ctl", "samples", "urls_fn")} for it in self.items.values()]

    # ---- internals

    def _get(self, key):
        return self.items.get(key)

    def _new_item(self, a):
        part = a["dest"] + ".part"
        return {"key": a["key"], "role": a["role"], "title": a["title"], "kind": a["kind"],
                "variant": a.get("variant"), "dest": a["dest"], "est": a["est"], "state": "queued", "urls_fn": a["urls_fn"],
                "done": os.path.getsize(part) if os.path.exists(part) else 0, "total": a["est"],
                "speed": 0.0, "eta": None, "err": "", "host": "", "report": [], "ctl": None,
                "samples": [], "gen": 0, "touched": time.time()}

    def _refresh_sources(self, it):
        """Takes the current source list for this file (a setting may have changed since the item was created)."""
        a = next((x for x in self.core.assets() if x["key"] == it["key"]), None)
        if a:
            it["urls_fn"] = a["urls_fn"]

    def _wedged(self, it):
        return it["state"] == "running" and time.time() - it.get("touched", 0) > WEDGED_SECONDS

    def _abandon(self, it, state, err):
        """Ends a running item whose worker has stopped reporting. The worker is left behind; its generation is out of date."""
        it["gen"] += 1
        it.update(state=state, err=err, speed=0.0, eta=None, ctl=None)
        if state == "cancelled":
            it["done"] = 0
            self._remove_part(it)
        log("dl.abandon", key=it["key"], state=state, done=it["done"])

    def _reap_all(self):
        for it in self.items.values():
            if self._wedged(it):
                self._abandon(it, "error", "Stopped: no progress for %s. Press Retry." % (
                    "%d minutes" % (WEDGED_SECONDS // 60) if WEDGED_SECONDS >= 60 else "%d seconds" % WEDGED_SECONDS))

    def _remove_part(self, it):
        try:
            os.remove(it["dest"] + ".part")
        except OSError:
            pass

    def _pump(self):
        """Starts the next queued download when no other is running. Called after every change of state."""
        with self.lock:
            self._reap_all()
            if any(i["state"] == "running" for i in self.items.values()):
                return
            nxt = next((i for i in self.items.values() if i["state"] == "queued"), None)
            if nxt is None:
                return
            nxt.update(state="running", ctl=None, touched=time.time(), gen=nxt["gen"] + 1)
            threading.Thread(target=self._worker, args=(nxt, nxt["gen"]), daemon=True).start()

    def _mine(self, it, gen):
        return it["gen"] == gen

    def _touch(self, it, gen):
        if self._mine(it, gen):
            it["touched"] = time.time()

    def _worker(self, it, gen):
        try:
            self._download(it, gen)
        except Exception as e:
            with self.lock:
                if self._mine(it, gen) and it["state"] == "running":
                    it.update(state="error", err=str(e)[:300], speed=0.0, eta=None)
            log("dl.error", key=it["key"], error=str(e)[:300])
        finally:
            try:
                self.core.on_files_changed()
            except Exception:
                pass
            self._pump()

    def _download(self, it, gen):
        dest, part = it["dest"], it["dest"] + ".part"
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with self.lock:
            if not self._mine(it, gen):
                return
            it["report"] = []
        try:
            urls = it["urls_fn"]()
        except Exception as e:
            raise RuntimeError("Could not work out where to download from: %s" % why(e))
        log("dl.start", key=it["key"], sources=len(urls), done=it["done"], total=it["total"])
        complete = False
        for url in urls:
            host = urllib.parse.urlparse(url).netloc
            for attempt in range(2):
                if it["ctl"] or not self._mine(it, gen):
                    break
                try:
                    it["host"] = host
                    self._fetch(it, url, part, gen)
                    complete = True
                    break
                except Stop:
                    break
                except Exception as e:
                    msg = "%s: %s" % (host, why(e))
                    log("dl.attempt_failed", key=it["key"], host=host, attempt=attempt, reason=msg[:200])
                    if attempt == 1 or isinstance(e, urllib.error.HTTPError):
                        it["report"].append(msg)
                    if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404):
                        break
                    for _ in range(15 * (attempt + 1)):          # back-off that still responds to pause and cancel
                        if it["ctl"] or not self._mine(it, gen):
                            break
                        time.sleep(0.1)
            if complete or it["ctl"] or not self._mine(it, gen):
                break
        if not self._mine(it, gen):
            return                                               # superseded by a reset or an abandon: nothing more to do
        with self.lock:
            ctl = it["ctl"]
            if ctl == "pause":
                it.update(state="paused", speed=0.0, eta=None, ctl=None)
                return
            if ctl == "cancel":
                self._remove_part(it)
                it.update(state="cancelled", done=0, speed=0.0, eta=None, ctl=None)
                log("dl.cancelled", key=it["key"])
                return
        if not complete and not os.path.exists(part) and not it["ctl"]:
            raise RuntimeError("The partial file was removed while downloading. Press Retry to start again.")
        if not complete:
            raise RuntimeError("Could not download. " + " · ".join(it["report"] or ["no source answered"]) +
                               "\nTry: a proxy, another source, a direct link, or Import file.")
        if it["kind"] == "engine":
            while self.core.engine_busy():                       # installing swaps the binary and stops the servers
                self._touch(it, gen)
                time.sleep(1)
            self.core.install_engine_from(part, it.get("variant") or "cpu")
            self._remove_part(it)
        elif it["kind"] == "wheel":
            pkg = it["key"].split(":", 1)[1]
            try:
                self.core.install_wheel(pkg, part)
            finally:
                self._remove_part(it)
        else:
            if not os.path.exists(part):
                raise RuntimeError("The partial file was removed while downloading. Press Retry to start again.")
            if not self.core.file_ok(part, it["est"], strict_name=dest):
                self._remove_part(it)
                log("dl.invalid", key=it["key"])
                raise RuntimeError("The downloaded file failed validation and was removed. Try again.")
            os.replace(part, dest)
        with self.lock:
            if self._mine(it, gen):
                it.update(state="done", done=it["total"], err="", speed=0.0, eta=None)
        log("dl.done", key=it["key"], bytes=it["done"])

    def _fetch(self, it, url, part, gen):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        req = urllib.request.Request(url, headers={"User-Agent": "KnowledgeBank/4"})
        if have:
            req.add_header("Range", "bytes=%d-" % have)
        try:
            r = self.core.opener().open(req, timeout=25)
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:
                it["done"] = it["total"] = have
                return
            raise
        with r:
            code = r.getcode()
            clen = int(r.headers.get("Content-Length") or 0)
            if code == 200:
                have = 0
                total = clen or it["est"]
            else:
                m = re.search(r"/(\d+)$", r.headers.get("Content-Range") or "")
                total = int(m.group(1)) if m else have + clen
            it["total"], it["done"] = total, have
            it["touched"] = time.time()
            samples = it["samples"] = [(time.time(), have)]
            mark = have                                          # bytes at the last progress step
            with open(part, "ab" if have else "wb") as o:
                while True:
                    if it["ctl"] or not self._mine(it, gen):
                        raise Stop()
                    # read1 returns what has arrived; read(n) would wait for all n bytes, so a slow stream would look stuck
                    b = r.read1(1 << 18) if hasattr(r, "read1") else r.read(1 << 18)
                    if not b:
                        break
                    o.write(b)
                    it["done"] += len(b)
                    now = time.time()
                    if it["done"] - mark >= PROGRESS_STEP:       # progress: 64 KB since the last step
                        mark = it["done"]
                        it["touched"] = now
                    elif now - it["touched"] > STALL_SECONDS:    # a trickle of data is not progress
                        raise RuntimeError("no progress for %d seconds" % STALL_SECONDS)
                    samples.append((now, it["done"]))
                    while samples and now - samples[0][0] > 4:
                        samples.pop(0)
                    if now - samples[0][0] > 0.4:
                        sp = (it["done"] - samples[0][1]) / (now - samples[0][0])
                        it["speed"] = sp
                        it["eta"] = (it["total"] - it["done"]) / sp if sp > 1 else None
        if it["total"] and it["done"] < it["total"]:
            raise RuntimeError("connection closed early")
