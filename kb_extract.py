"""Reads every supported document type, with fallbacks for PDFs."""
import os
import re
import json
import zipfile
import unicodedata
import zlib
import subprocess
import shutil
import urllib.request, urllib.error, urllib.parse
from html.parser import HTMLParser
from xml.etree import ElementTree as ET
from kb_text import *

def decode_bytes(b):
    if b[:3] == b"\xef\xbb\xbf":
        return b[3:].decode("utf-8", "replace")
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16", "replace")
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in ("cp1256", "cp1252", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("utf-8", "replace")


class H2T(HTMLParser):
    BLOCK = {"p", "div", "pre", "blockquote", "ul", "ol", "table", "section", "article", "header", "footer", "main"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.o, self.skip, self.pre = [], 0, 0

    def handle_starttag(self, tag, a):
        if tag in ("script", "style", "noscript", "svg", "head"):
            self.skip += 1
        elif tag == "pre":
            self.pre += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self.o.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in ("li", "br", "tr"):
            self.o.append("\n")
        elif tag in self.BLOCK:
            self.o.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
        elif re.fullmatch(r"h[1-6]", tag) or tag in self.BLOCK:
            self.o.append("\n\n")
        elif tag in ("td", "th"):
            self.o.append("\t")

    def handle_data(self, d):
        if self.skip:
            return
        self.o.append(d if self.pre else re.sub(r"\s+", " ", d))


def html_to_text(h):
    p = H2T()
    try:
        p.feed(h)
    except Exception:
        pass
    t = "".join(p.o)
    t = re.sub(r" *\n *", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def clean_md(t):
    def fm(m):
        mm = re.search(r"^title:\s*(.+)$", m.group(1), re.M)
        return "# " + mm.group(1).strip() + "\n\n" if mm else ""
    t = re.sub(r"\A---\r?\n(.*?)\r?\n---\r?\n", fm, t, flags=re.S)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"^(import|export) .* from .*$", "", t, flags=re.M)
    return t


def xml_text(xml_bytes, para_tags, text_tags, tab_tags=(), br_tags=()):
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""

    def local(e):
        return e.tag.rsplit("}", 1)[-1]

    def walk(e, cur):
        n = local(e)
        if n in para_tags:
            cur = []
            for c in e.iter():
                ln = local(c)
                if ln in text_tags and c.text:
                    cur.append(c.text)
                elif ln in tab_tags:
                    cur.append("\t")
                elif ln in br_tags:
                    cur.append("\n")
            s = "".join(cur).strip()
            if s:
                out.append(s)
            return
        for c in e:
            walk(c, cur)
    walk(root, [])
    return "\n\n".join(out)


def docx_text(z):
    parts = []
    names = [n for n in z.namelist() if n.startswith("word/") and n.endswith(".xml")]
    main = "word/document.xml"
    if main in names:
        parts.append(xml_text(z.read(main), {"p"}, {"t"}, {"tab"}, {"br"}))
    for n in names:
        if re.match(r"word/(footnotes|endnotes)\.xml", n):
            parts.append(xml_text(z.read(n), {"p"}, {"t"}))
    return "\n\n".join(p for p in parts if p)


def odf_text(z):
    if "content.xml" not in z.namelist():
        return ""
    return xml_text(z.read("content.xml"), {"p", "h"}, {"p", "h", "span"}, set(), {"line-break"}) or \
        flat_xml(z.read("content.xml"))


def flat_xml(b):
    try:
        root = ET.fromstring(b)
    except ET.ParseError:
        return ""
    out = []
    for e in root.iter():
        n = e.tag.rsplit("}", 1)[-1]
        if n in ("p", "h"):
            s = "".join(e.itertext()).strip()
            if s:
                out.append(s)
    return "\n\n".join(out)


def pptx_text(z):
    slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                    key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
    out = []
    for i, n in enumerate(slides, 1):
        t = xml_text(z.read(n), {"p"}, {"t"})
        if t:
            out.append("## Slide %d\n\n%s" % (i, t))
    return "\n\n".join(out)


def xlsx_text(z):
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root:
            ss.append("".join(t.text or "" for t in si.iter() if t.tag.endswith("}t")))
    out = []
    sheets = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    for sn in sheets:
        rows = []
        for row in ET.fromstring(z.read(sn)).iter():
            if not row.tag.endswith("}row"):
                continue
            cells = []
            for c in row:
                v = None
                for ch in c:
                    if ch.tag.endswith("}v"):
                        v = ch.text
                    elif ch.tag.endswith("}is"):
                        v = "".join(ch.itertext())
                if v is None:
                    continue
                if c.get("t") == "s":
                    try:
                        v = ss[int(v)]
                    except Exception:
                        pass
                cells.append(v)
            if cells:
                rows.append("\t".join(cells))
        if rows:
            out.append("\n".join(rows))
    return "\n\n".join(out)


def epub_text(z):
    names = z.namelist()
    order = []
    try:
        cont = ET.fromstring(z.read("META-INF/container.xml"))
        opf = next(e.get("full-path") for e in cont.iter() if e.tag.endswith("rootfile"))
        base = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
        o = ET.fromstring(z.read(opf))
        man = {e.get("id"): e.get("href") for e in o.iter() if e.tag.endswith("}item")}
        for e in o.iter():
            if e.tag.endswith("}itemref") and man.get(e.get("idref")):
                order.append(base + urllib.parse.unquote(man[e.get("idref")]))
    except Exception:
        pass
    if not order:
        order = sorted(n for n in names if re.search(r"\.(x?html?)$", n, re.I))
    out = []
    for n in order:
        if n in names:
            t = html_to_text(decode_bytes(z.read(n)))
            if t:
                out.append(t)
    return "\n\n".join(out)


def rtf_text(s):
    s = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("cp1256", "replace"), s)
    s = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), s)
    s = re.sub(r"\\par[d]?", "\n", s)
    s = re.sub(r"\{\\\*[^{}]*\}", "", s)
    s = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", s)
    return re.sub(r"[{}]", "", s)


