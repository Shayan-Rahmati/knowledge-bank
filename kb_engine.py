"""Runs llama.cpp's llama-server for embeddings and answers, each as a separate process."""
import os
import re
import json
import time
import threading
import subprocess
import traceback
import shutil
import sys
import urllib.request, urllib.error, urllib.parse
from kb_net import *
from kb_config import lower_priority, duty_pause, threads_for, DATA
from kb_log import log as klog, error

PIDFILE = os.path.join(ENGINE_DIR, "pids.json")


def _pids_read():
    try:
        with open(PIDFILE, encoding="utf-8") as f:
            return [int(x) for x in json.load(f)]
    except (OSError, ValueError, TypeError):
        return []


def _pids_write(pids):
    try:
        os.makedirs(ENGINE_DIR, exist_ok=True)
        with open(PIDFILE, "w", encoding="utf-8") as f:
            json.dump(sorted(set(pids)), f)
    except OSError:
        pass


def _is_engine(pid):
    """True only for a live llama-server process. Checked on Linux only, where /proc can be read safely."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return b"llama-server" in f.read()
    except OSError:
        return False


def reap_orphans():
    """Stops llama-server processes left over from a run that did not close cleanly."""
    for pid in _pids_read():
        if _is_engine(pid):
            try:
                os.kill(pid, 15)
            except OSError:
                pass
    _pids_write([])

def clean_think(t):
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    i = t.find("<think>")
    return (t[:i] if i >= 0 else t).lstrip()


class Engine:
    _tb_ok = True                              # whether this build of llama-server accepts the prompt-thread option
    _ngl_ok = True                             # whether to ask for GPU layers; turned off if the GPU fails
    """Runs the official llama.cpp `llama-server` as managed child processes (embeddings and answers).
    A separate process per role keeps native code away from the window, and always supports the newest models."""

    def __init__(self, core):
        reap_orphans()
        self.core = core
        self.srv = {}              # role -> {p: Popen, port: int, model: path}
        self.rlock = {r: threading.RLock() for r in ("embed", "gen", "rerank")}
        self.last_use = {}
        self._bins = {}
        self.started_once = set()             # roles loaded at least once this session
        self.last_exit = {}                   # role -> short reason, when a model stopped by itself
        threading.Thread(target=self._idle_loop, daemon=True).start()
        threading.Thread(target=self._watch_loop, daemon=True).start()

    _cpu_only = False                          # set when the GPU build could not start: the CPU build is used from then on

    def variant(self):
        """'gpu' when the GPU build should be used now, otherwise 'cpu'."""
        return "cpu" if (self._cpu_only or not gpu_backend()) else "gpu"

    def _find(self, variant):
        """Newest llama-server inside an engine folder of this variant, or None."""
        best = (-1.0, None)
        names = ("llama-server.exe",) if os.name == "nt" else ("llama-server",)
        if os.path.isdir(ENGINE_DIR):
            for root, _d, files in os.walk(ENGINE_DIR):
                if root == ENGINE_DIR:
                    continue
                top = os.path.relpath(root, ENGINE_DIR).split(os.sep)[0]   # the install folder this file sits in
                legacy = variant == "cpu" and re.match(r"llama-\d{8}-", top)  # single-build installs of earlier versions
                if not (top.startswith("llama-%s-" % variant) or legacy):
                    continue
                for n in names:
                    if n in files:
                        p = os.path.join(root, n)
                        mt = os.path.getmtime(p)
                        if mt > best[0]:
                            best = (mt, p)
        return best[1]

    def installed(self, variant):
        """True when this build is present (the custom engine path counts for either build)."""
        cand = self.core.settings.get("engine_path") or ""
        if cand and os.path.isfile(cand):
            return True
        return self._find(variant) is not None

    def binary(self, variant=None):
        """The llama-server to run. GPU build when wanted and installed, otherwise the CPU build."""
        variant = variant or self.variant()
        cache = self._bins.get(variant)
        if cache and time.time() - cache[0] < 4:
            return cache[1]
        found = None
        cand = self.core.settings.get("engine_path") or ""
        if cand and os.path.isfile(cand):
            found = cand
        if not found:
            found = self._find(variant)
        if not found and variant == "gpu":
            found = self._find("cpu")          # GPU build not installed yet: run the CPU build
        if not found and os.path.isdir(ENGINE_DIR):
            found = self._find("cpu") or self._find("gpu")   # folders from earlier versions
        if not found:
            found = shutil.which("llama-server")
        self._bins[variant] = (time.time(), found)
        return found

    def is_gpu_binary(self, path=None):
        """True when the binary about to run is the GPU (Vulkan) build, or a custom path that may be one."""
        path = path or self.binary()
        return bool(path) and gpu_backend() is not None and (
            "llama-gpu-" in path or path == (self.core.settings.get("engine_path") or ""))

    def forget_binary(self):
        self._bins = {}

    def _free_port(self):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def threads(self, role):
        """Processor threads for one server. The answer model always gets at least 2 (when the machine has 2): answers
        are almost all token generation, and one thread made them several times slower. On Light the answer model
        still runs at the lowest priority (see spawn_kwargs), so the window stays responsive; indexing uses 1 thread."""
        level = self.core.settings.get("resources", "balanced")
        threads = threads_for(level)
        if role == "gen":
            # the answer is the slow part (prompt reading and token generation), and indexing is paused while it runs,
            # so the answer model gets the full thread count. Takes effect when the server next starts.
            threads = max(threads_for("full"), min(2, os.cpu_count() or 1))
        elif role == "rerank":
            threads = max(threads, min(2, os.cpu_count() or 1))
        elif role == "embed" and level != "full":
            threads = 1         # indexing runs in the background; one thread leaves cores free for answers
        return threads

    def _cmd(self, role, model, port, batch_threads=True):
        e = self.core.model_entry(role)
        threads = self.threads(role)
        bin_ = self.binary()
        c = [bin_, "-m", model, "--host", "127.0.0.1", "--port", str(port), "-t", str(threads)]
        if batch_threads:                 # reading the prompt (the passages) uses the same thread limit
            c += ["-tb", str(threads)]
        if self.is_gpu_binary(bin_) and self._ngl_ok:   # put as many layers on the GPU as fit; "auto" lets llama.cpp decide
            c += ["-ngl", "auto"]
        if role == "embed":
            c += ["--embeddings", "--pooling", e["pooling"], "-c", str(e["ctx"]), "-b", str(e["ctx"]), "-ub", str(e["ctx"])]
        elif role == "rerank":
            c += ["--reranking", "-c", str(e["ctx"]), "-b", str(e["ctx"]), "-ub", str(e["ctx"])]
        else:
            # one slot: the whole context goes to one conversation, and the prompt cache is reused between
            # turns and for the grounding retry. With several slots, each one gets only part of the context.
            c += ["-c", str(e.get("ctx", 4096)), "-np", "1", "--jinja", "--chat-template-kwargs", '{"enable_thinking":false}']
        return c

    def _log_offload(self, role, logp):
        """Writes to kb.log whether the model went to the GPU: llama-server prints how many layers it offloaded."""
        try:
            with open(logp, "rb") as f:
                text = f.read().decode("utf-8", "replace")
            m = re.search(r"offloaded (\d+)/(\d+) layers", text)
            # context per slot and slot count: with several slots, each gets only part of the context
            klog("engine.ctx", role=role, lines=[l.strip()[:160] for l in text.splitlines()
                                                  if re.search(r"n_ctx|n_parallel|slot", l, re.I)][:8])
            # the lines llama-server prints about devices and layers, so the log shows what really ran
            info = [l.strip()[:160] for l in text.splitlines() if re.search(r"offload|vulkan|device|ggml_|no gpu|cpu", l, re.I)][:6]
            klog("engine.gpu", role=role, backend=gpu_backend() or "cpu",
                 offloaded=("%s/%s layers" % (m.group(1), m.group(2))) if m else "not reported", lines=info)
        except OSError:
            pass

    def ensure(self, role, timeout=240):
        with self.rlock[role]:
            s = self.srv.get(role)
            model = self.core.model_path(role)
            if s and s["p"].poll() is None and s["model"] == model:
                self.last_use[role] = time.time()
                return s["port"]
            self.stop(role)
            if not self.binary():
                raise RuntimeError("The llama.cpp engine is not installed yet (Downloads → Engine).")
            if not os.path.isfile(model):
                raise RuntimeError("The model file is missing (Downloads).")
            if not self.core.file_ok(model, self.core.model_entry(role)["size"]):
                raise RuntimeError("The model file is damaged or incomplete. Delete it in Downloads and download it again.")
            port = self._free_port()
            os.makedirs(os.path.join(DATA, "logs"), exist_ok=True)
            logp = os.path.join(DATA, "logs", "%s.log" % role)      # engine output is kept with the other logs
            log = open(logp, "wb")
            env = dict(os.environ)
            bdir = os.path.dirname(self.binary())
            if os.name != "nt":
                env["LD_LIBRARY_PATH"] = bdir + os.pathsep + env.get("LD_LIBRARY_PATH", "")
            extra = dict(NOWIN, **spawn_kwargs(self.core.settings.get("resources", "balanced")))
            if role == "embed" and os.name != "nt":
                extra["preexec_fn"] = lambda: os.nice(10)     # indexing yields to answers on a busy computer
            p = subprocess.Popen(self._cmd(role, model, port, batch_threads=self._tb_ok), stdout=log,
                                 stderr=subprocess.STDOUT, cwd=bdir, env=env, **extra)
            self.srv[role] = {"p": p, "port": port, "model": model}
            on_gpu = self.is_gpu_binary(self.binary())
            klog("engine.spawn", role=role, pid=p.pid, port=port, model=os.path.basename(model), binary=self.binary(),
                 build="gpu" if on_gpu else "cpu", backend=(gpu_backend() if (on_gpu and self._ngl_ok) else None) or "cpu")
            _pids_write(_pids_read() + [p.pid])
            self.started_once.add(role)
            t0 = time.time()
            while time.time() - t0 < timeout:
                if p.poll() is not None:
                    break
                try:
                    with LOCAL.open("http://127.0.0.1:%d/health" % port, timeout=2) as r:
                        if r.getcode() == 200:
                            self.last_use[role] = time.time()
                            self._log_offload(role, logp)
                            return port
                except urllib.error.HTTPError:
                    pass                      # 503 means the model is still loading
                except Exception:
                    pass
                time.sleep(0.4)
            log.flush()
            tail = ""
            try:
                with open(logp, "rb") as f:
                    f.seek(0, 2)
                    f.seek(max(0, f.tell() - 1500))
                    tail = f.read().decode("utf-8", "replace").strip().splitlines()[-4:]
                    tail = " | ".join(tail)
            except Exception:
                pass
            diag = []
            try:
                with open(logp, "rb") as f:
                    diag = [l.strip()[:200] for l in f.read().decode("utf-8", "replace").splitlines()
                            if re.search(r"error|fail|memory|abort|exit|killed|cannot|unknown", l, re.I)][-6:]
            except Exception:
                pass
            klog("engine.start_failed", role=role, tail=tail, exit=p.poll(), diag=diag)
            self.stop(role)
            if self._tb_ok and re.search(r"threads-batch|\-tb\b|unknown option|invalid argument", tail or "", re.I):
                self._tb_ok = False            # an older build without this option: start again without it
                return self.ensure(role, timeout)
            gpu_err = re.search(r"\-ngl|n-gpu-layers|vulkan|out of memory|device|dll|shared object|cannot open|loader", tail or "", re.I)
            if self._ngl_ok and on_gpu and gpu_err:
                self._ngl_ok = False           # the GPU build runs, but not with GPU layers: start again without them
                klog("engine.gpu_failed", role=role, tail=tail)
                return self.ensure(role, timeout)
            if on_gpu and not self._cpu_only and gpu_err and self._find("cpu"):
                self._cpu_only = True          # the GPU build cannot start on this machine: use the CPU build from now on
                self._ngl_ok = True
                self.forget_binary()
                klog("engine.cpu_fallback", role=role, tail=tail)
                return self.ensure(role, timeout)
            raise RuntimeError("The engine did not start (%s). If it says 'unknown model architecture', update the engine in Downloads. Log: %s" % (tail or "no output", logp))

    def _watch_loop(self):
        """Notices a model process that stopped on its own, logs why, and starts it again in the background."""
        while not self.core.closing:
            time.sleep(2)
            try:
                for role, s in list(self.srv.items()):
                    code = s["p"].poll()
                    if code is None:
                        continue
                    self.srv.pop(role, None)
                    klog("engine.exited", role=role, code=code)
                    tail = ""
                    try:
                        with open(os.path.join(DATA, "logs", "%s.log" % role), "rb") as f:
                            f.seek(0, 2)
                            f.seek(max(0, f.tell() - 800))
                            tail = " | ".join(f.read().decode("utf-8", "replace").strip().splitlines()[-3:])
                    except OSError:
                        pass
                    reason = "exit code %s%s" % (code, " (ended by the system: out of memory?)" if code in (-9, 137) else "")
                    self.last_exit[role] = reason
                    os.makedirs(os.path.join(DATA, "logs"), exist_ok=True)
                    with open(os.path.join(DATA, "logs", "engine_exit.txt"), "a", encoding="utf-8") as f:
                        f.write("%s %s stopped: %s\n  log: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), role, reason, tail))
                    self.core.start_prewarm()         # restart now, not on the next question
            except Exception:
                traceback.print_exc()

    def is_running(self, role):
        """True when this role's model is loaded and serving."""
        s = self.srv.get(role)
        return bool(s and s["p"].poll() is None)

    def stop(self, role=None):
        # Ask every server to exit first, then wait on all of them together for at most 2 seconds.
        # Waiting on each one in turn (4 s each) froze the window while the app closed.
        procs = []
        for r in ([role] if role else list(self.srv)):
            s = self.srv.pop(r, None)
            if s:
                try:
                    s["p"].terminate()
                except Exception:
                    pass
                procs.append(s["p"])
        deadline = time.time() + 0.6             # a server busy with a token can take a moment; past this it is killed
        for p in procs:
            try:
                p.wait(timeout=max(0.05, deadline - time.time()))
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        if procs:
            gone = {p.pid for p in procs}
            _pids_write([x for x in _pids_read() if x not in gone])

    def _idle_loop(self):
        while True:
            time.sleep(30)
            try:
                if self.core.settings.get("keep_loaded", True):
                    continue                      # models stay loaded while the app is open
                for role in list(self.srv):
                    limit = 3600 if role == "embed" else 1800
                    idle = time.time() - self.last_use.get(role, 0)
                    if idle > limit and not (role == "embed" and self.core.prog["meaning"]["busy"]):
                        self.stop(role)
            except Exception:
                traceback.print_exc()

    def _post(self, role, path, payload, timeout=300):
        for attempt in (0, 1):
            port = self.ensure(role)
            req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            try:
                with LOCAL.open(req, timeout=timeout) as r:
                    self.last_use[role] = time.time()
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                raise RuntimeError("engine said HTTP %s %s" % (e.code, body))
            except (ConnectionError, urllib.error.URLError):
                if attempt == 1:
                    raise
                self.stop(role)
            except OSError:
                # a timeout while reading: the caller has given up, so stop the server.
                # Otherwise llama-server keeps computing the abandoned request and makes the next one wait behind it.
                klog("engine.abandoned", role=role, path=path)
                self.stop(role)
                raise
        raise RuntimeError("engine unavailable")

    def busy(self):
        """True while an embedding or an answer is being computed, so an engine install waits."""
        return getattr(self, "_inflight", 0) > 0

    def rerank(self, query, docs):
        """Scores each passage against the question with the reranker. Returns one score per passage, in the same order."""
        r = self._post("rerank", "/v1/rerank", {"query": query, "documents": docs, "top_n": len(docs)})
        scores = [None] * len(docs)
        for item in r.get("results") or []:
            s = float(item["relevance_score"])
            if s == s:                              # NaN would break the sort and the gate
                scores[int(item["index"])] = s
        if any(s is None for s in scores):          # a partial or differently shaped answer must not be ranked on guesses
            raise RuntimeError("reranker returned %d of %d scores" % (sum(s is not None for s in scores), len(docs)))
        return scores

    def embed(self, texts, kind):
        self._inflight = getattr(self, "_inflight", 0) + 1
        try:
            return self._embed(texts, kind)
        finally:
            self._inflight -= 1

    def _embed(self, texts, kind):
        if kind == "passage":                    # indexing waits while a question is being answered, so the answer is not slowed
            waited = time.time()
            while self.core.question_busy.is_set() and not self.core.closing and time.time() - waited < 300:
                time.sleep(0.2)
        np = self.core.try_numpy()
        t0 = time.time()
        e = self.core.model_entry("embed")
        pre = e["qpre"] if kind == "query" else e["dpre"]
        lim = 1800
        for tr in (lim, 900, 400):
            try:
                r = self._post("embed", "/v1/embeddings", {"input": [pre + t[:tr] for t in texts], "model": "x", "encoding_format": "float"})
                break
            except RuntimeError as ex:
                if tr == 400 or ("too large" not in str(ex) and "exceed" not in str(ex) and "HTTP 400" not in str(ex) and "HTTP 500" not in str(ex)):
                    raise
        data = sorted(r["data"], key=lambda d: d.get("index", 0))
        v = np.array([d["embedding"] for d in data], dtype=np.float32)
        v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
        took = time.time() - t0
        klog("embed", kind=kind, texts=len(texts), dim=int(v.shape[1]) if v.ndim == 2 else 0,
            seconds=round(took, 3), norms_ok=bool(np.allclose(np.linalg.norm(v, axis=1), 1, atol=1e-3)))
        if kind == "passage":            # indexing yields between batches, so it never holds a core at 100%
            ratio = duty_pause(self.core.settings.get("resources", "balanced"))
            if ratio > 0:
                time.sleep(took * ratio)
        return v

    def chat(self, messages, max_tokens=320, on_delta=None):
        self._inflight = getattr(self, "_inflight", 0) + 1
        try:
            return self._chat(messages, max_tokens, on_delta)
        finally:
            self._inflight -= 1

    def _chat(self, messages, max_tokens=320, on_delta=None):
        for attempt in (0, 1):
            port = self.ensure("gen")
            t_req = time.time()
            klog("engine.request", role="gen", port=port, attempt=attempt, messages=len(messages),
                 chars=sum(len(m.get("content", "")) for m in messages), max_tokens=max_tokens)
            # Qwen3.5 2B in non-thinking mode, with the sampling settings from its model card.
            # Very low temperatures make this model loop, so the card's values stay as they are.
            payload = {"model": "x", "messages": messages,      # no token limit: the reply ends when the model finishes or the context is full
                       "temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5,
                       "stream": True, "chat_template_kwargs": {"enable_thinking": False},
                       "cache_prompt": True}      # reuse the processed prefix (system prompt, history, retry) from the last request
            req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % port, data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            text = ""
            finished = False                 # set when the stream says it is complete ([DONE] or a finish reason)
            aborted = False                  # set when the user pressed Stop
            done_ok = False                  # set only when a complete reply is returned
            truncated = False                # set when the reply hit the token limit: it is kept, but logged as cut short
            try:
                with LOCAL.open(req, timeout=600) as r:
                    for raw in r:
                        if self.core.gen_abort.is_set():      # Stop: leave the stream; the server is stopped below
                            aborted = True
                            break
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        d = line[5:].strip()
                        if d == "[DONE]":
                            finished = True
                            break
                        try:
                            j = json.loads(d)
                            if j.get("choices") and j["choices"][0].get("finish_reason"):
                                finished = True
                                if j["choices"][0]["finish_reason"] == "length":
                                    truncated = True
                            tm = j.get("timings")          # llama-server sends its own timing on the last chunk
                            if isinstance(tm, dict):
                                klog("engine.timings", role="gen", prompt_tokens=tm.get("prompt_n"),
                                     prompt_ms=round(tm.get("prompt_ms") or 0), prompt_tok_s=round(tm.get("prompt_per_second") or 0, 1),
                                     gen_tokens=tm.get("predicted_n"), gen_ms=round(tm.get("predicted_ms") or 0),
                                     gen_tok_s=round(tm.get("predicted_per_second") or 0, 1), threads=self.threads("gen"))
                            delta = j["choices"][0]["delta"].get("content") or ""
                        except Exception:
                            continue
                        if delta:
                            text += delta
                            if on_delta:
                                on_delta(clean_think(text))
                # Stop can close the stream from the server side before any text arrives: that is still a Stop, not an error
                if aborted or (not finished and self.core.gen_abort.is_set()):
                    klog("engine.response", role="gen", seconds=round(time.time() - t_req, 2), chars=len(text), status="aborted")
                    return clean_think(text)           # Stop keeps what was written so far
                if not finished:
                    # the connection closed before the model finished: a cut-off reply must not be saved as an answer
                    klog("engine.response", role="gen", seconds=round(time.time() - t_req, 2), chars=len(text), status="incomplete")
                    raise RuntimeError("the answer stopped early (the stream ended before it was complete)")
                self.last_use["gen"] = time.time()
                klog("engine.response", role="gen", seconds=round(time.time() - t_req, 2), chars=len(text),
                     status="truncated" if truncated else "ok", max_tokens=max_tokens)
                done_ok = True
                return clean_think(text)
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                raise RuntimeError("engine said HTTP %s %s" % (e.code, body))
            except (ConnectionError, urllib.error.URLError):
                if self.core.gen_abort.is_set():          # Stop killed the server: this is the user's choice, not a failure
                    klog("engine.response", role="gen", seconds=round(time.time() - t_req, 2), chars=len(text), status="aborted")
                    return clean_think(text)           # Stop keeps what was written so far
                if attempt == 1 or text:
                    raise
                self.stop("gen")
            finally:
                if not done_ok:
                    # the app is no longer waiting for this reply (timeout, error, or cut-off stream): stop the server
                    # so llama-server does not keep generating it and block the next question
                    self.stop("gen")
        return ""
