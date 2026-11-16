"""Storage in SQLite with full-text search, and the search index."""
import os
import json
import math
import hashlib
import sqlite3
import threading
from kb_extract import *
from kb_text import stem, word_root, tokens, edit_distance
from kb_config import MIN_MEANING_SIM, MEANING_MARGIN
from kb_log import log

# A word found in more than this share of the passages is filler for this bank (it matches almost everything),
# so it is not searched for. UNCALIBRATED: set from the logs once the coverage numbers are reviewed.
STOPWORD_SHARE = 0.3

class Store:
    """One writer connection, guarded by a lock, and one reader connection per thread.
    WAL mode lets the window read while indexing writes."""

    def __init__(self):
        os.makedirs(TEXTDIR, exist_ok=True)
        self.path = os.path.join(BANK, "kb.sqlite")
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.RLock()
        self._local = threading.local()
        self._readers = []                    # (thread, connection) pairs; dead threads are pruned, see _prune_locked
        self._rlock = threading.Lock()
        with self.lock:
            self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, src INTEGER, rel TEXT, size INTEGER,
                mtime INTEGER, status TEXT, note TEXT, nchunks INTEGER, th TEXT);
            CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, idx INTEGER,
                h TEXT, text TEXT);
            CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path);
            CREATE INDEX IF NOT EXISTS chunks_h ON chunks(h);
            CREATE INDEX IF NOT EXISTS files_src ON files(src);
            CREATE INDEX IF NOT EXISTS files_status ON files(status);
            CREATE TABLE IF NOT EXISTS vecs(h TEXT PRIMARY KEY, v BLOB);
            """)
            try:
                self.db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(tok, tokenize="unicode61 remove_diacritics 0")')
                self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts_v USING fts5vocab(fts, 'row')")
            except sqlite3.OperationalError as e:
                raise RuntimeError("This Python's SQLite has no FTS5 support (%s). Use a standard python.org / distro Python 3.8+." % e)
            self.db.commit()
        self.migrate()

    def rconn(self):
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            self._local.c = c
            with self._rlock:
                self._prune_locked()
                self._readers.append((threading.current_thread(), c))
        return c

    def _prune_locked(self):
        """Closes reader connections whose worker thread has ended. Each question starts new worker threads,
        so without this the connections (and their file handles) grew for the whole session."""
        alive = []
        for th, conn in self._readers:
            if th.is_alive():
                alive.append((th, conn))
            else:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
        self._readers = alive

    def close(self):
        """Closes all reader connections, then the writer. Safe to call twice."""
        with self._rlock:
            readers, self._readers = self._readers, []
        for _th, c in readers:
            try:
                c.close()
            except sqlite3.Error:
                pass
        with self.lock:
            try:
                self.db.commit()
                self.db.close()
            except sqlite3.Error:
                pass

    def migrate(self):
        if self.get("fts_ok") == 3:          # 3: stemmer and script-spacing changed, so rebuild the word index once
            return
        with self.lock:
            self.db.execute("DELETE FROM fts")
            batch = []
            for (i, text) in self.db.execute("SELECT id, text FROM chunks").fetchall():
                batch.append((i, " ".join(tokens(text))))
                if len(batch) >= 2000:
                    self.db.executemany("INSERT INTO fts(rowid, tok) VALUES(?,?)", batch)
                    batch = []
            if batch:
                self.db.executemany("INSERT INTO fts(rowid, tok) VALUES(?,?)", batch)
            self.db.commit()
        self.put("fts_ok", 3)

    def get(self, k, d=None):
        r = self.rconn().execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        if not r:
            return d
        try:
            return json.loads(r[0])
        except Exception:
            return d

    def put(self, k, v):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, json.dumps(v, ensure_ascii=False)))
            self.db.commit()

    def q(self, sql, a=()):
        return self.rconn().execute(sql, a).fetchall()

    def x(self, sql, a=()):
        with self.lock:
            self.db.execute(sql, a)
            self.db.commit()

    def xid(self, sql, a=()):
        """Runs a write and returns the new row id."""
        with self.lock:
            cur = self.db.execute(sql, a)
            self.db.commit()
            return cur.lastrowid


def thash(path):
    return hashlib.sha1(path.encode("utf-8", "replace")).hexdigest()[:20]


def chash(text):
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


def posix(p):
    return p.replace("\\", "/")


def extract_job(path, nice=5):
    """Runs in a worker process, so heavy parsing does not compete with the window for the GIL.
    nice is 15 on Light, so reading documents gives way to everything else on the computer."""
    try:
        if hasattr(os, "nice"):
            os.nice(nice)
    except Exception:
        pass
    return extract_file(path)


class Index:
    """Word search uses SQLite FTS5 with bm25. Meaning search uses one numpy matrix and a plain cosine comparison."""

    def __init__(self, store):
        self.st = store
        self.N = 0
        self._vocab = None
        self.ids, self.paths = [], []
        self.row_of = {}
        self.mat = None
        self.have = None
        self.dim = 0
        self.last_top = None
        self._df = {}
        self._mask = None
        self._mask_sig = None

    def reload(self, np):
        rows = self.st.q("SELECT c.id, c.path, v.v FROM chunks c LEFT JOIN vecs v ON v.h = c.h ORDER BY c.id")
        self._vocab = None
        self.ids = [r[0] for r in rows]
        self.paths = [r[1] for r in rows]
        self.row_of = {i: n for n, i in enumerate(self.ids)}
        self.N = len(rows)
        self._df.clear()
        self._mask = None
        self.mat = self.have = None
        self.dim = 0
        if not np or not rows:
            return
        blobs = [r[2] for r in rows]
        for b in blobs:
            if b is not None:
                self.dim = len(b) // 2
                break
        if not self.dim:
            return
        zero = bytes(self.dim * 2)
        have = [b is not None and len(b) == self.dim * 2 for b in blobs]
        buf = b"".join(b if h else zero for b, h in zip(blobs, have))
        self.mat = np.frombuffer(buf, dtype=np.float16).reshape(-1, self.dim).astype(np.float32)
        self.have = np.array(have, dtype=bool)

    def doc_freq(self, t):
        """How many passages contain the word (stemmed), read from the bank's own vocabulary."""
        r = self.st.q("SELECT doc FROM fts_v WHERE term=?", (t,))
        return r[0][0] if r else 0

    def content_terms(self, terms):
        """The words of a question that distinguish passages in THIS bank. A word found in more than STOPWORD_SHARE of
        the passages is filler (in any language) and is dropped. Words the bank does not
        contain are kept: they still match nothing when searched. No word list is used."""
        limit = max(1, STOPWORD_SHARE * (self.N or 1))
        kept = [t for t in terms if self.doc_freq(t) <= limit]
        return kept or list(terms)          # never leave the search with no words

    def idf(self, t):
        v = self._df.get(t)
        if v is None:
            r = self.st.q("SELECT doc FROM fts_v WHERE term=?", (t,))
            v = self._df[t] = math.log(1 + (self.N or 1) / ((r[0][0] if r else 0) or 1))
        return v

    def vocabulary(self):
        """The bank's words, grouped by length, so a spelling check only compares words of similar length."""
        if self._vocab is None:
            by_len = {}
            for (term,) in self.st.q("SELECT term FROM fts_v"):
                by_len.setdefault(len(term), []).append(term)
            self._vocab = by_len
        return self._vocab

    def expand(self, terms):
        """Search alternatives for each term: the term itself, its word root (ایرانی finds ایران), and close spellings from the bank's own words. Long words tolerate one typo, very long ones two."""
        out = []
        by_len = self.vocabulary() if terms else {}
        for t in terms:
            alts = [t]
            if len(t) >= 4:
                root = word_root(t)
                if root != t and len(root) >= 3:
                    # Stem the root the same way indexed words were stemmed, so both sides match.
                    stemmed_root = stem(root)
                    if len(stemmed_root) >= 3:
                        alts.append(stemmed_root + "*")
                elif len(t) >= 4:
                    alts.append(t + "*")
            if len(t) >= 5:
                limit = 2 if len(t) >= 8 else 1
                close = [v for n in range(len(t) - limit, len(t) + limit + 1) for v in by_len.get(n, [])
                         if v != t and edit_distance(t, v, limit) <= limit]
                alts += sorted(close, key=lambda v: edit_distance(t, v, limit))[:6]
            out.append(alts)
        return out

    @staticmethod
    def _group_expr(alts):
        """One term's alternatives as an FTS5 expression: (a OR b* OR c)."""
        return "(" + " OR ".join(('"%s"*' % a.rstrip("*")) if a.endswith("*") else '"%s"' % a.replace('"', "")
                                 for a in alts) + ")"

    def bm25(self, terms, limit, groups=None):
        if not terms:
            return []
        groups = self.expand(terms) if groups is None else groups
        q = " OR ".join(self._group_expr(alts) for alts in groups)
        try:
            rows = self.st.q("SELECT rowid, bm25(fts) FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT ?", (q, limit))
        except sqlite3.OperationalError as e:
            log("bm25.sql_error", query=q, error=str(e))
            return []
        return [(i, -s) for i, s in rows]

    def bm25_hits(self, terms, limit):
        """Word search: passages ranked by bm25, best first."""
        if not terms:
            return []
        groups = self.expand(terms)
        hits = self.bm25(terms, limit, groups=groups)
        log("bm25", groups=groups, raw_hits=len(hits), best=hits[0][1] if hits else None)
        return hits if hits and hits[0][1] > 0 else []

    def vector_hits(self, np, qv, limit, core=None, min_sim=None):
        """Meaning search: passages whose cosine similarity to the question is at least min_sim (see MIN_MEANING_SIM).
        Returns (row, similarity) pairs, best first. Rows index self.ids."""
        min_sim = MIN_MEANING_SIM if min_sim is None else min_sim
        self.last_top = None
        self.last_floor = None
        if self.mat is None or not self.N or qv is None or qv.shape[-1] != self.mat.shape[1]:
            return []                             # no vectors, or the query came from a different model
        sims = np.where(self.have, self.mat @ qv, -1.0)     # rows and qv are already normalised, so this is a dot product
        if core is not None:
            mask = self.allowed_mask(np, core)
            if mask is not None:
                sims = np.where(mask, sims, -1.0)
        k = min(limit, sims.shape[0])
        if k <= 0:
            return []
        part = np.argpartition(-sims, k - 1)[:k]          # top-k without sorting every passage
        order = part[np.argsort(-sims[part])]
        self.last_top = float(sims[order[0]]) if len(order) else None   # best score, stored for the calibration log
        # Keep passages within MEANING_MARGIN of the best score, and never below the absolute floor.
        # -1.0 marks rows that are unticked or have no vector, so they are never returned.
        if self.last_top is None:
            return []
        floor = max(min_sim, self.last_top - MEANING_MARGIN)
        self.last_floor = floor
        return [(int(i), float(sims[i])) for i in order if sims[i] >= floor and sims[i] > -0.9999]

    def allowed_mask(self, np, core):
        if not core.off:
            return None
        sig = (tuple(sorted(core.off)), self.N)
        if self._mask is None or self._mask_sig != sig:
            self._mask = np.array([core.is_on(p) for p in self.paths], dtype=bool)
            self._mask_sig = sig
        return self._mask