def pdf_builtin(data):
    """A minimal PDF reader, used when no PDF library is installed. Handles simple text PDFs only."""
    objs = {}
    for m in re.finditer(rb"(\d+)\s+(\d+)\s+obj(.*?)endobj", data, re.S):
        objs[int(m.group(1))] = m.group(3)

    def stream_of(body):
        m = re.search(rb"stream\r?\n(.*?)\r?\nendstream", body, re.S)
        if not m:
            return b""
        raw = m.group(1)
        if b"FlateDecode" in body[: m.start()]:
            try:
                return zlib.decompress(raw)
            except Exception:
                try:
                    return zlib.decompressobj().decompress(raw)
                except Exception:
                    return b""
        return raw

    cmaps = []
    for body in objs.values():
        s = stream_of(body)
        if b"beginbfchar" in s or b"beginbfrange" in s:
            mp = {}
            for blk in re.findall(rb"beginbfchar(.*?)endbfchar", s, re.S):
                for a, b in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
                    try:
                        mp[int(a, 16)] = bytes.fromhex(b.decode()).decode("utf-16-be", "ignore")
                    except Exception:
                        pass
            for blk in re.findall(rb"beginbfrange(.*?)endbfrange", s, re.S):
                for a, b, c in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
                    try:
                        lo, hi, st = int(a, 16), int(b, 16), int(c, 16)
                        for k in range(lo, min(hi, lo + 4096) + 1):
                            mp[k] = chr(st + k - lo)
                    except Exception:
                        pass
            cmaps.append(mp)
    cm = {}
    for mp in cmaps:
        cm.update(mp)

    def dec_hex(h):
        h = re.sub(rb"\s+", b"", h)
        if len(h) % 2:
            h += b"0"
        raw = bytes.fromhex(h.decode())
        if cm:
            two = max(cm) > 255
            if two and len(raw) % 2 == 0:
                return "".join(cm.get(int.from_bytes(raw[i:i + 2], "big"), "") for i in range(0, len(raw), 2))
            return "".join(cm.get(b, chr(b)) for b in raw)
        return raw.decode("latin-1")

    def dec_lit(s):
        s = re.sub(rb"\\([nrtbf()\\])", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(m.group(1), m.group(1)), s)
        s = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 255]), s)
        return "".join(cm.get(b, chr(b)) for b in s) if cm else s.decode("latin-1")

    pages = []
    for body in objs.values():
        if b"/Type/Page" in body.replace(b" ", b"") and b"/Type/Pages" not in body.replace(b" ", b""):
            pages.append(body)
    texts = []
    for body in objs.values():
        s = stream_of(body)
        if b"BT" not in s or b"ET" not in s:
            continue
        out = []
        for bt in re.findall(rb"BT(.*?)ET", s, re.S):
            for m in re.finditer(rb"\[(.*?)\]\s*TJ|<([0-9A-Fa-f\s]+)>\s*Tj|\((?:\\.|[^\\)])*\)\s*Tj|T\*|(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+T[dD]", bt, re.S):
                if m.group(1) is not None:
                    seg = ""
                    for p in re.finditer(rb"<([0-9A-Fa-f\s]+)>|\(((?:\\.|[^\\)])*)\)|(-?\d+\.?\d*)", m.group(1)):
                        if p.group(1) is not None:
                            seg += dec_hex(p.group(1))
                        elif p.group(2) is not None:
                            seg += dec_lit(p.group(2))
                        elif p.group(3) is not None and float(p.group(3)) < -200:
                            seg += " "
                    out.append(seg)
                elif m.group(2) is not None:
                    out.append(dec_hex(m.group(2)))
                elif m.group(0).endswith(b"Tj"):
                    out.append(dec_lit(m.group(0)[1:m.group(0).rfind(b")")]))
                else:
                    out.append("\n")
        t = "".join(out).strip()
        if t:
            texts.append(t)
    return "\n\n".join(texts)


