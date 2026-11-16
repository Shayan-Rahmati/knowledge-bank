"""Chat history (stored in the bank database) and the context sent to the model.

Messages form a tree. Each message knows its parent, and each chat remembers its latest message (leaf).
The conversation shown is the path from the leaf back to the first message. When a question is edited,
the edit becomes a sibling branch: nothing is deleted, and the user can switch between branches.

Each saved assistant message has a kind:
  "answer"    an AI answer; sent back to the model as conversation history
  "passages"  a passage-only answer (no AI text); kept for the transcript, never sent to the model
extra holds the answer's passages and citations as JSON, so a reopened chat shows the same sources.

Storage failures never break a question: each method logs the error to data/logs/chat_errors.txt
and returns an empty result, so the answer still appears (it just is not saved)."""
import json
import os
import sqlite3
import time
import traceback
import uuid
from kb_config import CHARS_PER_TOKEN, PROMPT_RESERVE_TOKENS, DATA
from kb_log import log as klog, error as kerror

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY, title TEXT, created INTEGER, updated INTEGER);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, chat TEXT, role TEXT,
    content TEXT, sources TEXT, created INTEGER);
CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat, id);
"""

# columns added after the first release; existing databases get them on start
MIGRATIONS = [
    ("messages", "kind", "TEXT NOT NULL DEFAULT 'answer'"),
    ("messages", "extra", "TEXT"),
    ("messages", "parent", "INTEGER"),
    ("chats", "leaf", "INTEGER"),
]

LOG = os.path.join(DATA, "logs", "chat_errors.txt")

AUTO = "auto"          # add(): attach the message to the chat's latest message


def _log(where):
    kerror("chat:" + where)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), where, traceback.format_exc()))
    except OSError:
        pass


def _json_list(raw):
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def _json_obj(raw):
    try:
        v = json.loads(raw) if raw else None
        return v if isinstance(v, dict) else None
    except (TypeError, ValueError):
        return None


def _dump(v):
    return json.dumps(v, ensure_ascii=False, default=str)


class ChatStore:
    def __init__(self, store):
        self.st = store
        try:
            with store.lock:
                store.db.executescript(SCHEMA)
                cols = {r[1] for r in store.db.execute("PRAGMA table_info(messages)")}
                chat_cols = {r[1] for r in store.db.execute("PRAGMA table_info(chats)")}
                for table, col, decl in MIGRATIONS:
                    have = cols if table == "messages" else chat_cols
                    if col in have:
                        continue
                    try:
                        store.db.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, decl))
                    except sqlite3.Error:
                        _log("migration %s.%s" % (table, col))
                store.db.commit()
                n_back = store.db.execute("SELECT COUNT(*) FROM chats WHERE leaf IS NULL AND id IN (SELECT chat FROM messages)").fetchone()[0]
                klog("chat.schema", messages_cols=sorted(cols), chats_cols=sorted(chat_cols), legacy_chats_to_backfill=n_back)
                # run after every column exists: chats saved before the leaf column get their parent links and leaf
                self._backfill_parents(store.db)
                store.db.commit()
        except sqlite3.Error:
            _log("chat schema")

    @staticmethod
    def _backfill_parents(db):
        """Chats saved before branches existed are a straight line: each message's parent is the one before it.
        Only chats whose leaf is still unset are touched, so this is safe to run on every start."""
        for (cid,) in db.execute("SELECT id FROM chats WHERE leaf IS NULL AND id IN (SELECT chat FROM messages)").fetchall():
            ids = [r[0] for r in db.execute("SELECT id FROM messages WHERE chat=? ORDER BY id", (cid,))]
            prev = None
            for mid in ids:
                db.execute("UPDATE messages SET parent=? WHERE id=?", (prev, mid))
                prev = mid
            db.execute("UPDATE chats SET leaf=? WHERE id=?", (prev, cid))

    def new_chat(self, title=""):
        """Returns the new chat id, or None if storage failed."""
        cid, now = uuid.uuid4().hex, int(time.time())
        try:
            self.st.x("INSERT INTO chats(id, title, created, updated, leaf) VALUES(?,?,?,?,NULL)", (cid, title, now, now))
            klog("chat.new", chat=cid[:8], title=title)
            return cid
        except sqlite3.Error:
            _log("new_chat")
            return None

    def chats(self):
        try:
            rows = self.st.q("SELECT id, title, updated FROM chats ORDER BY updated DESC")
        except sqlite3.Error:
            _log("chats")
            return []
        return [{"id": r[0], "title": r[1], "updated": r[2]} for r in rows]

    def title(self, chat_id):
        try:
            r = self.st.q("SELECT title FROM chats WHERE id=?", (chat_id,))
            return r[0][0] if r else ""
        except sqlite3.Error:
            return ""

    def rename(self, chat_id, title):
        title = (title or "").strip()[:80]
        if not chat_id or not title:
            return False
        try:
            self.st.x("UPDATE chats SET title=? WHERE id=?", (title, chat_id))
            return True
        except sqlite3.Error:
            _log("rename chat")
            return False

    def _leaf(self, chat_id):
        r = self.st.q("SELECT leaf FROM chats WHERE id=?", (chat_id,))
        return r[0][0] if r else None

    def add(self, chat_id, role, content, sources=None, kind="answer", extra=None, parent=AUTO):
        """Saves one message after the chat's latest message (or after `parent`, to start a branch).
        Returns the message id, or None if there is no chat or storage failed."""
        if not chat_id:
            return None
        content = "" if content is None else str(content)
        now = int(time.time())
        try:
            if parent == AUTO:
                parent = self._leaf(chat_id)
            mid = self.st.xid("INSERT INTO messages(chat, role, content, sources, created, kind, extra, parent) "
                              "VALUES(?,?,?,?,?,?,?,?)",
                              (chat_id, role, content, _dump(sources or []), now, kind,
                               _dump(extra) if extra is not None else None, parent))
            self.st.x("UPDATE chats SET updated=?, leaf=? WHERE id=?", (now, mid, chat_id))
            if role == "user" and not self.title(chat_id):
                self.st.x("UPDATE chats SET title=? WHERE id=?", (content[:60], chat_id))
            klog("chat.add", chat=chat_id[:8], msg=mid, role=role, kind=kind, parent=parent, chars=len(content),
                 sources=len(sources or []))
            return mid
        except sqlite3.Error:
            _log("add message")
            return None

    def update(self, message_id, content, sources=None, kind="answer", extra=None):
        """Replaces a saved message (used when an AI answer replaces the passage-only one)."""
        if not message_id:
            return False
        try:
            self.st.x("UPDATE messages SET content=?, sources=?, kind=?, extra=? WHERE id=?",
                      ("" if content is None else str(content), _dump(sources or []), kind,
                       _dump(extra) if extra is not None else None, message_id))
            return True
        except sqlite3.Error:
            _log("update message")
            return False

    def parent_of(self, message_id):
        r = self.st.q("SELECT parent FROM messages WHERE id=?", (message_id,))
        return r[0][0] if r else None

    def messages(self, chat_id):
        """The conversation as shown: the path from the chat's latest message back to its first."""
        if not chat_id:
            return []
        klog("chat.load", chat=str(chat_id)[:8])
        try:
            rows = self.st.q("SELECT id, role, content, sources, kind, extra, parent FROM messages WHERE chat=?",
                             (chat_id,))
            leaf = self._leaf(chat_id)
        except sqlite3.Error:
            _log("messages")
            return []
        by_id = {r[0]: r for r in rows}
        if leaf in by_id:
            path, seen, cur = [], set(), leaf
            while cur in by_id and cur not in seen:
                seen.add(cur)
                r = by_id[cur]
                path.append(r)
                cur = r[6]
            ordered = list(reversed(path))
        else:                       # no usable pointer: show everything in the order it was written
            ordered = [by_id[i] for i in sorted(by_id)]
        klog("chat.loaded", chat=str(chat_id)[:8], shown=len(ordered), stored=len(rows), leaf_found=leaf in by_id)
        return [{"id": r[0], "role": r[1], "content": r[2] or "", "sources": _json_list(r[3]),
                 "kind": r[4] or "answer", "extra": _json_obj(r[5])} for r in ordered]

    def branches(self, message_id):
        """(position, total, sibling ids) for a message: the other versions of it that start at the same point."""
        r = self.st.q("SELECT chat, role, parent FROM messages WHERE id=?", (message_id,))
        if not r:
            return 1, 1, [message_id]
        chat, role, parent = r[0]
        sibs = [x[0] for x in self.st.q("SELECT id FROM messages WHERE chat=? AND role=? AND parent IS ? ORDER BY id",
                                        (chat, role, parent))]
        if message_id not in sibs:
            sibs.append(message_id)
        return sibs.index(message_id) + 1, len(sibs), sibs

    def switch_branch(self, chat_id, message_id):
        """Makes a branch the one shown: the chat continues from its newest message."""
        if not chat_id or not message_id:
            return False
        try:
            cur, seen = message_id, set()
            while cur not in seen:
                seen.add(cur)
                nxt = self.st.q("SELECT id FROM messages WHERE chat=? AND parent=? ORDER BY id DESC LIMIT 1",
                                (chat_id, cur))
                if not nxt:
                    break
                cur = nxt[0][0]
            self.st.x("UPDATE chats SET leaf=? WHERE id=?", (cur, chat_id))
            klog("chat.branch", chat=chat_id[:8], shown_from=message_id, leaf=cur)
            return True
        except sqlite3.Error:
            _log("switch branch")
            return False

    def export_markdown(self, chat_id):
        """The chat as Markdown: the questions, the answers, and the files each answer used."""
        lines = ["# %s" % (self.title(chat_id) or "Chat"), ""]
        for m in self.messages(chat_id):
            if m["role"] == "user":
                lines += ["## Question", "", m["content"], ""]
            else:
                lines += ["## Answer", "", m["content"] or "(no answer text)", ""]
                names = sorted({str(s.get("name")) for s in m["sources"] if isinstance(s, dict) and s.get("name")})
                if names:
                    lines += ["Sources: " + ", ".join(names), ""]
        return "\n".join(lines).rstrip() + "\n"

    def delete(self, chat_id):
        if not chat_id:
            return
        try:
            self.st.x("DELETE FROM messages WHERE chat=?", (chat_id,))
            self.st.x("DELETE FROM chats WHERE id=?", (chat_id,))
            klog("chat.delete", chat=chat_id[:8])
        except sqlite3.Error:
            _log("delete chat")


