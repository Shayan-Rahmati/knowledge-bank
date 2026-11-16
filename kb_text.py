"""Persian and multilingual text: normalising, tokens, chunks, sentences, and quality checks."""
import re
import unicodedata
from kb_config import *


DIAC = re.compile("[\u064B-\u065F\u0670\u0640]")


TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


CAMEL = re.compile(r"([a-z0-9])([A-Z])")


FA_DIG = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}


AR_DIG = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}


FA_SUF = re.compile(r"(ها|های|ان|ات|ین)$")


# Latin letters touching Persian letters with no space (common in PDF text): "docاز" -> "doc از"
SCRIPT_GAP = re.compile(r"(?<=[\u0600-\u06FF])(?=[A-Za-z])|(?<=[A-Za-z])(?=[\u0600-\u06FF])")


def norm(t):
    t = unicodedata.normalize("NFKC", t)
    t = DIAC.sub("", t).replace("ي", "ی").replace("ك", "ک")
    t = t.replace("\u200c", " ").replace("\u200d", " ")
    return SCRIPT_GAP.sub(" ", t.translate(FA_DIG).translate(AR_DIG))


def words(t):
    t = CAMEL.sub(r"\1 \2", norm(t)).lower()
    return [w for w in TOKEN.findall(t) if len(w) > 1]


def stem(w):
    if re.search("[\u0600-\u06FF]", w):
        # Strip a plural/possessive suffix only if at least 4 letters remain.
        # Without this, ایران (Iran) became ایر, and a search for ایرانی could not find it.
        if len(w) <= 4:
            return w
        s = FA_SUF.sub("", w)
        return s if len(s) >= 4 else w
    if len(w) < 4 or w.isdigit():
        return w
    s = w
    if s.endswith("ies") and len(s) > 4:
        s = s[:-3] + "y"
    elif re.search("(sses|xes|ches|shes)$", s):
        s = s[:-2]
    elif re.search("[^s]s$", s):
        s = s[:-1]
    if len(s) > 4 and re.search("(ing|ed)$", s):
        s = re.sub("(ing|ed)$", "", s)
        s = re.sub("([^aeiouls])\\1$", "\\1", s)
    if len(s) > 4 and s.endswith("e"):
        s = s[:-1]
    return s


def tokens(t):
    return [stem(w) for w in words(t)]


def query_terms(text):
    """Distinct stemmed words of a question. Which of them are filler is decided by Index.content_terms,
    from the bank's own word counts, so no word list is used."""
    return list(dict.fromkeys(stem(w) for w in words(text)))


def _merge_short(chunks, min_len=80):
    """Joins chunks shorter than min_len to a neighbour. Page headers and stray headings carry no answer on their own."""
    out, pending = [], ""
    for c in chunks:
        if len(c) < min_len:
            if out:
                out[-1] += "\n\n" + c
            else:
                pending = (pending + "\n\n" + c).strip()
            continue
        if pending:
            c, pending = pending + "\n\n" + c, ""
        out.append(c)
    if pending:
        if out:
            out[-1] += "\n\n" + pending
        else:
            out.append(pending)
    return out


def chunk_text(t, size=1000):
    out, buf = [], ""
    for p in re.split(r"\n\s*\n", t):
        if not p:
            continue
        if buf and len(buf) + len(p) > size:
            out.append(buf.strip())
            buf = ""
        buf += p + "\n\n"
        while len(buf) > 2 * size:
            c = max(buf.rfind(". ", 0, size), buf.rfind("\n", 0, size))
            if c < size * 0.5:
                c = buf.rfind(" ", 0, size)
            if c < 1:
                c = size
            out.append(buf[: c + 1].strip())
            buf = buf[c + 1:]
    if buf.strip():
        out.append(buf.strip())
    return _merge_short([c for c in out if c])


SENT_SPLIT = re.compile(r"(?<=[.!?؟۔…])\s+(?=[^\W\d_]|\d|[\"(«])", re.UNICODE)


def sentences(t):
    lines, code = [], False
    for l in t.split("\n"):
        if len(l) > 3 and l.lstrip().startswith("```"):
            code = not code
            continue
        if code:
            continue
        tr = l.strip()
        if not tr or tr[0] in "#|":
            continue
        tr = re.sub(r"^([-*+]|\d+[.)])\s+", "", tr)
        tr = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", tr)
        tr = tr.replace("`", "")
        # emphasis only: a * or _ inside a formula (Cand1*min, p_norm) is kept
        tr = re.sub(r"(?<![\w*])\*\*?(?=\S)(.+?)(?<=\S)\*\*?(?![\w*])", r"\1", tr)
        tr = re.sub(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"\1", tr)
        lines.append(tr)
    joined = " ".join(lines)
    return [s.strip() for s in SENT_SPLIT.split(joined) if 25 <= len(s.strip()) < 800]


COMMON = set("ابپتثجچحخدذرزژسشصضطعغفقکگلمنوهیآئءؤيكةۀ")


TOKEN_AR = re.compile(r"[\u0600-\u06FF\uFB50-\uFEFF]+")


def text_quality(t):
    """Share of Persian words that look like real words. A word is real if it has no run of three identical letters, is at most 18 letters long,
    uses only common Persian letters, and (if it has 4 or more letters) contains a vowel-bearing letter (ا و ی ه).
    Broken PDF font maps fail this test badly, so the score drops far below normal text."""
    words = [w.replace("\u200c", "") for w in TOKEN_AR.findall(t)]
    words = [w for w in words if len(w) >= 2]
    if sum(len(w) for w in words) < 30:
        return 1.0
    good = 0
    for w in words:
        if re.search(r"(.)\1\1", w) or len(w) > 18:
            continue
        if sum(1 for ch in w if ch not in COMMON) / len(w) > 0.15:
            continue
        if len(w) >= 4 and not any(ch in "اوىیه" for ch in w):
            continue
        good += 1
    return good / len(words)


QUALITY_MIN = 0.6


def sentences_plain(text):
    """Splits an answer into sentences, so each one can be linked to its passage."""
    parts = re.split(r"(?<=[.!?؟۔])\s+", re.sub(r"\s+", " ", text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 2]


def answer_language(text):
    """'fa' or 'en' from the script of the letters: Persian and Arabic script against Latin letters.
    A tie goes to Persian, since a Persian question can contain English terms. No word list is used."""
    fa = len(re.findall(r"[\u0600-\u06FF\uFB50-\uFEFF]", text or ""))
    en = len(re.findall(r"[A-Za-z]", text or ""))
    if fa == 0 and en == 0:
        return "en"
    return "fa" if fa >= en else "en"


def edit_distance(a, b, limit=2):
    """Levenshtein distance. Stops early once it passes limit."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def word_root(w):
    """A shorter form that groups related words: ایرانی to ایران, سیاسی to سیاس."""
    if len(w) >= 5 and w[-1] in "یی":
        return w[:-1]
    return w[:-1] if len(w) >= 6 and w[-1] in "ه" else w