def pdf_pdftotext(path):
    """pdftotext (Poppler) handles many PDFs that the Python readers garble, if it is installed."""
    exe = shutil.which("pdftotext")
    if not exe:
        raise ImportError("pdftotext not installed")
    r = subprocess.run([exe, "-enc", "UTF-8", "-layout", path, "-"], capture_output=True, timeout=180, **NOWIN)
    return r.stdout.decode("utf-8", "replace")


def pdf_text(path):
    """Returns (text, reader name). Tries the readers from best to worst; the name is shown in the viewer."""
    best = None
    for fn in (pdf_pypdf, pdf_pdftotext, pdf_pdfminer, pdf_fitz):
        try:
            t = fn(path)
        except Exception:            # includes a reader that is not installed
            continue
        if not t or len(t.strip()) <= 20:
            continue
        q = text_quality(t)
        if best is None or q > best[0]:
            best = (q, t, fn.__name__.replace("_pdf_", ""))
        if q >= 0.95:                # clean enough: the slower readers are not needed
            break
    if best and best[0] >= QUALITY_MIN:
        return best[1], best[2]
    with open(path, "rb") as f:
        return pdf_builtin(f.read()), "built-in (install pypdf for better spacing)"


def pdf_pypdf(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    r = PdfReader(path)
    if getattr(r, "is_encrypted", False):
        try:
            r.decrypt("")
        except Exception:
            return ""
    out = []
    for p in r.pages:
        try:
            out.append((p.extract_text() or "").strip())
        except Exception:
            out.append("")
    return "\n\n".join(x for x in out if x)


def pdf_pdfminer(path):
    from pdfminer.high_level import extract_text
    return extract_text(path)


def pdf_fitz(path):
    import fitz
    d = fitz.open(path)
    return "\n\n".join(p.get_text() for p in d)


def tidy(t):
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").replace("\u00ad", "")
    t = re.sub(r"[ \t\f\v]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def extract_file(path):
    """Returns (text, note). The text is the file's own text, structured block by block, with no OCR and
    no change to the characters. Search normalises its own copy (kb_text.norm)."""
    text, note = extract_raw(path)
    is_pdf = path.lower().endswith(".pdf")
    blocks = extract_blocks(path, text if is_pdf else None)
    if blocks:
        return blocks_text(blocks), note
    return text, note


def extract_raw(path):
    ext = path.rsplit(".", 1)[-1].lower() if "." in os.path.basename(path) else ""
    try:
        if ext == "pdf":
            raw, reader = pdf_text(path)
            t = tidy(raw)
            if text_quality(t) < QUALITY_MIN:
                return "", ("unreadable: the PDF's font encoding is broken; it needs OCR or a different export")
            return t, "reader: " + reader
        if ext in ("docx", "pptx", "xlsx", "odt", "odp", "ods", "epub"):
            with zipfile.ZipFile(path) as z:
                fn = {"docx": docx_text, "pptx": pptx_text, "xlsx": xlsx_text, "odt": odf_text, "odp": odf_text,
                      "ods": odf_text, "epub": epub_text}[ext]
                return tidy(fn(z)), ""
        with open(path, "rb") as f:
            raw = f.read(60_000_000)
        s = decode_bytes(raw)
        if ext in ("html", "htm", "xhtml"):
            s = html_to_text(s)
        elif ext == "rtf":
            s = rtf_text(s)
        elif ext in ("md", "mdx"):
            s = clean_md(s)
        elif ext == "json":
            try:
                s = json.dumps(json.loads(s), ensure_ascii=False, indent=1)
            except Exception:
                pass
        return tidy(s), ""
    except Exception as e:
        return "", "%s: %s" % (type(e).__name__, e)


# ---------------------------------------------------------------------------
# Structured extraction: headings, paragraphs, list items, tables and code, each with its own direction.
# The viewer shows these blocks; the index reads the same text. Characters are kept as the file has them
# (no language-specific rewriting here: search normalises its own copy in kb_text.norm).

def text_dir(s):
    """'rtl' or 'ltr' from the first strong letter, the way bidirectional text is read. None if there is none."""
    for ch in s or "":
        if ch.isdigit():                      # digits are weak: they do not decide the direction
            continue
        o = ord(ch)
        if 0x590 <= o <= 0x8FF or 0xFB1D <= o <= 0xFEFF:
            return "rtl"
        if ch.isalpha():
            return "ltr"
    return None


def blk(kind, text="", rows=None, level=0):
    b = {"kind": kind, "text": text, "level": level}
    if rows is not None:
        b["rows"] = rows
    return b


def _local(e):
    return e.tag.rsplit("}", 1)[-1]


def _attr_val(e, name="val"):
    for k, v in e.attrib.items():
        if k.endswith("}" + name) or k == name:
            return v
    return ""


def _para_text(p):
    out = []
    for e in p.iter():
        n = _local(e)
        if n == "t" and e.text:
            out.append(e.text)
        elif n == "tab":
            out.append("\t")
        elif n == "br":
            out.append("\n")
    return "".join(out)


def docx_blocks(z):
    root = ET.fromstring(z.read("word/document.xml"))
    body = next((e for e in root.iter() if _local(e) == "body"), root)
    out = []
    for el in body:
        n = _local(el)
        if n == "p":
            style, numbered = "", False
            for ppr in el:
                if _local(ppr) == "pPr":
                    for x in ppr:
                        if _local(x) == "pStyle":
                            style = _attr_val(x)
                        elif _local(x) == "numPr":
                            numbered = True
            text = _para_text(el).strip()
            if not text:
                continue
            m = re.search(r"(?i)heading\s*(\d)", style)
            if m:
                out.append(blk("h", text, level=min(int(m.group(1)), 4)))
            elif re.search(r"(?i)^title$", style):
                out.append(blk("h", text, level=1))
            elif numbered:
                out.append(blk("li", text))
            else:
                out.append(blk("p", text))
        elif n == "tbl":
            rows = []
            for tr in el:
                if _local(tr) != "tr":
                    continue
                cells = []
                for tc in tr:
                    if _local(tc) == "tc":
                        cells.append("\n".join(x for x in (_para_text(p).strip() for p in tc if _local(p) == "p") if x))
                rows.append(cells)
            if rows:
                out.append(blk("table", rows=rows))
    return out


def pptx_blocks(z):
    slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                    key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
    out = []
    for i, name in enumerate(slides, 1):
        root = ET.fromstring(z.read(name))
        title, paras = None, []
        for sp in root.iter():
            if _local(sp) != "sp":
                continue
            is_title = any(_local(x) == "ph" and x.get("type") in ("title", "ctrTitle") for x in sp.iter())
            ps = ["".join(t.text or "" for t in p.iter() if _local(t) == "t").strip()
                  for p in sp.iter() if _local(p) == "p"]
            ps = [x for x in ps if x]
            if is_title and ps and title is None:
                title = " ".join(ps)
            else:
                paras += ps
        out.append(blk("h", title or "Slide %d" % i, level=2))
        out += [blk("p", x) for x in paras]
    return out


def xlsx_blocks(z):
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root:
            ss.append("".join(t.text or "" for t in si.iter() if _local(t) == "t"))
    out = []
    sheets = sorted((n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
                    key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)))
    for i, sn in enumerate(sheets, 1):
        rows = []
        for row in ET.fromstring(z.read(sn)).iter():
            if _local(row) != "row":
                continue
            cells = []
            for c in row:
                v = None
                for ch in c:
                    if _local(ch) == "v":
                        v = ch.text
                    elif _local(ch) == "is":
                        v = "".join(ch.itertext())
                if v is None:
                    continue
                if c.get("t") == "s":
                    try:
                        v = ss[int(v)]
                    except (ValueError, IndexError):
                        pass
                cells.append(v)
            if cells:
                rows.append(cells)
        if rows:
            out.append(blk("h", "Sheet %d" % i, level=2))
            out.append(blk("table", rows=rows))
    return out


class HtmlBlocks(HTMLParser):
    """Turns HTML into blocks: headings, paragraphs, list items, preformatted text and tables."""
    SKIP = {"script", "style", "noscript", "svg", "head"}
    PARA = {"p", "div", "blockquote", "section", "article", "header", "footer", "dd", "dt", "figure", "figcaption"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.cur, self.table, self.row, self.cell = [], None, None, None, None
        self.skip, self.pre = 0, 0

    def _buf(self):
        """Where text goes right now: the open table cell, the open block, or a new paragraph."""
        if self.cell is not None:
            return self.cell
        if self.cur is None:
            self.cur = ["p", []]
        return self.cur[1]

    def _flush(self):
        if self.cur is not None:
            kind, parts = self.cur[0], self.cur[1]
            text = "".join(parts)
            text = text if kind == "pre" else re.sub(r"[ \t\r\f\v]+", " ", text)
            text = text.strip("\n") if kind == "pre" else text.strip()
            if text:
                self.out.append(blk(kind, text, level=self.cur[2] if len(self.cur) > 2 else 0))
        self.cur = None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if self.cell is not None:                 # inside a table cell: only line breaks matter
            if tag in ("br", "p", "div", "li"):
                self.cell.append("\n")
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.cur = ["h", [], min(int(tag[1]), 4)]
        elif tag in self.PARA:
            self._flush()
            self.cur = ["p", []]
        elif tag == "li":
            self._flush()
            self.cur = ["li", []]
        elif tag == "pre":
            self._flush()
            self.cur = ["pre", []]
            self.pre += 1
        elif tag == "table":
            self._flush()
            self.table, self.row = [], None
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.table is not None:
            self.cell = []
        elif tag == "br":
            self._buf().append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if self.cell is not None:
            if tag in ("td", "th"):
                if self.row is not None:
                    self.row.append("".join(self.cell).strip())
                self.cell = None
            return
        if re.fullmatch(r"h[1-6]", tag) or tag in self.PARA or tag in ("li", "pre"):
            self._flush()
            if tag == "pre":
                self.pre = max(0, self.pre - 1)
        elif tag == "tr" and self.table is not None and self.row is not None:
            if any(c.strip() for c in self.row):
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            if self.table:
                self.out.append(blk("table", rows=self.table))
            self.table = None

    def handle_data(self, d):
        if self.skip:
            return
        if self.pre or (self.cur and self.cur[0] == "pre"):
            self._buf().append(d)
        else:
            s = re.sub(r"\s+", " ", d)
            if self.cell is None and self.cur is None and not s.strip():
                return
            self._buf().append(s)

    def blocks(self):
        self._flush()
        return self.out


def html_blocks(html):
    p = HtmlBlocks()
    p.feed(html)                 # errors surface to extract_blocks, which reports them as "no text"
    p.close()
    return p.blocks()


def md_blocks(text):
    lines = clean_md(text).replace("\r\n", "\n").split("\n")
    out, para, code, table = [], [], None, []

    def flush_para():
        if para:
            out.append(blk("p", "\n".join(para)))
            para.clear()

    def flush_table():
        if table:
            out.append(blk("table", rows=list(table)))
            table.clear()

    for line in lines:
        s = line.strip()
        if s.startswith("```"):
            flush_para(); flush_table()
            if code is None:
                code = []
            else:
                out.append(blk("pre", "\n".join(code)))
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        if s.startswith("|") and s.count("|") >= 2:
            flush_para()
            if re.fullmatch(r"\|?[\s:|-]+\|?", s) and "-" in s:
                continue                       # the |---|---| row
            table.append([c.strip() for c in s.strip("|").split("|")])
            continue
        flush_table()
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush_para()
            out.append(blk("h", m.group(2).strip().rstrip("#").strip(), level=min(len(m.group(1)), 4)))
        elif re.match(r"^([-*+]|\d+[.)])\s+", s):
            flush_para()
            out.append(blk("li", re.sub(r"^([-*+]|\d+[.)])\s+", "", s)))
        elif not s:
            flush_para()
        else:
            para.append(s)
    flush_para(); flush_table()
    if code:
        out.append(blk("pre", "\n".join(code)))
    return out


def text_blocks(text):
    """Plain text: paragraphs are separated by blank lines; line breaks inside a paragraph are kept."""
    out = []
    for para in re.split(r"\n\s*\n", text or ""):
        lines = [l.rstrip() for l in para.split("\n")]
        body = "\n".join(l for l in lines if l.strip())
        if body.strip():
            out.append(blk("p", body.strip()))
    return out


def csv_blocks(text, delimiter=","):
    import csv
    import io
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    return [blk("table", rows=rows)] if rows else []


def epub_blocks(z):
    names = z.namelist()
    order = []
    try:
        cont = ET.fromstring(z.read("META-INF/container.xml"))
        opf = next(e.get("full-path") for e in cont.iter() if _local(e) == "rootfile")
        base = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
        o = ET.fromstring(z.read(opf))
        man = {e.get("id"): e.get("href") for e in o.iter() if _local(e) == "item"}
        for e in o.iter():
            if _local(e) == "itemref" and man.get(e.get("idref")):
                order.append(base + urllib.parse.unquote(man[e.get("idref")]))
    except Exception:
        pass
    if not order:
        order = sorted(n for n in names if re.search(r"\.(x?html?)$", n, re.I))
    out = []
    for n in order:
        if n in names:
            out += html_blocks(decode_bytes(z.read(n)))
    return out


def odf_blocks(z):
    if "content.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("content.xml"))
    out = []
    for e in root.iter():
        n = _local(e)
        if n in ("p", "h"):
            s = "".join(e.itertext()).strip()
            if s:
                out.append(blk("h" if n == "h" else "p", s, level=2 if n == "h" else 0))
    return out


def extract_blocks(path, pdf_text_value=None):
    """Structured text of a file, as a list of blocks. Empty if nothing could be read."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in os.path.basename(path) else ""
    try:
        if ext == "pdf":
            raw = pdf_text_value if pdf_text_value is not None else extract_raw(path)[0]
            return text_blocks(raw)
        if ext in ("docx", "pptx", "xlsx", "odt", "odp", "ods", "epub"):
            with zipfile.ZipFile(path) as z:
                fn = {"docx": docx_blocks, "pptx": pptx_blocks, "xlsx": xlsx_blocks, "odt": odf_blocks,
                      "odp": odf_blocks, "ods": odf_blocks, "epub": epub_blocks}[ext]
                return fn(z)
        with open(path, "rb") as f:
            raw = f.read(60_000_000)
        s = decode_bytes(raw)
        if ext in ("html", "htm", "xhtml"):
            return html_blocks(s)
        if ext in ("md", "mdx"):
            return md_blocks(s)
        if ext == "rtf":
            return text_blocks(rtf_text(s))
        if ext == "csv":
            return csv_blocks(s, ",")
        if ext == "tsv":
            return csv_blocks(s, "\t")
        if ext == "json":
            try:
                return [blk("pre", json.dumps(json.loads(s), ensure_ascii=False, indent=2))]
            except ValueError:
                return text_blocks(s)
        return text_blocks(tidy(s))
    except Exception:
        return []


def blocks_text(blocks):
    """Plain text for the index: one paragraph per block, table rows on their own lines."""
    parts = []
    for b in blocks:
        if b.get("rows") is not None:
            parts.append("\n".join("\t".join(c for c in row) for row in b["rows"]))
        elif b["text"]:
            parts.append(b["text"])
    return "\n\n".join(p for p in parts if p)