def build_messages(system, history, sources_text, question, ctx_tokens=8192, max_tokens=420):
    """Builds the messages so the whole prompt fits the model's context.

    Every saved AI answer in the chat is sent, oldest first. Only when the prompt would overflow are the
    oldest turns dropped. Passages for the current question are shortened first if they are too long.
    Passage-only answers are never sent: they are not AI answers. Sizes are character estimates."""
    limit = max(1000, int((ctx_tokens - max_tokens - PROMPT_RESERVE_TOKENS) * CHARS_PER_TOKEN))
    if sources_text:
        room = limit - len(system) - len(question) - len("Excerpts:\n\n\n") - 1000   # keep room for some history
        if len(sources_text) > max(room, 200):
            sources_text = sources_text[:max(room, 200)].rstrip() + " …"
        current = "Excerpts:\n%s\n\n%s" % (sources_text, question)
    else:
        current = question
    room = limit - len(system) - len(current)
    kept, used = [], 0
    # An answer written from general knowledge (no passage was used) is kept in the chat but not sent back
    # to the model, together with the question it answered, so an invented answer cannot shape later ones.
    hist = list(history or [])
    skip = set()
    for i, m in enumerate(hist):
        if m.get("role") == "assistant" and m.get("kind", "answer") == "answer" and \
                ((m.get("extra") or {}).get("general") or not (m.get("extra") or {}).get("checked")):
            skip.add(i)
            if i > 0 and hist[i - 1].get("role") == "user":
                skip.add(i - 1)
    hist = [m for i, m in enumerate(hist) if i not in skip]
    for m in reversed(hist):
        if m.get("kind", "answer") != "answer":
            continue
        c = str(m.get("content") or "")
        if not c:
            continue
        if used + len(c) > room:
            break                                    # everything older than this is dropped too
        kept.append({"role": m.get("role") if m.get("role") in ("user", "assistant") else "user", "content": c})
        used += len(c)
    kept.reverse()
    klog("prompt.build", history_offered=len(history or []), history_sent=len(kept), history_chars=used,
         system_chars=len(system), current_chars=len(current), room_chars=room, limit_chars=limit)
    return [{"role": "system", "content": system}] + kept + [{"role": "user", "content": current}]
