"""Turns a model answer into clean HTML for the chat bubble.

The model writes markdown (headings, bullets, **bold**, > quotes). This module shows that as real formatting
instead of raw symbols, keeps each paragraph or bullet whole, and puts a citation after the block it supports.
It only changes how an answer looks. The text itself and the citation links are not changed."""
import html
import re

_HEAD = re.compile(r"^#{1,6}\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_BULLET = re.compile(r"^([-*+•]|\d+[.)]|[۰-۹]+[.)])\s+(.*)$")
_RULE = re.compile(r"^[-*_]{3,}$")


def _bdir(s):
    """Direction of one block: set by its first letter (Persian/Arabic script is rtl, Latin is ltr). Each block gets its own,
    so a Persian paragraph with an English word, or an English paragraph, is laid out correctly inside a Persian answer."""
    for ch in s or "":
        o = ord(ch)
        if 0x590 <= o <= 0x8FF or 0xFB50 <= o <= 0xFEFF:
            return "rtl"
        if ch.isalpha():
            return "ltr"
    return "rtl"


def _inline(s):
    """Escapes the text, then turns the markdown emphasis and code marks into HTML. Stray markers are removed."""
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)               # links keep their text
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", r"<b>\1</b>", s)
    return s.replace("**", "").replace("`", "").strip()


def _norm(s):
    """Lower-case letters and digits only, for matching a sentence to the block that contains it."""
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\[\d+\]", "", s)
    return re.sub(r"[\W_]+", "", s).lower()


def blocks(text):
    """Splits an answer into blocks: paragraphs (wrapped lines joined), headings, bullets, quotes."""
    out, para, code = [], [], False

    def flush():
        if para:
            t = _inline(" ".join(para))
            out.append({"kind": "p", "text": t, "norm": _norm(t), "mark": ""})
            para.clear()

    for raw in (text or "").split("\n"):
        s = raw.strip()
        if s.startswith("```"):
            flush()
            code = not code
            continue
        if code:
            if s:
                out.append({"kind": "p", "text": html.escape(s, quote=False), "norm": _norm(s), "mark": ""})
            continue
        if not s or _RULE.match(s):
            flush()
            out.append({"kind": "gap", "text": "", "norm": "", "mark": ""})
            continue
        m = _HEAD.match(s)
        if m:
            flush()
            t = _inline(m.group(1))
            out.append({"kind": "h", "text": t, "norm": _norm(t), "mark": ""})
            continue
        m = _QUOTE.match(s)
        if m:
            flush()
            t = _inline(m.group(1))
            out.append({"kind": "q", "text": t, "norm": _norm(t), "mark": ""})
            continue
        m = _BULLET.match(s)
        if m:
            flush()
            marker = m.group(1)
            marker = "•" if marker[0] in "-*+•" else marker
            t = _inline(m.group(2))
            out.append({"kind": "li", "text": t, "norm": _norm(t), "mark": marker})
            continue
        para.append(s)
    flush()
    return out


def answer_html(text, spans, badge, c):
    """Renders the answer. `spans` are the cited sentences from the core (each has sent, path, n, score).
    `badge(k, span)` returns the citation link for span number k; only linked spans get one."""
    bl = blocks(text)
    if not bl:
        return ""
    # Find the block that holds each linked sentence. Sentences are matched by their first words.
    marks = {}
    for k, sp in enumerate(spans or []):
        if sp.get("path") is None:
            continue
        key = _norm(sp.get("sent", ""))[:40]
        if len(key) < 12:
            continue
        for bi, b in enumerate(bl):
            if b["norm"] and key in b["norm"]:
                marks.setdefault(bi, []).append((k, sp))
                break
    out = []
    for bi, b in enumerate(bl):
        if b["kind"] == "gap":
            continue
        extra, seen = "", set()
        for k, sp in marks.get(bi, []):
            if sp.get("n") in seen:
                continue
            seen.add(sp.get("n"))
            extra += badge(k, sp)
        if b["kind"] == "h":
            d = _bdir(b["text"])
            out.append('<div dir="%s" align="%s" style="margin:10px 0 4px 0"><b>%s</b>%s</div>' % (d, "right" if d == "rtl" else "left", b["text"], extra))
        elif b["kind"] == "li":
            d = _bdir(b["text"])
            out.append('<div dir="%s" align="%s" style="margin:3px 0"><span dir="%s">%s&nbsp;%s</span>%s</div>' % (
                d, "right" if d == "rtl" else "left", d, html.escape(b["mark"], quote=False), b["text"], extra))
        elif b["kind"] == "q":
            d = _bdir(b["text"])
            out.append('<div dir="%s" align="%s" style="margin:6px 0;color:%s"><i>%s</i>%s</div>' % (
                d, "right" if d == "rtl" else "left", c["mute"], b["text"], extra))
        else:
            d = _bdir(b["text"])
            out.append('<div dir="%s" align="%s" style="margin:6px 0">%s%s</div>' % (d, "right" if d == "rtl" else "left", b["text"], extra))
    return "".join(out)
