"""The desktop window: layout, themes, the document list, and the Downloads window."""
import os
import sys
import re
import time
import threading
import html
import subprocess
import traceback
from kb_core import *
from kb_answer import answer_html

ICONS = {
    'search': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path>'),
    'sparkle': ({'fill': 'currentColor', 'stroke': 'none'}, '<path d="M12 2.5 13.6 9l6.4 1.6-6.4 1.6L12 18.6l-1.6-6.4L4 10.6 10.4 9z"></path>'),
    'folder': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>'),
    'folder-plus': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><path d="M12 11v6M9 14h6"></path>'),
    'refresh': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M21 12a9 9 0 1 1-3-6.7"></path><path d="M21 3v6h-6"></path>'),
    'chevron-down': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="m6 9 6 6 6-6"></path>'),
    'chevron-right': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="m9 6 6 6-6 6"></path>'),
    'chevron-left': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="m15 6-6 6 6 6"></path>'),
    'menu': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round'}, '<path d="M4 7h16M4 12h16M4 17h16"></path>'),
    'pause': ({'fill': 'currentColor', 'stroke': 'none'}, '<rect x="6" y="5" width="4" height="14" rx="1"></rect><rect x="14" y="5" width="4" height="14" rx="1"></rect>'),
    'x': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M6 6l12 12M18 6 6 18"></path>'),
    'check': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '3', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="m5 13 4 4L19 7"></path>'),
    'download': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M12 3v12"></path><path d="m7 10 5 5 5-5"></path><path d="M5 21h14"></path>'),
    'copy': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<rect x="8" y="8" width="12" height="12" rx="2"></rect><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"></path>'),
    'trash': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M4 7h16M9 7V4h6v3M6 7v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7M10 11v6M14 11v6"></path>'),
    'book': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M4 5a2 2 0 0 1 2-2h6v18H6a2 2 0 0 1-2-2zM20 5a2 2 0 0 0-2-2h-6v18h6a2 2 0 0 0 2-2z"></path>'),
    'sliders': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M4 6h8M16 6h4M4 12h16M4 18h4M12 18h8"></path><circle cx="14" cy="6" r="2"></circle><circle cx="10" cy="18" r="2"></circle>'),
    'file': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><path d="M14 3v6h6"></path>'),
    'docs': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M7 3h7l4 4v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"></path><path d="M14 3v4h4M9 12h6M9 16h6M9 8h2"></path>'),
    'shield': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M12 2 4 5v7c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V5z"></path><path d="m9 12 2 2 4-4"></path>'),
    'github': ({'fill': 'currentColor', 'stroke': 'none'}, '<path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z"></path>'),
    'instagram': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<rect x="3" y="3" width="18" height="18" rx="5"></rect><circle cx="12" cy="12" r="4"></circle><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"></circle>'),
    'telegram': ({'fill': 'currentColor', 'stroke': 'none'}, '<path d="M21.5 3.5 2.9 10.6c-1.3.5-1.3 1.2-.2 1.6l4.8 1.5 1.8 5.6c.2.7.4 1 .9 1 .6 0 .8-.3 1.1-.6l2.7-2.6 5.6 4.1c1 .6 1.8.3 2-.9L22.8 5c.4-1.5-.5-2.2-1.3-1.5zM9.7 14.3l-.3 3.7 1.5-1.4 5.9-5.4c.3-.2.5-.3.3-.5-.2-.2-.5 0-.8.1l-7.6 3.5z"></path>'),
    'globe': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<circle cx="12" cy="12" r="9"></circle><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"></path>'),
    'linkedin': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<rect x="3" y="3" width="18" height="18" rx="3"></rect><path d="M8 11v5"></path><path d="M8 8v.01"></path><path d="M12 16v-5"></path><path d="M12 11a2.5 2.5 0 0 1 5 0v5"></path>'),
    'mail': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="m3 7 9 6 9-6"></path>'),
    'sun': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"></path>'),
    'moon': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M21 14.5A8.5 8.5 0 1 1 9.5 3a7 7 0 0 0 11.5 11.5z"></path>'),
    'monitor': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<rect x="3" y="4" width="18" height="13" rx="2"></rect><path d="M8 21h8M12 17v4"></path>'),
    'logo': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H18v15H6.5A1.5 1.5 0 0 0 5 19.5z"></path><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H18v-3"></path><path d="m12.5 7 .9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z" fill="currentColor" stroke="none"></path>'),
    'db': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<ellipse cx="12" cy="5.5" rx="8" ry="3"></ellipse><path d="M4 5.5v6.5c0 1.7 3.6 3 8 3s8-1.3 8-3V5.5M4 12v6.5c0 1.7 3.6 3 8 3s8-1.3 8-3V12"></path>'),
    'layers': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="m12 3 9 5-9 5-9-5z"></path><path d="m3 13 9 5 9-5"></path>'),
    'file-plus': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><path d="M14 3v6h6M12 12v6M9 15h6"></path>'),
    'send': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2.2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M12 19V5"></path><path d="m5 12 7-7 7 7"></path>'),
    'stop': ({'fill': 'currentColor', 'stroke': 'none'}, '<rect x="6" y="6" width="12" height="12" rx="2.5"></rect>'),
    'hash': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M5 9h14M5 15h14M10 4 8 20M16 4l-2 16"></path>'),
    'pencil': ({'fill': 'none', 'stroke': 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}, '<path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path>'),
}


ERR_FA = {
    "The model file is missing (Downloads).": "فایل مدل پیدا نشد (بخش دانلودها را ببینید).",
    "The model file is damaged or incomplete. Delete it in Downloads and download it again.": "فایل مدل خراب یا ناقص است. آن را در بخش دانلودها حذف کنید و دوباره دانلود کنید.",
    "The llama.cpp engine is not installed yet (Downloads → Engine).": "موتور llama.cpp هنوز نصب نشده (در بخش دانلودها ببینید).",
    "unknown file": "فایل ناشناخته",
    "connection closed early": "اتصال زودتر از موعد بسته شد",
    "The downloaded file failed validation and was removed. Try again.": "فایل دانلودشده معتبر نبود و حذف شد. دوباره امتحان کنید.",
    "This file does not look like the expected one": "این فایل همان فایل مورد انتظار به نظر نمی‌رسد",
    "engine unavailable": "موتور در دسترس نیست",
    "No llama-server found in that file.": "llama-server در این فایل پیدا نشد.",
    "unsafe path in archive": "مسیر نامعتبر در فایل فشرده",
    "unsafe path in wheel": "مسیر نامعتبر در بسته",
    "pdftotext not installed": "pdftotext نصب نیست",
    "Could not download.": "دانلود انجام نشد.",
    "Could not work out where to download from:": "مبدأ دانلود مشخص نشد:",
    "no source answered": "هیچ منبعی پاسخ نداد",
    "Try: a proxy, another source, a direct link, or Import file.": "امتحان کنید: یک پروکسی، منبع دیگر، پیوند مستقیم یا «وارد کردن فایل».",
    "DNS lookup failed (the name cannot be resolved)": "نشانی سرور پیدا نشد (خطای DNS)",
    "timed out": "زمان انتظار تمام شد",
    "connection refused": "اتصال رد شد",
    "connection reset (often a filter or firewall)": "اتصال قطع شد (معمولاً فیلتر یا فایروال)",
    "TLS/SSL error": "خطای TLS/SSL",
    "(blocked or not found)": "(مسدود یا پیدا نشد)",
    "The engine did not start": "موتور شروع نشد",
    "Search engine:": "موتور جست‌وجو:",
    "Path not found:": "مسیر پیدا نشد:",
    "If it says 'unknown model architecture', update the engine in Downloads.": "اگر در خروجی «unknown model architecture» آمده، موتور را در بخش دانلودها به‌روز کنید.",
    "Log:": "گزارش:",
    "no output": "خروجی ندارد",
    "The model did not produce an answer. Please ask again.": "مدل پاسخی نداد. دوباره بپرسید.",
    "Could not write": "نوشتن انجام نشد",
    "not available": "در دسترس نیست",
}

# messages that start with a fixed phrase and end with a detail the app cannot translate (paths, codes)
ERR_PREFIX_FA = [
    ("The engine did not start", "موتور شروع نشد"),
    ("Could not download.", "دانلود انجام نشد."),
    ("Could not work out where to download from:", "مبدأ دانلود مشخص نشد:"),
    ("Path not found:", "مسیر پیدا نشد:"),
    ("Search engine:", "موتور جست‌وجو:"),
]


def _loc_part(part):
    """Translates one part of a message: an exact phrase, a known prefix, or a known phrase inside it."""
    t = part.strip()
    if not t:
        return part
    if t in ERR_FA:
        return ERR_FA[t]
    for en, fa in ERR_PREFIX_FA:
        if t.startswith(en):
            t = fa + t[len(en):]
            break
    for en, fa in ERR_FA.items():
        if en in t:
            t = t.replace(en, fa)
    return t


def loc(msg):
    """Shows a message in Persian when the interface is in Persian. Parts that are known phrases are translated;
    technical details (file names, paths, HTTP codes, log locations) are kept as they are."""
    msg = "" if msg is None else str(msg)
    if LANG != "fa":
        return msg
    if msg in ERR_FA:
        return ERR_FA[msg]
    out = []
    for line in msg.split("\n"):
        segs = re.split(r"( · )", line)
        out.append("".join(seg if seg == " · " else _loc_part(seg) for seg in segs))
    return "\n".join(out)


LANG = "en"


def T(en, fa):
    return fa if LANG == "fa" else en


def fd(n):
    s = str(n)
    return s.translate({ord(str(i)): "۰۱۲۳۴۵۶۷۸۹"[i] for i in range(10)}) if LANG == "fa" else s


def esc(s):
    return html.escape(str(s), quote=True)


def dir_of(s):
    for ch in s:
        o = ord(ch)
        if 0x590 <= o <= 0x8FF or 0xFB50 <= o <= 0xFEFF:
            return "rtl"
        if ch.isalpha():
            return "ltr"
    return "rtl" if LANG == "fa" else "ltr"


def rt(h, d):
    return '<div dir="%s" align="%s">%s</div>' % (d, "right" if d == "rtl" else "left", h)


def fmt_size(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return ("%.0f %s" if u == "B" else "%.1f %s") % (n, u)
        n /= 1024


def round_eta(s):
    """Remaining time, in 5-second steps, so the label is not redrawn on every refresh."""
    return None if s is None else int(round(float(s) / 5.0)) * 5


def fmt_eta(s):
    if s is None:
        return "—"
    s = int(s)
    return "%ds" % s if s < 60 else ("%dm %02ds" % (s // 60, s % 60) if s < 3600 else "%dh %02dm" % (s // 3600, (s % 3600) // 60))


DEV_LINKS = [
    ("github", "GitHub", "https://github.com/Shayan-Rahmati"),
    ("linkedin", "LinkedIn", "http://www.linkedin.com/in/shayan-rahmati"),
    ("instagram", "Instagram", "https://instagram.com/shayan.g.rahmati"),
    ("telegram", "@TheOBS3RVER", "https://t.me/TheOBS3RVER"),
    ("telegram", "@TheENGIN3ER", "https://t.me/TheENGIN3ER"),
    ("globe", "Primee.ir", "https://primee.ir"),
    ("mail", "Email", "mailto:shayan.g.rahmati@gmail.com"),
]


ACCENTS = {  # name: (light, light ink, dark, dark ink, swatch)
    "blue": ("#1f4fd8", "#ffffff", "#6f95ff", "#071333", "#3b6ef0"),
    "violet": ("#7c3aed", "#ffffff", "#a78bfa", "#1a1030", "#8b5cf6"),
    "teal": ("#0d9488", "#ffffff", "#2dd4bf", "#042f2e", "#14b8a6"),
    "green": ("#15803d", "#ffffff", "#4ade80", "#052e16", "#22c55e"),
    "amber": ("#d97706", "#ffffff", "#fbbf24", "#1c1000", "#f59e0b"),
    "rose": ("#e11d48", "#ffffff", "#fb7185", "#2a0a12", "#f43f5e"),
}


# Starter questions shown in an empty conversation: (English, Persian)
STARTERS = [
    ("Summarise my documents", "خلاصه‌ی اسناد من"),
    ("What are the key dates?", "تاریخ‌های مهم کدام‌ها هستند؟"),
    ("What do the documents say about…", "اسناد درباره‌ی … چه می‌گویند؟"),
]


BASE_COLORS = {
    "light": dict(bg="#e8eef5", side="#f4f7fb", paper="#ffffff", ink="#14202b", mute="#5a6b7c", line="#d0d8e2",
                  hover="#e4ebf3", soft="#f5f7fb", cite="#f0b429",
                  ok="#1f9d57", warn="#d9962b", bad="#c8412a"),
    "dark": dict(bg="#000000", side="#0a0a0a", paper="#141414", ink="#f2f2f2", mute="#9a9a9a", line="#2a2a2a",
                 hover="#1c1c1c", soft="#0f0f0f", cite="#e3ad52",
                 ok="#4cc882", warn="#e3ad52", bad="#e0684f"),
}


FILE_BADGES = {
    "pdf": ("#ef4444", "#b91c1c", "PDF"), "docx": ("#3b82f6", "#1d4ed8", "DOC"), "odt": ("#3b82f6", "#1d4ed8", "ODT"),
    "rtf": ("#3b82f6", "#1d4ed8", "RTF"), "xlsx": ("#22c55e", "#15803d", "XLS"), "ods": ("#22c55e", "#15803d", "ODS"),
    "csv": ("#22c55e", "#15803d", "CSV"), "tsv": ("#22c55e", "#15803d", "TSV"), "pptx": ("#fb923c", "#c2410c", "PPT"),
    "odp": ("#fb923c", "#c2410c", "ODP"), "txt": ("#94a3b8", "#64748b", "TXT"), "log": ("#94a3b8", "#64748b", "LOG"),
    "md": ("#a78bfa", "#6d28d9", "MD"), "mdx": ("#a78bfa", "#6d28d9", "MDX"), "rst": ("#a78bfa", "#6d28d9", "RST"),
    "html": ("#fbbf24", "#b45309", "HTM"), "htm": ("#fbbf24", "#b45309", "HTM"), "xml": ("#22d3ee", "#0e7490", "XML"),
    "json": ("#fbbf24", "#b45309", "JSON"), "yml": ("#fbbf24", "#b45309", "YML"), "yaml": ("#fbbf24", "#b45309", "YML"),
    "epub": ("#2dd4bf", "#0f766e", "EPUB"),
}


_SVG_CACHE = {}


def svg_icon(name, color):
    """Icons are built once per (name, color): the window repaints often and the markup never changes."""
    key = (name, color)
    if key not in _SVG_CACHE:
        _SVG_CACHE[key] = _svg_icon_build(name, color)
    return _SVG_CACHE[key]


def _svg_icon_build(name, color):
    attrs, inner = ICONS[name]
    a = " ".join('%s="%s"' % (k, v.replace("currentColor", color)) for k, v in attrs.items())
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" %s>%s</svg>' % (a, inner.replace("currentColor", color))


def svg_file(ext):
    c1, c2, lab = FILE_BADGES.get(ext, ("#94a3b8", "#64748b", (ext or "FILE").upper()[:4]))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/></linearGradient></defs>'
            '<path d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="url(#g)"/>'
            '<path d="M14 2v5h5" fill="#ffffff" fill-opacity=".45"/>'
            '<text x="12" y="17.5" font-size="5.4" font-weight="800" text-anchor="middle" fill="#ffffff" font-family="sans-serif">%s</text></svg>'
            % (c1, c2, lab))


SVG_FOLDER = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><defs><linearGradient id="f" x1="0" y1="0" x2="0" y2="1">'
              '<stop offset="0" stop-color="#fcd34d"/><stop offset="1" stop-color="#f59e0b"/></linearGradient></defs>'
              '<path d="M2 6a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v1H2z" fill="#d97706"/>'
              '<path d="M2 9h20v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z" fill="url(#f)"/></svg>')


def linux_scheme():
    """Best-effort dark or light detection, for when Qt cannot tell (WSL, bare X11, and so on)."""
    try:
        if os.environ.get("WSL_DISTRO_NAME"):
            r = subprocess.run(["reg.exe", "query", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                                "/v", "AppsUseLightTheme"], capture_output=True, text=True, timeout=3)
            m = re.search(r"0x([0-9a-fA-F]+)", r.stdout or "")
            if m:
                return "light" if int(m.group(1), 16) else "dark"
    except Exception:
        pass
    try:
        if sys.platform.startswith("linux"):
            for key in ("color-scheme", "gtk-theme"):
                r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", key], capture_output=True, text=True, timeout=2)
                o = (r.stdout or "").lower()
                if "dark" in o:
                    return "dark"
                if key == "color-scheme" and ("light" in o or "default" in o):
                    return "light"
            if "dark" in os.environ.get("GTK_THEME", "").lower():
                return "dark"
    except Exception:
        pass
    return None


FONT_STATE = {"loaded": False, "family": "", "why": ""}


def apply_vazirmatn(core, qapp, QFont, QFontDatabase, QFontInfo):
    """Loads the cached Vazirmatn and applies it to the whole application."""
    from PySide6.QtGui import QFontMetrics
    p = core.font_path()
    if not (os.path.isfile(p) and os.path.getsize(p) > 50_000):
        FONT_STATE["why"] = "font file not present"
        return False
    fid = QFontDatabase.addApplicationFont(p)
    if fid < 0:
        FONT_STATE["why"] = "Qt could not read the font file"
        return False
    fams = QFontDatabase.applicationFontFamilies(fid)
    if not fams:
        FONT_STATE["why"] = "Qt found no font family in the file"
        return False
    f = QFont()
    f.setFamilies(fams + ["Segoe UI", "Noto Sans Arabic", "Tahoma", "DejaVu Sans"])
    f.setPointSize(10)
    qapp.setFont(f)
    for w in qapp.allWidgets():
        w.setFont(f)
    in_use = QFontInfo(f).family()
    sample = "سلام دنیای فارسی ۱۲۳"
    fb = QFont()
    fb.setFamilies(["DejaVu Sans", "Liberation Sans"])
    fb.setPointSize(10)
    w_vaz, w_fb = QFontMetrics(f).horizontalAdvance(sample), QFontMetrics(fb).horizontalAdvance(sample)
    FONT_STATE.update(loaded=True, family=in_use, why="")
    print("Persian UI font: family=%s, width Vazirmatn=%d fallback=%d" % (in_use, w_vaz, w_fb))
    return True


from kb_log import log as _klog


def run_gui(core):
    from PySide6.QtCore import (Qt, QObject, Signal, QTimer, QRegularExpression, QSize, QRect, QPoint, QRectF,
                                QByteArray, QUrl, QEvent, QPointF)
    from PySide6.QtGui import (QFont, QFontMetrics, QPalette, QColor, QPen, QTextDocument, QTextCursor, QPixmap, QPainter, QIcon, QBrush,
                               QDesktopServices)
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import (QStyledItemDelegate, QStyle, QGraphicsDropShadowEffect, QRadioButton, QSlider,
                                   QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QPushButton,
                                   QLabel, QTreeWidget, QTreeWidgetItem, QProgressBar, QCheckBox, QComboBox, QTextEdit, QPlainTextEdit,
                                   QTextBrowser, QDialog, QFileDialog, QMessageBox, QFrame, QScrollArea, QToolButton,
                                   QButtonGroup, QLineEdit, QLayout, QSizePolicy, QInputDialog, QWidgetItem, QListWidget, QListWidgetItem)
    global LANG
    LANG = core.settings.get("lang", "en")
    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setApplicationName("Knowledge Bank")
    qapp.setStyle("Fusion")
    hints = qapp.styleHints()

    # ---- fonts: Vazirmatn if it is cached, otherwise the system fonts
    from PySide6.QtGui import QFontDatabase, QFontInfo
    base_font = QFont()
    base_font.setFamilies(["Segoe UI", "Noto Sans Arabic", "Noto Sans", "Tahoma", "DejaVu Sans"])
    base_font.setPointSize(10)
    qapp.setFont(base_font)
    apply_vazirmatn(core, qapp, QFont, QFontDatabase, QFontInfo)

    # ---- background work helper
    class Bridge(QObject):
        done = Signal(object, object)
        delta = Signal(object, object)

        def __init__(self):
            super().__init__()
            self.done.connect(lambda cb, res: cb(res))

    bridge = Bridge()

    def bg(fn, cb):
        def w():
            try:
                res = ("ok", fn())
            except Exception as e:
                traceback.print_exc()
                res = ("err", "%s" % e)
            bridge.done.emit(cb, res)
        threading.Thread(target=w, daemon=True).start()

    # ---- theme
    def system_scheme():
        try:
            cs = hints.colorScheme()
            if cs == Qt.ColorScheme.Dark:
                return "dark"
            if cs == Qt.ColorScheme.Light:
                return "light"
        except Exception:
            pass
        return linux_scheme() or "light"

    def resolved_mode():
        m = core.settings.get("theme", "system")
        return m if m in ("light", "dark") else system_scheme()

    def tok():
        mode = resolved_mode()
        c = dict(BASE_COLORS[mode])
        a = ACCENTS.get(core.settings.get("accent", "blue"), ACCENTS["blue"])
        c["acc"], c["accink"] = (a[0], a[1]) if mode == "light" else (a[2], a[3])
        c["mode"] = mode
        c["tint"] = _rgba(c["acc"], 0.14 if mode == "dark" else 0.10)     # soft accent fill
        c["tint2"] = _rgba(c["acc"], 0.26 if mode == "dark" else 0.20)    # stronger accent fill (pills)
        return c

    icon_cache = {}

    def pix(svg, size):
        key = (svg, size)
        if key in icon_cache:
            return icon_cache[key]
        dpr = max(1.0, float(qapp.devicePixelRatio()))
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p, QRectF(0, 0, size, size))
        p.end()
        icon_cache[key] = pm
        return pm

    def icon(name, color, size=16):
        return QIcon(pix(svg_icon(name, color), size))

    def file_icon(name_or_ext, size=18):
        ext = name_or_ext.rsplit(".", 1)[-1].lower() if "." in name_or_ext else name_or_ext.lower()
        return QIcon(pix(svg_file(ext), size))

    folder_icon = lambda size=18: QIcon(pix(SVG_FOLDER, size))  # noqa: E731

    def _mix(hexa, hexb, t):
        a = [int(hexa[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(hexb[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))

    def _rgba(hexc, alpha):
        r, g, b = [int(hexc[i:i + 2], 16) for i in (1, 3, 5)]
        return "rgba(%d,%d,%d,%.2f)" % (r, g, b, alpha)

    def check_icon_url():
        """A white check mark as an SVG file, for the checked state of checkboxes (Qt style sheets need a file)."""
        folder = os.path.join(DATA, "icons")
        path = os.path.join(folder, "check-white.svg")
        if not os.path.isfile(path):
            os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg_icon("check", "#ffffff"))
        return path.replace("\\", "/")

    def make_qss(c):
        # accent-based colours: a soft tint and the gradient end
        c = dict(c)
        c["check"] = check_icon_url()
        c["tint"] = _rgba(c["acc"], 0.14 if c["mode"] == "dark" else 0.10)
        c["tint2"] = _rgba(c["acc"], 0.26 if c["mode"] == "dark" else 0.20)
        c["grad2"] = _mix(c["acc"], "#ffffff", 0.22)
        c["grad_end"] = _mix(c["acc"], "#000000", 0.12) if c["mode"] == "light" else _mix(c["acc"], "#ffffff", 0.10)
        fam = FONT_STATE.get("family") if FONT_STATE.get("loaded") else ""
        # set the family on every widget, so none falls back to a system font
        font_rule = ('QWidget{font-family:"%s","Segoe UI","Noto Sans Arabic","Tahoma","DejaVu Sans";}' % fam) if fam else ""
        return font_rule + """
        QWidget{color:%(ink)s}
        QMainWindow,QDialog{background:%(bg)s}
        #sideScroll,#sideInner{background:%(side)s;border:none}
        #mainArea,#threadScroll,#threadIn,#threadWrap{background:%(bg)s;border:none}
        QToolTip{background:%(paper)s;color:%(ink)s;border:1px solid %(line)s;padding:4px 8px;border-radius:6px}
        QFrame#card{background:%(paper)s;border:1px solid %(line)s;border-radius:14px}

        QFrame#chipbar{background:%(paper)s;border:1px solid %(line)s;border-radius:10px}
        QFrame#seg{background:%(soft)s;border:1px solid %(line)s;border-radius:9px}
        QLabel{background:transparent}
        QLabel#cardTitle{font-weight:700;font-size:11pt}
        QLabel#appTitle{font-weight:800;font-size:15pt}
        QLabel#mute{color:%(mute)s}
        QLabel#devlabel{color:%(acc)s;font-size:8pt;font-weight:700;letter-spacing:1px}
        QLabel#groupTitle{color:%(acc)s;font-weight:700;font-size:10pt;padding-bottom:2px;border-bottom:1px solid %(line)s}
        QLabel#subTitle{font-weight:600;font-size:9.5pt;padding-top:4px}
        QWidget#tuneBody{background:%(bg)s}
        QRadioButton{spacing:8px;padding:2px 0px}
        QRadioButton::indicator{width:15px;height:15px;border-radius:8px;border:1px solid %(mute)s;background:%(paper)s}
        QRadioButton::indicator:checked{border:4px solid %(acc)s;background:%(paper)s}
        QRadioButton::indicator:hover{border-color:%(acc)s}
        QCheckBox{spacing:8px;padding:2px 0px}
        QCheckBox::indicator{width:15px;height:15px;border-radius:4px;border:1px solid %(mute)s;background:%(paper)s}
        QCheckBox::indicator:checked{background:%(acc)s;border:1px solid %(acc)s;image:url("%(check)s")}
        QCheckBox::indicator:hover{border-color:%(acc)s}
        QLabel#devname{color:%(ink)s;font-weight:700;font-size:11pt;border-bottom:2px solid %(acc)s;padding-bottom:1px}
        QLabel#devver{color:%(mute)s;font-size:8pt;padding-top:2px}
        QLabel#logo{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 %(acc)s,stop:1 %(grad_end)s);border-radius:11px}
        QLabel#avatar{background:%(acc)s;border-radius:14px}
        QLabel#heroIcon{background:%(soft)s;border:1px solid %(line)s;border-radius:22px}
        QLabel#badge{background:%(soft)s;border:1px solid %(line)s;border-radius:9px;padding:1px 9px;color:%(mute)s;font-size:8pt}
        QLabel#badge[kind="ok"]{color:%(ok)s;border-color:%(ok)s}
        QLabel#badge[kind="warn"]{color:%(warn)s;border-color:%(warn)s}
        QLabel#badge[kind="bad"]{color:%(bad)s;border-color:%(bad)s}
        QLabel#badge[kind="acc"]{color:%(acc)s;border-color:%(acc)s;background:%(tint)s}
        QLabel#dot{border-radius:5px;min-width:10px;max-width:10px;min-height:10px;max-height:10px;background:%(mute)s}
        QLabel#dot[kind="ok"]{background:%(ok)s}QLabel#dot[kind="warn"]{background:%(warn)s}QLabel#dot[kind="acc"]{background:%(acc)s}
        QPushButton{background:%(paper)s;border:1px solid %(line)s;border-radius:9px;padding:7px 14px}
        QPushButton:hover{background:%(hover)s}
        QPushButton:disabled{color:%(mute)s;background:%(soft)s}
        QPushButton#primary{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %(grad2)s,stop:1 %(acc)s);color:%(accink)s;border:1px solid %(acc)s;font-weight:600}
        QPushButton#primary:hover{border-color:%(ink)s}
        QPushButton#primary:disabled{background:%(line)s;color:%(mute)s;border-color:%(line)s}
        QPushButton#ghost{border:none;background:transparent;color:%(mute)s;padding:4px 8px}
        QPushButton#ghost:hover{background:%(hover)s;color:%(ink)s}
        QPushButton#link{background:%(soft)s;border:1px solid %(line)s;border-radius:14px;padding:4px 11px;font-size:9pt}
        QPushButton#link:hover{border-color:%(acc)s;color:%(acc)s;background:%(tint)s}
        QPushButton#chip{background:%(soft)s;border:1px solid %(line)s;border-radius:13px;padding:3px 11px 3px 8px;font-size:9pt}
        QPushButton#chip:hover{background:%(tint)s}
        QPushButton#chip:hover{border-color:%(acc)s}
        QToolButton{background:transparent;border:1px solid transparent;border-radius:8px;padding:5px}
        QToolButton:hover{background:%(hover)s}
        QToolButton:checked{background:%(tint2)s;border:1px solid %(acc)s}
        QToolButton#passToggle{padding:3px 8px;color:%(mute)s}
        QLineEdit,QComboBox{background:%(soft)s;border:1px solid %(line)s;border-radius:8px;padding:5px 9px}
        QLineEdit:focus,QComboBox:focus{border:1px solid %(acc)s;background:%(paper)s}
        QComboBox:on{border:1px solid %(acc)s}
        QComboBox::drop-down{border:none;width:22px}
        QComboBox QAbstractItemView{background:%(paper)s;border:1px solid %(line)s;selection-background-color:%(acc)s;selection-color:%(accink)s}
        QCheckBox{spacing:8px}
        QTreeWidget{background:transparent;border:none;outline:0}
        QTreeWidget{font-size:10pt}
        QTreeWidget::item{padding:6px 6px;margin:1px 0px;border-radius:8px;min-height:22px}
        QTreeWidget::item:hover{background:%(hover)s}
        QTreeWidget::item:selected{background:%(tint2)s;color:%(ink)s}
        QProgressBar{background:%(line)s;border:none;border-radius:3px;min-height:6px;max-height:6px}
        QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 %(acc)s,stop:1 %(grad2)s);border-radius:3px}
        QScrollBar:vertical{background:transparent;width:11px;margin:2px}
        QScrollBar::handle:vertical{background:%(line)s;min-height:28px;border-radius:4px}
        QScrollBar::handle:vertical:hover{background:%(acc)s}
        QScrollBar::add-line,QScrollBar::sub-line{height:0;width:0}
        QScrollBar:horizontal{height:0}
        QFrame#bubbleQ{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 %(acc)s,stop:1 %(grad_end)s);border-radius:15px}
        QLabel#qtext{color:%(accink)s;background:transparent}
        QFrame#ans{background:%(paper)s;border:1px solid %(line)s;border-left:3px solid %(acc)s;border-radius:14px}
        QFrame#lead{background:%(soft)s;border-radius:9px}
        QFrame#ai{background:%(soft)s;border:1px solid %(line)s;border-left:3px solid %(acc)s;border-radius:9px}
        QFrame#hit{background:%(soft)s;border:1px solid %(line)s;border-radius:10px}
        QFrame#composer{background:%(paper)s;border:1px solid %(line)s;border-radius:28px}
        QFrame#composer:focus-within{border:1px solid %(acc)s}
        QPushButton#sendBtn{background:%(acc)s;border:none;border-radius:18px;min-width:36px;max-width:36px;min-height:36px;max-height:36px;padding:0px}
        QPushButton#sendBtn:hover{background:%(grad2)s}
        QPushButton#sendBtn:disabled{background:%(line)s}
        QPushButton#stopBtn{background:%(tint2)s;border:1px solid %(acc)s;border-radius:18px;min-width:36px;max-width:36px;min-height:36px;max-height:36px;padding:0px}
        QPushButton#stopBtn:hover{background:%(tint)s;border-color:%(acc)s}
        QPushButton#chipToggle{background:transparent;border:1px solid %(line)s;border-radius:13px;padding:4px 13px;color:%(mute)s;font-size:9pt}
        QPushButton#chipToggle:hover{color:%(ink)s;border-color:%(mute)s}
        QPushButton#chipToggle:checked{background:%(tint)s;border-color:%(acc)s;color:%(acc)s}
        QTextEdit#q{background:transparent;border:none;font-size:11pt}
        QFrame#dlrow{background:%(soft)s;border:1px solid %(line)s;border-radius:10px}
        QTextBrowser{background:%(paper)s;border:1px solid %(line)s;border-radius:10px}
        QSplitter::handle{background:%(line)s;width:1px}
        """ % c

    def apply_theme():
        m = core.settings.get("theme", "system")
        try:
            hints.setColorScheme({"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(m, Qt.ColorScheme.Unknown))
        except Exception:
            pass
        c = tok()
        pal = QPalette()
        R = QPalette.ColorRole
        for role, key in ((R.Window, "bg"), (R.WindowText, "ink"), (R.Base, "paper"), (R.AlternateBase, "soft"),
                          (R.Text, "ink"), (R.Button, "paper"), (R.ButtonText, "ink"), (R.Highlight, "acc"),
                          (R.HighlightedText, "accink"), (R.Link, "acc"), (R.PlaceholderText, "mute"),
                          (R.ToolTipBase, "paper"), (R.ToolTipText, "ink")):
            pal.setColor(role, QColor(c[key]))
        qapp.setPalette(pal)
        qapp.setStyleSheet(make_qss(c))
        return c

    # ---- small widgets
    class ElideLabel(QLabel):
        def __init__(self, text=""):
            super().__init__()
            self._full = text
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        def setFull(self, t):
            self._full = t
            self.setToolTip(t)
            self.update()

        def minimumSizeHint(self):
            return QSize(24, self.fontMetrics().height() + 2)

        def sizeHint(self):
            return QSize(self.fontMetrics().horizontalAdvance(self._full) + 6, self.fontMetrics().height() + 2)

        def paintEvent(self, e):
            p = QPainter(self)
            p.setPen(self.palette().color(self.foregroundRole()))
            t = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(10, self.width()))
            # a left-to-right mark keeps the base direction left to right, so paths and English titles read correctly
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute,
                       "\u200e" + t)

    class FlowLayout(QLayout):
        def __init__(self, hs=6, vs=6):
            super().__init__()
            self.items, self.hs, self.vs = [], hs, vs

        def addItem(self, it):
            self.items.append(it)

        def count(self):
            return len(self.items)

        def itemAt(self, i):
            return self.items[i] if 0 <= i < len(self.items) else None

        def takeAt(self, i):
            return self.items.pop(i) if 0 <= i < len(self.items) else None

        def hasHeightForWidth(self):
            return True

        def heightForWidth(self, w):
            return self._do(QRect(0, 0, w, 0), True)

        def setGeometry(self, r):
            super().setGeometry(r)
            self._do(r, False)

        def sizeHint(self):
            return self.minimumSize()

        def addWidget(self, w):
            self.addChildWidget(w)
            self.items.append(QWidgetItem(w))

        def minimumSize(self):
            s = QSize(0, 0)
            for it in self.items:
                s = s.expandedTo(it.minimumSize())
            m = self.contentsMargins()
            return QSize(s.width() + m.left() + m.right(), s.height() + m.top() + m.bottom())

        def _do(self, rect, test):
            m = self.contentsMargins()
            eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
            rtl = qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
            x = eff.right() + 1 if rtl else eff.x()
            y, lh = eff.y(), 0
            for it in self.items:
                sz = it.sizeHint()
                w, h = sz.width(), sz.height()
                if rtl:
                    if x - w < eff.x() and lh > 0:
                        x, y, lh = eff.right() + 1, y + lh + self.vs, 0
                    if not test:
                        it.setGeometry(QRect(QPoint(x - w, y), sz))
                    x -= w + self.hs
                else:
                    if x + w > eff.right() + 1 and lh > 0:
                        x, y, lh = eff.x(), y + lh + self.vs, 0
                    if not test:
                        it.setGeometry(QRect(QPoint(x, y), sz))
                    x += w + self.hs
                lh = max(lh, h)
            return y + lh - rect.y() + m.bottom()

    class Composer(QTextEdit):
        asked = Signal()

        def __init__(self):
            super().__init__()
            self.setAcceptRichText(False)
            self.setObjectName("q")
            self.setFrameShape(QFrame.Shape.NoFrame)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.document().setDocumentMargin(6)
            self._dir = None
            self.textChanged.connect(self.adjust)
            self.adjust()

        def adjust(self):
            txt = self.toPlainText()
            d = dir_of(txt) if txt.strip() else ("rtl" if LANG == "fa" else "ltr")
            if d != self._dir:                      # Persian or Arabic text runs right to left; Latin text runs left to right
                self._dir = d
                opt = self.document().defaultTextOption()
                opt.setTextDirection(Qt.LayoutDirection.RightToLeft if d == "rtl" else Qt.LayoutDirection.LeftToRight)
                opt.setAlignment(Qt.AlignmentFlag.AlignLeft)   # "left" means the start edge, so it flips in right-to-left layouts
                self.document().setDefaultTextOption(opt)
                # The widget's own direction too: it sets where the caret starts and how mixed lines are resolved.
                self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if d == "rtl" else Qt.LayoutDirection.LeftToRight)
            h = int(self.document().size().height()) + 8
            self.setFixedHeight(max(44, min(150, h)))

        def keyPressEvent(self, e):
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    super().keyPressEvent(e)          # Shift+Enter: a new line
                else:
                    self.asked.emit()
                return
            super().keyPressEvent(e)

    def term_pattern(t):
        """A regex for one search term or cited sentence. Spaces match any whitespace, so a sentence still matches when its line breaks differ."""
        return re.escape(t).replace(r"\ ", r"\s+")

    def block_html(b, terms, c, hit=False):
        """One block as HTML, in its own direction. Right-to-left blocks are right-aligned, others left-aligned."""
        kind, text = b["kind"], b["text"]
        d = text_dir(text) or ("rtl" if LANG == "fa" else "ltr")
        al = "right" if d == "rtl" else "left"
        bg = "background-color:%s;border-radius:6px;" % c["soft"] if hit else ""
        if kind == "h":
            size = {1: "16pt", 2: "13pt", 3: "12pt"}.get(b.get("level", 2), "11pt")
            return ('<h%d dir="%s" align="%s" style="font-size:%s;margin:14px 0 6px 0;%s">%s</h%d>'
                    % (min(b.get("level", 2), 4), d, al, size, bg, hl(text, terms, c), min(b.get("level", 2), 4)))
        if kind == "li":
            return ('<ul style="margin:2px 0 2px 0"><li dir="%s" align="%s" style="%s">%s</li></ul>'
                    % (d, al, bg, hl(text, terms, c).replace("\n", "<br>")))
        if kind == "pre":
            return ('<pre dir="ltr" style="font-family:monospace;background-color:%s;padding:8px;'
                    'border-radius:6px;">%s</pre>' % (c["soft"], hl(text, terms, c).replace("\n", "<br>")))
        if b.get("rows") is not None:
            rows = []
            for row in b["rows"]:
                cells = []
                for cell in row:
                    cd = text_dir(cell) or d
                    cells.append('<td dir="%s" align="%s" style="border:1px solid %s;padding:5px;">%s</td>'
                                 % (cd, "right" if cd == "rtl" else "left", c["line"],
                                    hl(cell, terms, c).replace("\n", "<br>")))
                rows.append("<tr>%s</tr>" % "".join(cells))
            return ('<table dir="%s" width="100%%" cellspacing="0" cellpadding="0" style="margin:8px 0;%s">%s</table>'
                    % (d, bg, "".join(rows)))
        return ('<p dir="%s" align="%s" style="margin:6px 0;%s">%s</p>'
                % (d, al, bg, hl(text, terms, c).replace("\n", "<br>")))

    def hl(text, terms, c):
        # No highlighting: the text is shown as written. Matches are still found by the viewer
        # (first_hit and find() below), so it still opens at the first match.
        return esc(text)

    # viewer
    class Viewer(QDialog):
        def __init__(self, parent):
            super().__init__(parent)
            self.resize(920, 720)
            lay = QVBoxLayout(self)
            top = QHBoxLayout()
            self.title = ElideLabel()
            self.prev, self.next, self.close_b = QToolButton(), QToolButton(), QToolButton()
            self.prev.clicked.connect(lambda: self.step(True))
            self.next.clicked.connect(lambda: self.step(False))
            self.close_b.clicked.connect(self.close)
            top.addWidget(self.title, 1)
            for b in (self.prev, self.next, self.close_b):
                top.addWidget(b)
            lay.addLayout(top)
            self.tb = QTextBrowser()
            self.tb.setOpenLinks(False)
            lay.addWidget(self.tb, 1)
            self.rx = None
            self.cache = {}                       # (path, modified, size) -> blocks, so reopening is instant
            self.token = None                     # identifies the latest request; older results are ignored
            self.pieces, self.pos, self.first_hit, self.scrolled = [], 0, None, False
            self.feed = QTimer(self)
            self.feed.timeout.connect(self.feed_next)
            self.restyle()

        def restyle(self):
            c = tok()
            fa = LANG == "fa"                       # Persian reads right to left
            self.prev.setIcon(icon("chevron-right" if fa else "chevron-left", c["ink"]))
            self.next.setIcon(icon("chevron-left" if fa else "chevron-right", c["ink"]))
            self.close_b.setIcon(icon("x", c["ink"]))
            self.prev.setToolTip(T("Previous match", "نتیجه‌ی قبلی"))
            self.next.setToolTip(T("Next match", "نتیجه‌ی بعدی"))

        def show_doc(self, path, ci, terms):
            """Opens a file at once and reads it in the background, so a large file never freezes the window."""
            self.restyle()
            self.title.setLayoutDirection(Qt.LayoutDirection.LeftToRight)     # a file path always reads left to right
            self.title.setFull(path)
            self.feed.stop()
            self.pieces, self.pos, self.first_hit, self.scrolled = [], 0, None, False
            self.show()
            self.raise_()
            self.tb.setHtml('<html><body><p dir="%s">%s</p></body></html>' % (
                "rtl" if LANG == "fa" else "ltr", esc(T("Reading the file…", "در حال خواندن فایل…"))))
            try:
                st = os.stat(path)
                key = (path, int(st.st_mtime), st.st_size)
            except OSError:
                key = None
            token = object()
            self.token = token
            if key in self.cache:
                return self.render(self.cache[key], terms)

            def done(res):
                if self.token is not token:               # another file was opened meanwhile
                    return
                if res[0] == "err":
                    self.tb.setHtml('<html><body><p>%s</p></body></html>' % esc(res[1]))
                    return
                if key is not None:
                    self.cache = dict(list(self.cache.items())[-7:] + [(key, res[1])])
                self.render(res[1], terms)

            bg(lambda: extract_blocks(path), done)

        def render(self, blocks, terms):
            """Builds the document in pieces, so a long document appears as it is prepared."""
            c = tok()
            ts = [t for t in (terms or []) if len(t) > 1]
            self.rx = (QRegularExpression("(" + "|".join(term_pattern(t) for t in ts) + ")",
                                          QRegularExpression.PatternOption.CaseInsensitiveOption) if ts else None)
            self.first_hit, self.scrolled = None, False
            pieces = []
            for i, b in enumerate(blocks):
                plain = b["text"] or " ".join(" ".join(r) for r in (b.get("rows") or []))
                hit = any(re.search(term_pattern(t), plain, re.I) for t in ts) if ts else False
                if hit and self.first_hit is None:
                    self.first_hit = i
                pieces.append('<a name="b%d"></a>%s' % (i, block_html(b, ts, c, hit)))
            if not blocks:
                pieces.append('<p dir="%s">%s</p>' % (
                    "rtl" if LANG == "fa" else "ltr",
                    esc(T("No readable text was found in this file.", "در این فایل متن خوانایی پیدا نشد."))))
            self.pieces, self.pos = pieces, 0
            self.tb.setHtml('<html><body style="line-height:150%%"></body></html>')
            self.feed.start(0)

        def feed_next(self):
            """Adds the next part of the document; scrolls to the first match once it is on screen."""
            if self.pos >= len(self.pieces):
                self.feed.stop()
                if self.first_hit is not None:
                    self.tb.scrollToAnchor("b%d" % self.first_hit)
                else:
                    self.tb.verticalScrollBar().setValue(0)
                self.pieces = []
                return
            end = min(len(self.pieces), self.pos + 120)
            cur = self.tb.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            cur.insertHtml("".join(self.pieces[self.pos:end]))
            self.pos = end
            if self.first_hit is not None and self.pos > self.first_hit and not self.scrolled:
                self.tb.scrollToAnchor("b%d" % self.first_hit)
                self.scrolled = True

        def step(self, back):
            if not self.rx:
                return
            fl = QTextDocument.FindFlag.FindBackward if back else QTextDocument.FindFlag(0)
            if not self.tb.find(self.rx, fl):
                cur = self.tb.textCursor()
                cur.movePosition(cur.MoveOperation.End if back else cur.MoveOperation.Start)
                self.tb.setTextCursor(cur)
                self.tb.find(self.rx, fl)

    # download manager
    class TuneDialog(QDialog):
        """Answer settings, in three short groups. Each choice has a one-line explanation."""
        LENGTHS = (("short", "Short", "کوتاه", "One or two sentences.", "یک یا دو جمله."),
                   ("normal", "Medium", "متوسط", "A few sentences.", "چند جمله."),
                   ("long", "Detailed", "کامل", "A short paragraph.", "یک پاراگراف کوتاه."))
        COUNTS = (("few", "Few", "کم", "Fewer passages, quicker to read.", "بند کمتر و خواندن سریع‌تر."),
                  ("standard", "Standard", "معمول", "A balanced number of passages.", "تعداد معمولی بندها."),
                  ("many", "Many", "زیاد", "More passages, for broad questions.", "بندهای بیشتر برای پرسش‌های گسترده."))

        def __init__(self, parent):
            super().__init__(parent)
            self.resize(440, 520)
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            body = QWidget()
            body.setObjectName("tuneBody")
            root = QVBoxLayout(body)
            root.setContentsMargins(18, 16, 18, 14)
            root.setSpacing(12)
            scroll.setWidget(body)
            outer.addWidget(scroll, 1)
            self.title = QLabel()
            self.title.setObjectName("appTitle")
            self.sub = QLabel()
            self.sub.setObjectName("mute")
            self.sub.setWordWrap(True)
            root.addWidget(self.title)
            root.addWidget(self.sub)

            # --- group 1: answers
            g1, l1, self.h_answers = self.group()
            self.len_h = QLabel()
            self.len_h.setObjectName("subTitle")
            l1.addWidget(self.len_h)
            self.radios = {}
            for key, en, fa, hint, hint_fa in self.LENGTHS:
                rb = QRadioButton()
                rb.toggled.connect(lambda on, k=key: on and self.set_len(k))
                note = QLabel()
                note.setObjectName("mute")
                note.setContentsMargins(24, 0, 0, 4)
                l1.addWidget(rb)
                l1.addWidget(note)
                self.radios[key] = (rb, en, fa, hint, hint_fa, note)
            self.ai_box = QCheckBox()
            self.ai_box.toggled.connect(self.set_ai)
            self.ai_note = QLabel()
            self.ai_note.setObjectName("mute")
            self.ai_note.setWordWrap(True)
            self.ai_note.setContentsMargins(24, 0, 0, 0)
            l1.addWidget(self.ai_box)
            l1.addWidget(self.ai_note)
            root.addWidget(g1)

            # --- group 2: search
            g2, l2, self.h_search = self.group()
            self.count_h = QLabel()
            self.count_h.setObjectName("subTitle")
            l2.addWidget(self.count_h)
            self.count_radios = {}
            for key, en, fa, hint, hint_fa in self.COUNTS:
                rb = QRadioButton()
                rb.toggled.connect(lambda on, k=key: on and self.set_setting("results", k))
                note = QLabel()
                note.setObjectName("mute")
                note.setContentsMargins(24, 0, 0, 4)
                l2.addWidget(rb)
                l2.addWidget(note)
                self.count_radios[key] = (rb, en, fa, hint, hint_fa, note)
            self.meaning_box = QCheckBox()
            self.meaning_box.toggled.connect(lambda on: self.set_setting("use_meaning", bool(on)))
            self.meaning_note = QLabel()
            self.meaning_note.setObjectName("mute")
            self.meaning_note.setWordWrap(True)
            self.meaning_note.setContentsMargins(24, 0, 0, 0)
            l2.addWidget(self.meaning_box)
            l2.addWidget(self.meaning_note)
            root.addWidget(g2)

            # --- group 3: display
            g3, l3, self.h_display = self.group()
            self.match_box = QCheckBox()
            self.match_box.toggled.connect(lambda on: self.set_setting("show_match", bool(on)))
            self.match_note = QLabel()
            self.match_note.setObjectName("mute")
            self.match_note.setWordWrap(True)
            self.match_note.setContentsMargins(24, 0, 0, 0)
            l3.addWidget(self.match_box)
            l3.addWidget(self.match_note)
            root.addWidget(g3)

            # --- group 4: speed and resources
            g4, l4, self.h_speed = self.group()
            self.speed_note = QLabel()
            self.speed_note.setObjectName("mute")
            self.speed_note.setWordWrap(True)
            l4.addWidget(self.speed_note)
            self.speed = QSlider(Qt.Orientation.Horizontal)
            self.speed.setRange(0, len(RESOURCE_LEVELS) - 1)
            self.speed.setTickPosition(QSlider.TickPosition.TicksBelow)
            self.speed.setTickInterval(1)
            self.speed.setValue(RESOURCE_LEVELS.index(core.settings.get("resources", "balanced")))
            self.speed.valueChanged.connect(self.set_speed)
            l4.addWidget(self.speed)
            ends = QHBoxLayout()
            self.speed_labels = []
            for i in range(len(RESOURCE_LEVELS)):
                lb = QLabel()
                lb.setObjectName("mute")
                lb.setAlignment(Qt.AlignmentFlag.AlignCenter if i else Qt.AlignmentFlag.AlignLeft)
                self.speed_labels.append(lb)
                ends.addWidget(lb, 1)
            l4.addLayout(ends)
            root.addWidget(g4)

            root.addStretch(1)
            foot = QHBoxLayout()
            foot.addStretch(1)
            self.close_b = QPushButton()
            self.close_b.setObjectName("primary")
            self.close_b.clicked.connect(self.close)
            foot.addWidget(self.close_b)
            root.addLayout(foot)
            self.texts()

        def group(self):
            """One settings group: a card with its own layout. Returns (card, layout, heading label)."""
            card = QFrame()
            card.setObjectName("card")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(16, 12, 16, 12)
            lay.setSpacing(6)
            heading = QLabel()
            heading.setObjectName("groupTitle")
            lay.addWidget(heading)
            return card, lay, heading

        def set_len(self, key):
            self.parent().set_answer_length(key)
            self.refresh()

        def set_ai(self, on):
            if not on and not core.settings.get("grounded", True):
                # Smart answer and Based on sources cannot both be off: keep this one on
                self.ai_box.blockSignals(True)
                self.ai_box.setChecked(True)
                self.ai_box.blockSignals(False)
                return
            self.set_setting("ai", bool(on))

        def set_speed(self, index):
            key = RESOURCE_LEVELS[index]
            if core.settings.get("resources") != key:
                self.set_setting("resources", key)
                core.restart_engines()            # the engines restart in the background with the new thread count

        def set_setting(self, key, value):
            core.settings[key] = value
            core.save_settings()
            if key in ("grounded", "answer_length", "use_meaning", "ai"):
                from kb_log import log as _klog
                _klog("settings.change", key=key, value=value)

        def texts(self):
            self.setWindowTitle(T("Answer settings", "تنظیمات پاسخ"))
            self.title.setText(T("Answer settings", "تنظیمات پاسخ"))
            self.sub.setText(T("Changes apply to the next question you ask.", "از پرسش بعدی اعمال می‌شود."))
            self.h_answers.setText(T("Answers", "پاسخ‌ها"))
            self.len_h.setText(T("Length", "طول"))
            for key, (rb, en, fa, hint, hint_fa, note) in self.radios.items():
                rb.setText(T(en, fa))
                note.setText(T(hint, hint_fa))
            self.ai_box.setText(T("Write an AI answer for every question", "نوشتن پاسخ هوشمند برای هر پرسش"))
            self.ai_note.setText(T("Each answer is checked against your passages.", "هر پاسخ با بندهای شما بررسی می‌شود."))
            self.h_search.setText(T("Search", "جست‌وجو"))
            self.count_h.setText(T("How many passages", "تعداد بندها"))
            for key, (rb, en, fa, hint, hint_fa, note) in self.count_radios.items():
                rb.setText(T(en, fa))
                note.setText(T(hint, hint_fa))
            self.meaning_box.setText(T("Search by meaning as well as words", "جست‌وجو بر اساس معنا، علاوه بر واژه‌ها"))
            self.meaning_note.setText(T("Finds passages that use different words for the same idea.",
                                        "بندهایی را پیدا می‌کند که همان مفهوم را با کلمات دیگری بیان کرده‌اند."))
            self.h_display.setText(T("Display", "نمایش"))
            self.match_box.setText(T("Show how closely each citation matches", "نمایش میزان تطابق هر استناد"))
            self.match_note.setText(T("A percentage next to each citation, for example 80%.",
                                      "درصد کنار هر استناد؛ مثلاً ۸۰٪."))
            self.close_b.setText(T("Done", "تمام"))
            self.h_speed.setText(T("Speed and resources", "سرعت و منابع"))
            self.speed_note.setText(T("Full is fastest but uses most of the processor. Light keeps the computer responsive.",
                                      "«کامل» سریع‌ترین است، اما بیشترین پردازنده را می‌گیرد. «سبک» رایانه را روان نگه می‌دارد."))
            for lb, (key, en, fa) in zip(self.speed_labels, (("light", "Light", "سبک"), ("balanced", "Balanced", "متعادل"),
                                                            ("full", "Full", "کامل"))):
                lb.setText(T(en, fa))

        def refresh(self):
            cur = core.answer_length()
            for key, (rb, *_rest) in self.radios.items():
                rb.blockSignals(True)
                rb.setChecked(key == cur)
                rb.blockSignals(False)
            for key, (rb, *_rest) in self.count_radios.items():
                rb.blockSignals(True)
                rb.setChecked(key == core.settings.get("results", "standard"))
                rb.blockSignals(False)
            self.speed.blockSignals(True)
            self.speed.setValue(RESOURCE_LEVELS.index(core.settings.get("resources", "balanced")))
            self.speed.blockSignals(False)
            for box, key, default in ((self.meaning_box, "use_meaning", True), (self.match_box, "show_match", True),
                                      (self.ai_box, "ai", True)):
                box.blockSignals(True)
                box.setChecked(bool(core.settings.get(key, default)))
                box.blockSignals(False)

    class DlDialog(QDialog):
        def __init__(self, parent):
            super().__init__(parent)
            self.resize(860, 760)
            self.rows = {}
            self.sig = None
            self.notes = {}
            lay = QVBoxLayout(self)
            lay.setContentsMargins(16, 14, 16, 14)
            lay.setSpacing(10)
            self.title = QLabel()
            self.title.setObjectName("appTitle")
            self.sub = QLabel()
            self.sub.setObjectName("mute")
            self.sub.setWordWrap(True)
            lay.addWidget(self.title)
            lay.addWidget(self.sub)
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.Shape.NoFrame)
            inner = QWidget()
            inner.setObjectName("threadIn")
            self.v = QVBoxLayout(inner)
            self.v.setSpacing(12)
            # --- connection
            c1 = QFrame()
            c1.setObjectName("card")
            l1 = QVBoxLayout(c1)
            l1.setContentsMargins(14, 12, 14, 12)
            self.h_conn = QLabel()
            self.h_conn.setObjectName("cardTitle")
            l1.addWidget(self.h_conn)
            r1 = QHBoxLayout()
            self.proxy_l = QLabel()
            self.proxy = QLineEdit(core.settings.get("proxy", ""))
            self.proxy.setPlaceholderText(T("System proxy (automatic)", "پروکسی سیستم (خودکار)"))
            self.proxy.editingFinished.connect(self.on_proxy)
            r1.addWidget(self.proxy_l)
            r1.addWidget(self.proxy, 1)
            l1.addLayout(r1)
            r2 = QHBoxLayout()
            self.mirror_l = QLabel()
            self.mirror = QComboBox()
            self.mirror.addItem("", "auto")
            self.mirror.addItem("huggingface.co", "https://huggingface.co")
            self.mirror.addItem("hf-mirror.com", "https://hf-mirror.com")
            self.mirror.addItem("", "custom")
            self.mirror.currentIndexChanged.connect(self.on_mirror)
            self.custom = QLineEdit()
            self.custom.setPlaceholderText("https://my-mirror.example")
            self.custom.setVisible(False)
            self.custom.editingFinished.connect(self.on_custom)
            self.b_test = QPushButton()
            self.b_test.clicked.connect(self.run_test)
            r2.addWidget(self.mirror_l)
            r2.addWidget(self.mirror)
            r2.addWidget(self.custom, 1)
            r2.addStretch(1)
            r2.addWidget(self.b_test)
            l1.addLayout(r2)
            self.test_out = QLabel()
            self.test_out.setWordWrap(True)
            self.test_out.setTextFormat(Qt.TextFormat.RichText)
            l1.addWidget(self.test_out)
            self.v.addWidget(c1)
            # --- models (one model per task)
            c2 = QFrame()
            c2.setObjectName("card")
            l2 = QVBoxLayout(c2)
            l2.setContentsMargins(14, 12, 14, 12)
            l2.setSpacing(8)
            self.h_models = QLabel()
            self.h_models.setObjectName("cardTitle")
            l2.addWidget(self.h_models)
            self.role_l, self.role_v, self.notes = {}, {}, {}
            for role in ("embed", "gen", "rerank"):
                r = QHBoxLayout()
                lb = QLabel()
                lb.setMinimumWidth(120)
                vl = QLabel()
                vl.setObjectName("mute")
                self.role_l[role] = lb
                self.role_v[role] = vl
                r.addWidget(lb)
                r.addWidget(vl, 1)
                l2.addLayout(r)
                nl = QLabel()
                nl.setObjectName("mute")
                nl.setWordWrap(True)
                self.notes[role] = nl
                l2.addWidget(nl)
            er = QHBoxLayout()
            self.eng_l = QLabel()
            self.eng_l.setWordWrap(True)
            self.b_upd = QPushButton()
            self.b_upd.clicked.connect(self.update_engine)
            self.b_own = QPushButton()
            self.b_own.clicked.connect(self.own_engine)
            er.addWidget(self.eng_l, 1)
            er.addWidget(self.b_upd)
            er.addWidget(self.b_own)
            l2.addLayout(er)
            self.v.addWidget(c2)
            # --- Python packages
            c3 = QFrame()
            c3.setObjectName("card")
            l3 = QVBoxLayout(c3)
            l3.setContentsMargins(14, 12, 14, 12)
            l3.setSpacing(8)
            self.h_pkgs = QLabel()
            self.h_pkgs.setObjectName("cardTitle")
            l3.addWidget(self.h_pkgs)
            self.pkg_rows = {}
            for pk, (en, fa) in {"pypdf": ("PDF reader (pypdf)", "خواننده‌ی PDF (pypdf)"),
                                 "numpy": ("Vector math (numpy)", "محاسبات برداری (numpy)")}.items():
                r = QHBoxLayout()
                nm = QLabel(T(en, fa))
                st = QLabel()
                st.setObjectName("badge")
                st.setMinimumWidth(120)
                st.setAlignment(Qt.AlignmentFlag.AlignCenter)
                bt = QPushButton(T("Install", "نصب"))
                bt.setMinimumWidth(84)
                bt.clicked.connect(lambda _=False, p=pk: core.start_pip([p]))
                r.addWidget(nm, 1)
                r.addWidget(st, 0)
                r.addWidget(bt, 0)
                l3.addLayout(r)
                self.pkg_rows[pk] = (st, bt)
            fr_ = QHBoxLayout()
            fnm = QLabel(T("Persian UI font (Vazirmatn)", "قلم فارسی برنامه (وزیرمتن)"))
            self.font_st = QLabel()
            self.font_st.setObjectName("badge")
            self.font_st.setMinimumWidth(120)
            self.font_st.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.font_btn = QPushButton(T("Retry", "تلاش دوباره"))
            self.font_btn.setMinimumWidth(84)
            self.font_btn.clicked.connect(lambda: (self.font_btn.setEnabled(False), bg(core.ensure_font, lambda _r: self.refresh())))
            fr_.addWidget(fnm, 1)
            fr_.addWidget(self.font_st, 0)
            fr_.addWidget(self.font_btn, 0)
            l3.addLayout(fr_)
            self.font_note = QLabel()
            self.font_note.setObjectName("mute")
            self.font_note.setWordWrap(True)
            l3.addWidget(self.font_note)
            self.pkg_note = QLabel()
            self.pkg_note.setObjectName("mute")
            self.pkg_note.setWordWrap(True)
            l3.addWidget(self.pkg_note)
            self.v.addWidget(c3)
            # --- files
            gh = QHBoxLayout()
            self.h_files = QLabel()
            self.h_files.setObjectName("cardTitle")
            self.b_all = QPushButton()
            self.b_all.setObjectName("primary")
            self.b_pause = QPushButton()
            self.b_cancel = QPushButton()
            self.b_all.clicked.connect(lambda: core.dm.start())
            self.b_pause.clicked.connect(self.toggle_all)
            self.b_cancel.clicked.connect(core.dm.cancel_all)
            gh.addWidget(self.h_files, 1)
            gh.addWidget(self.b_all)
            gh.addWidget(self.b_pause)
            gh.addWidget(self.b_cancel)
            self.v.addLayout(gh)
            self.files_box = QVBoxLayout()
            self.files_box.setSpacing(8)
            self.v.addLayout(self.files_box)
            self.v.addStretch(1)
            sc.setWidget(inner)
            lay.addWidget(sc, 1)
            foot = QHBoxLayout()
            self.where = QLabel()
            self.where.setObjectName("mute")
            self.where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.b_open = QPushButton()
            self.b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(MODELS)))
            self.b_close = QPushButton()
            self.b_close.clicked.connect(self.close)
            foot.addWidget(self.where, 1)
            foot.addWidget(self.b_open)
            foot.addWidget(self.b_close)
            lay.addLayout(foot)
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            cur = core.settings.get("hf_host", "auto")
            idx = {"auto": 0, "https://huggingface.co": 1, "https://hf-mirror.com": 2}.get(cur, 3)
            self.mirror.blockSignals(True)
            self.mirror.setCurrentIndex(idx)
            self.mirror.blockSignals(False)
            if idx == 3:
                self.custom.setText(cur)
                self.custom.setVisible(True)
            self.texts()

        def texts(self):
            self.setWindowTitle(T("Downloads", "دانلودها"))
            self.title.setText(T("Downloads & models", "دانلودها و مدل‌ها"))
            self.sub.setText(T("Everything is downloaded once into the data folder, then works offline. Downloads resume after a pause or a lost connection, and every source is tried in turn.",
                               "همه‌چیز یک‌بار در پوشه‌ی داده دانلود می‌شود و بعد بدون اینترنت کار می‌کند. اگر دانلود قطع شود، از همان‌جا ادامه پیدا می‌کند و همه‌ی منبع‌ها به نوبت امتحان می‌شوند."))
            self.h_conn.setText(T("Connection", "اتصال"))
            self.proxy_l.setText(T("Proxy", "پروکسی"))
            self.mirror_l.setText(T("Source", "منبع"))
            self.mirror.setItemText(0, T("Automatic", "خودکار"))
            self.mirror.setItemText(3, T("Custom…", "دلخواه…"))
            self.b_test.setText(T("Test connection", "آزمایش اتصال"))
            self.h_models.setText(T("Models", "مدل‌ها"))
            self.role_l["embed"].setText(T("Meaning search", "جست‌وجوی معنایی"))
            self.role_l["gen"].setText(T("Answer writer", "نویسنده‌ی پاسخ"))
            self.role_l["rerank"].setText(T("Passage ranking", "رتبه‌بندی بندها"))
            self.b_upd.setText(T("Update engine", "به‌روزرسانی موتور"))
            self.b_own.setText(T("My own llama-server…", "انتخاب llama-server از رایانه…"))
            self.h_pkgs.setText(T("Python packages", "بسته‌های پایتون"))
            self.h_files.setText(T("Files", "فایل‌ها"))
            self.b_all.setText(T("Download all", "دانلود همه"))
            self.b_cancel.setText(T("Cancel all", "لغو همه"))
            self.where.setText(MODELS)
            self.b_open.setText(T("Open folder", "باز کردن پوشه"))
            self.b_close.setText(T("Close", "بستن"))
            self.sig = None
            self.refresh()

        def showEvent(self, e):
            self.timer.start(450)
            super().showEvent(e)

        def hideEvent(self, e):
            self.timer.stop()
            super().hideEvent(e)

        # ---- settings handlers
        def on_proxy(self):
            core.settings["proxy"] = self.proxy.text().strip()
            core.save_settings()

        def on_mirror(self):
            d = self.mirror.currentData()
            self.custom.setVisible(d == "custom")
            if d != "custom":
                core.settings["hf_host"] = d
                core.save_settings()

        def on_custom(self):
            v = self.custom.text().strip().rstrip("/")
            if v:
                core.settings["hf_host"] = v
                core.save_settings()

        def update_engine(self):
            core.dm.start(["engine", "engine-cpu"], force=True)

        def own_engine(self):
            p, _ = QFileDialog.getOpenFileName(self, T("Choose llama-server", "llama-server را انتخاب کنید"))
            if p:
                core.settings["engine_path"] = p
                core.save_settings()
                core.engine.stop()
                core.engine.forget_binary()
                core.on_files_changed()

        def run_test(self):
            self.test_out.setText(T("Testing… (up to a minute)", "در حال آزمایش… (حداکثر یک دقیقه)"))
            self.b_test.setEnabled(False)

            def done(res):
                self.b_test.setEnabled(True)
                if res[0] == "err":
                    self.test_out.setText(esc(res[1]))
                    return
                c = tok()
                lines = []
                for d in res[1]:
                    ok = d["ok"]
                    lines.append('<span style="color:%s">%s</span> <b>%s</b> — DNS: %s · %s · %d ms' % (
                        c["ok"] if ok else c["bad"], "✓" if ok else "✗", d["host"], esc(d["dns"]), esc(d["http"]), d["ms"]))
                self.test_out.setText("<br>".join(lines))
            bg(core.diagnose, done)

        def toggle_all(self):
            snap = core.dm.snapshot()
            if any(i["state"] in ("running", "queued") for i in snap):
                core.dm.pause_all()
            else:
                core.dm.resume_all()

        # ---- file rows
        def import_for(self, key):
            p, _ = QFileDialog.getOpenFileName(self, T("Choose the downloaded file", "فایل دانلودشده را انتخاب کنید"))
            if p:
                def done(res):
                    if res[0] == "err":
                        self.notify(res[1])
                bg(lambda: core.dm.import_file(key, p), done)

        def set_link(self, key):
            cur = (core.settings.get("custom_urls") or {}).get(key, "")
            txt, ok = QInputDialog.getText(self, T("Direct link", "پیوند مستقیم"),
                                           T("Paste a direct download link for this file (leave empty to remove):",
                                             "پیوند مستقیم دانلود این فایل را وارد کنید (برای حذف، خالی بگذارید):"), text=cur)
            if ok:
                d = dict(core.settings.get("custom_urls") or {})
                if txt.strip():
                    d[key] = txt.strip()
                else:
                    d.pop(key, None)
                core.settings["custom_urls"] = d
                core.save_settings()

        def copy_link(self, a):
            def done(res):
                if res[0] == "ok" and res[1]:
                    QApplication.clipboard().setText(res[1][-1] if a["kind"] == "engine" else res[1][0])
            bg(a["urls_fn"], done)

        def buttons_for(self, a, st):
            dm = core.dm
            k = a["key"]
            more = [(T("Import…", "وارد کردن…"), lambda: self.import_for(k)), (T("Link…", "پیوند…"), lambda: self.set_link(k)),
                    (T("Copy link", "کپی پیوند"), lambda: self.copy_link(a))]
            if st == "done":
                return []
            if st in ("running", "queued"):
                return [(T("Pause", "توقف"), lambda: dm.pause(k)), (T("Cancel", "لغو"), lambda: dm.cancel(k))]
            if st == "paused":
                return [(T("Resume", "ادامه"), lambda: dm.resume(k)), (T("Cancel", "لغو"), lambda: dm.cancel(k))]
            if st == "error":
                return [(T("Retry", "تلاش دوباره"), lambda: dm.resume(k))] + more
            return [(T("Download", "دانلود"), lambda: dm.start([k]))] + more

        def build_row(self, a, st):
            c = tok()
            fr = QFrame()
            fr.setObjectName("dlrow")
            v = QVBoxLayout(fr)
            v.setContentsMargins(12, 10, 12, 10)
            v.setSpacing(6)
            top = QHBoxLayout()
            ic = QLabel()
            ic.setPixmap(pix(svg_icon("check" if st == "done" else "download", c["ok"] if st == "done" else c["acc"]), 18))
            name = ElideLabel(a["title"] + ("  ·  " + os.path.basename(a["dest"]) if a["kind"] == "file" else ""))
            meta = QLabel()
            meta.setObjectName("mute")
            top.addWidget(ic)
            top.addWidget(name, 1)
            top.addWidget(meta)
            v.addLayout(top)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, 1000)
            v.addWidget(bar)
            note = QLabel()
            note.setWordWrap(True)
            note.setObjectName("mute")
            v.addWidget(note)
            btns = QHBoxLayout()
            btns.addStretch(1)
            for label, fn in self.buttons_for(a, st):
                b = QPushButton(label)
                b.clicked.connect(fn)
                btns.addWidget(b)
            v.addLayout(btns)
            return {"frame": fr, "meta": meta, "bar": bar, "note": note}

        def refresh(self):
            assets = core.assets()
            snap = {i["key"]: i for i in core.dm.snapshot()}
            rows = []
            for a in assets:
                it = snap.get(a["key"])
                st = "done" if core.asset_ok(a) else (it["state"] if it else "idle")
                rows.append((a, st, it))
            sig = (tuple((a["key"], st) for a, st, _ in rows), LANG, resolved_mode(),
                   tuple(core.sel(r) for r in CATALOG))
            if sig != self.sig:
                self.sig = sig
                while self.files_box.count():
                    w = self.files_box.takeAt(0).widget()
                    if w:
                        w.deleteLater()
                self.rows = {}
                for (a, st, it) in rows:
                    r = self.build_row(a, st)
                    self.files_box.addWidget(r["frame"])
                    self.rows[a["key"]] = r
                for role in ("embed", "gen", "rerank"):
                    e = core.model_entry(role)
                    self.role_v[role].setText("%s · %s" % (e["name"], fmt_size(e["size"])))
                    self.notes[role].setText(e["fa"] if LANG == "fa" else e["en"])
            state_txt = {"idle": T("Not downloaded", "دانلود نشده"), "queued": T("Waiting…", "در انتظار…"),
                         "paused": T("Paused", "متوقف"), "error": T("Failed", "ناموفق"),
                         "cancelled": T("Cancelled", "لغو شد"), "done": T("Ready", "آماده")}
            for (a, st, it) in rows:
                r = self.rows.get(a["key"])
                if not r:
                    continue
                if it and st in ("running", "queued", "paused", "error", "cancelled"):
                    tot = it["total"] or a["est"]
                    r["bar"].setValue(int(1000 * it["done"] / tot) if tot else 0)
                    if st == "running":
                        r["meta"].setText("%s / %s · %s/s · %s %s" % (fmt_size(it["done"]), fmt_size(tot), fmt_size(it["speed"]),
                                                                       fmt_eta(it["eta"]), T("left", "مانده")))
                        r["note"].setText(T("From ", "از ") + (it["host"] or "…"))
                    else:
                        r["meta"].setText("%s / %s · %s" % (fmt_size(it["done"]), fmt_size(tot), state_txt.get(st, st)))
                        r["note"].setText(loc(it["err"]) if st == "error" else "")
                elif st == "done":
                    r["bar"].setValue(1000)
                    sz = os.path.getsize(a["dest"]) if a["kind"] == "file" and os.path.exists(a["dest"]) else 0
                    r["meta"].setText(T("Ready", "آماده") + (" · " + fmt_size(sz) if sz else ""))
                    r["note"].setText("")
                else:
                    r["bar"].setValue(0)
                    r["meta"].setText("≈ %s · %s" % (fmt_size(a["est"]), state_txt["idle"]))
                    r["note"].setText("")
            busy = any(i["state"] in ("running", "queued") for i in snap.values())
            self.b_pause.setText(T("Pause all", "توقف همه") if busy else T("Resume all", "ادامه‌ی همه"))
            self.b_pause.setEnabled(any(i["state"] in ("running", "queued", "paused", "error") for i in snap.values()))
            self.b_cancel.setEnabled(any(i["state"] in ("running", "queued", "paused") for i in snap.values()))
            self.b_all.setEnabled(any(st in ("idle", "cancelled", "error") for _, st, _ in rows))
            ep = core.engine.binary()
            self.eng_l.setText((T("Engine: ", "موتور: ") + ep) if ep else T("Engine: not installed (download it below)", "موتور: نصب نشده (از پایین دانلود کنید)"))
            P = core.prog["pip"]
            fp = core.font_path()
            fok = os.path.isfile(fp) and os.path.getsize(fp) > 50_000
            applied = fok and FONT_STATE["loaded"]
            if applied:
                self.font_st.setText("✓ " + T("applied", "اعمال شد"))
            elif fok:
                self.font_st.setText(T("installed, not applied", "نصب شد، اعمال نشد"))
            else:
                self.font_st.setText(T("missing", "نصب نشده"))
            self.font_st.setProperty("kind", "ok" if fok else "warn")
            self.font_st.style().unpolish(self.font_st)
            self.font_st.style().polish(self.font_st)
            self.font_btn.setVisible(not fok)
            self.font_btn.setEnabled(True)
            if applied:
                self.font_note.setText(T("In use: ", "در حال استفاده: ") + FONT_STATE["family"])
            elif fok:
                self.font_note.setText(T("Reason: ", "دلیل: ") + (FONT_STATE["why"] or "?"))
            else:
                self.font_note.setText(T("Reason: ", "دلیل: ") + (core.font_err or T("not downloaded yet", "هنوز دانلود نشده")))
            for pk, (st, bt) in self.pkg_rows.items():
                ok = have_mod(pk)
                st.setText(("✓ " + T("installed", "نصب شد")) if ok else T("missing", "نصب نشده"))
                st.setProperty("kind", "ok" if ok else "warn")
                st.style().unpolish(st)
                st.style().polish(st)
                bt.setVisible(not ok)
                bt.setEnabled(not P["busy"])
            broken = [k for k in self.pkg_rows if not have_mod(k) and k in MOD_ERR]
            if P["busy"]:
                self.pkg_note.setText(T("Installing… ", "در حال نصب… ") + (P["log"] or ""))
            elif P["err"]:
                self.pkg_note.setText(T("Install failed: ", "نصب ناموفق: ") + P["err"])
            elif broken:
                self.pkg_note.setText(T("Installed but cannot be imported: ", "نصب شده اما وارد نمی‌شود: ") + MOD_ERR[broken[0]])
            else:
                self.pkg_note.setText(T("Installed into your user folder (no admin rights).", "در پوشه‌ی کاربر نصب می‌شود؛ به دسترسی مدیر نیاز ندارد."))

    def start_watchdog():
        """Writes data/slow.log whenever the window freezes for more than about 0.4 s, with the code that was running."""
        main_id = threading.get_ident()
        st = {"hb": time.time(), "last": 0.0}
        beat = QTimer()
        beat.timeout.connect(lambda: st.__setitem__("hb", time.time()))
        beat.start(50)
        keep.append(beat)

        def run():
            while True:
                time.sleep(0.15)
                gap = time.time() - st["hb"]
                if gap > 0.4 and time.time() - st["last"] > 1.5:
                    st["last"] = time.time()
                    fr = sys._current_frames().get(main_id)
                    stack = "".join(traceback.format_stack(fr)[-7:]) if fr else ""
                    try:
                        lp = os.path.join(DATA, "slow.log")
                        if os.path.exists(lp) and os.path.getsize(lp) > 200_000:
                            os.remove(lp)
                        with open(lp, "a", encoding="utf-8") as f:
                            f.write("[%s] window frozen for %.2fs\n%s\n" % (time.strftime("%H:%M:%S"), gap, stack))
                    except Exception:
                        pass
        threading.Thread(target=run, daemon=True).start()

    keep = []

    # main window
    class ChatDelegate(QStyledItemDelegate):
        """Chat history rows: bold title, muted date under it, a soft tint and an accent bar on the open chat."""
        ROW_H = 60
        ACTIONS = (("rename", "pencil"), ("export", "download"), ("delete", "trash"))

        def __init__(self, parent, on_action):
            super().__init__(parent)
            self.on_action = on_action
            self.swallow = False

        def sizeHint(self, opt, idx):
            if idx.data(Qt.ItemDataRole.UserRole + 3) == "header":
                return QSize(max(200, opt.rect.width()), 26)
            return QSize(max(200, opt.rect.width()), self.ROW_H)

        def action_rects(self, rect):
            """Where the row's icons sit: on the right, in the order rename, export, delete."""
            r = QRectF(rect).adjusted(4, 3, -4, -3)
            yc = r.center().y() - 8
            out = {}
            for i, (name, _icon) in enumerate(self.ACTIONS):
                x = r.right() - 12 - 16 - (len(self.ACTIONS) - 1 - i) * 26
                out[name] = QRectF(x, yc, 16, 16)
            return out

        def editorEvent(self, event, model, option, index):
            cid = index.data(Qt.ItemDataRole.UserRole)
            if cid is None:                                   # the empty-state hint has no actions
                return False
            # icons are only drawn on hovered or open rows, so a press on one of them is always meant for it
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                for name, rect in self.action_rects(option.rect).items():
                    if rect.adjusted(-5, -5, 5, 5).contains(QPointF(event.position())):
                        self.swallow = True             # the release belongs to this click, not to opening the chat
                        self.on_action(cid, name)
                        return True
            if event.type() == QEvent.Type.MouseButtonRelease and self.swallow:
                self.swallow = False
                return True
            return False

        def paint(self, p, opt, idx):
            c = tok()
            cid = idx.data(Qt.ItemDataRole.UserRole)
            title = idx.data(Qt.ItemDataRole.UserRole + 1) or ""
            when = idx.data(Qt.ItemDataRole.UserRole + 2) or ""
            hover_or_sel = bool(opt.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver))
            rtl = LANG == "fa" if idx.data(Qt.ItemDataRole.UserRole + 3) == "header" else bool(re.search(r"[\u0600-\u06FF]", title))     # aligned by the script of the title
            sel = bool(opt.state & QStyle.StateFlag.State_Selected)
            hov = bool(opt.state & QStyle.StateFlag.State_MouseOver)
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            if idx.data(Qt.ItemDataRole.UserRole + 3) == "header":     # group heading: Today, Yesterday, Earlier
                f = QFont(opt.font)
                f.setPointSize(8)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor(c["mute"]))
                align = (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignAbsolute
                p.drawText(QRectF(opt.rect).adjusted(14, 0, -14, 0), align | Qt.AlignmentFlag.AlignVCenter, title)
                p.restore()                               # balances the save at the top of paint
                return
            if cid is None:                                   # the empty-state hint
                f = QFont(opt.font)
                p.setFont(f)
                p.setPen(QColor(c["mute"]))
                p.drawText(QRectF(opt.rect).adjusted(12, 0, -12, 0),
                           Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, title)
                p.restore()
                return
            r = QRectF(opt.rect).adjusted(4, 3, -4, -3)
            if sel or hov:
                p.setPen(Qt.PenStyle.NoPen)
                if sel:
                    tint = QColor(c["acc"])
                    tint.setAlpha(60 if c.get("mode") == "dark" else 46)
                    p.setBrush(tint)
                else:
                    p.setBrush(QColor(c["hover"]))
                p.drawRoundedRect(r, 12, 12)
            if sel:                                           # accent bar on the open chat
                bar_x = r.right() - 4 if rtl else r.left() + 1
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(c["acc"]))
                p.drawRoundedRect(QRectF(bar_x, r.top() + 12, 3, r.height() - 24), 1.5, 1.5)
            inner = r.adjusted(16, 0, -16, 0)
            if hover_or_sel:                                  # leave room for the icons
                inner.setRight(inner.right() - len(self.ACTIONS) * 26 - 6)
            align = (Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignAbsolute
            tf = QFont(opt.font)
            tf.setPointSize(10)
            tf.setBold(sel)
            p.setFont(tf)
            p.setPen(QColor(c["ink"]))
            shown = QFontMetrics(tf).elidedText(title, Qt.TextElideMode.ElideRight, int(inner.width()))
            p.drawText(QRectF(inner.left(), inner.top() + 11, inner.width(), 22), align | Qt.AlignmentFlag.AlignVCenter, shown)
            df = QFont(opt.font)
            df.setPointSize(8)
            p.setFont(df)
            p.setPen(QColor(c["mute"]))
            p.drawText(QRectF(inner.left(), inner.top() + 33, inner.width(), 18), align | Qt.AlignmentFlag.AlignVCenter, when)
            if hover_or_sel:
                rects = self.action_rects(opt.rect)
                for name, icon in self.ACTIONS:
                    color = ("#ef4444" if c.get("mode") == "dark" else "#dc2626") if name == "delete" else c["mute"]
                    p.drawPixmap(rects[name].toRect(), pix(svg_icon(icon, color), 16))
            p.restore()

    class RowDelegate(QStyledItemDelegate):
        """Document-list rows: a taller row, a count pill on the right, and an accent edge on the selected row."""
        ROW_H = 34

        def sizeHint(self, opt, idx):
            s = super().sizeHint(opt, idx)
            s.setHeight(max(s.height(), self.ROW_H))
            return s

        def paint(self, p, opt, idx):
            try:
                c = tok()
                col = idx.column()
                data = idx.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole) or {}
                folder = data.get("k") in ("src", "dir")
                if col == 1:
                    super().paint(p, opt, idx)        # paint the normal row background first
                    txt = idx.data(Qt.ItemDataRole.DisplayRole) or ""
                    empty = data.get("status") == "empty"
                    p.save()
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    if folder:                        # folder counts are drawn as an accent pill
                        r = QRectF(opt.rect).adjusted(4, 8, -6, -8)
                        p.setPen(Qt.PenStyle.NoPen)
                        pill = QColor(c["acc"])
                        pill.setAlpha(64 if c.get("mode") == "dark" else 52)
                        p.setBrush(pill)
                        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
                    fg = QColor(c["warn"]) if empty else QColor(c["acc"] if folder else c["mute"])
                    p.setPen(fg)
                    f = QFont(opt.font)
                    f.setPointSize(max(8, f.pointSize() - 1))
                    p.setFont(f)
                    p.drawText(QRectF(opt.rect).adjusted(4, 0, -6, 0), Qt.AlignmentFlag.AlignCenter, txt)
                    p.restore()
                    return
                super().paint(p, opt, idx)
                if col == 0 and (opt.state & QStyle.StateFlag.State_Selected):
                    p.save()
                    bar = QRectF(opt.rect.right() - 2.5, opt.rect.top() + 7, 3, opt.rect.height() - 14) \
                        if qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft else \
                        QRectF(opt.rect.left(), opt.rect.top() + 7, 3, opt.rect.height() - 14)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(c["acc"]))
                    p.drawRoundedRect(bar, 1.5, 1.5)
                    p.restore()
            except Exception:
                traceback.print_exc()
                super().paint(p, opt, idx)

    class FileRowDelegate(QStyledItemDelegate):
        """Source and file rows, styled like chat rows: a bold name, a muted detail line, a soft highlight on hover
        or selection, and a trash icon at the end of the row. Folders and the count column keep their own look."""
        ROW_H = 46
        TRASH = 18

        def __init__(self, parent, on_action, pill):
            super().__init__(parent)
            self.on_action = on_action
            self.pill = pill
            self.swallow = False

        def _rtl(self):
            return qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft

        def _mirror(self, rect, bounds):
            """A rect as it sits in the row: mirrored in right-to-left layouts."""
            if not self._rtl():
                return rect
            return QRectF(bounds.right() - (rect.left() - bounds.left()) - rect.width(), rect.top(), rect.width(), rect.height())

        def check_rect(self, rect):
            """Where a file's checkbox is drawn, and where a click toggles it."""
            r = QRectF(rect).adjusted(4, 3, -4, -3)
            x = r.right() - 12 - 16 if self._rtl() else r.left() + 12
            return QRectF(x, r.center().y() - 8, 16, 16)

        def trash_rect(self, rect):
            r = QRectF(rect).adjusted(4, 3, -4, -3)
            x = r.left() + 10 if self._rtl() else r.right() - 10 - self.TRASH
            return QRectF(x, r.center().y() - self.TRASH / 2, self.TRASH, self.TRASH)

        def sizeHint(self, opt, idx):
            d = idx.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole) or {}
            if idx.column() == 1 or d.get("k") not in ("file", "src"):
                return self.pill.sizeHint(opt, idx)
            return QSize(opt.rect.width(), self.ROW_H)

        def paint(self, p, opt, idx):
            d = idx.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole) or {}
            if idx.column() == 1 or d.get("k") not in ("file", "src"):
                if idx.column() == 1 and not (idx.data(Qt.ItemDataRole.DisplayRole) or ""):
                    return                            # no count, no pill
                return self.pill.paint(p, opt, idx)
            c = tok()
            hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)
            sel = bool(opt.state & QStyle.StateFlag.State_Selected)
            row = QRectF(opt.rect).adjusted(4, 3, -4, -3)
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            if sel or hover:
                p.setPen(Qt.PenStyle.NoPen)
                tint = QColor(c["acc"])
                tint.setAlpha(60 if c.get("mode") == "dark" else 46)
                p.setBrush(tint if sel else QColor(c["hover"]))
                p.drawRoundedRect(row, 12, 12)
            if sel:
                bar = QRectF(row.right() - 4, row.top() + 12, 3, row.height() - 24) if self._rtl() else \
                      QRectF(row.left() + 1, row.top() + 12, 3, row.height() - 24)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(c["acc"]))
                p.drawRoundedRect(bar, 1.5, 1.5)
            ind = self.check_rect(opt.rect)
            if d.get("k") == "file" and d.get("path"):          # the core's selection is the truth, so the box always matches it
                state = Qt.CheckState.Checked if core.is_on(d["path"]) else Qt.CheckState.Unchecked
            else:
                state = idx.data(Qt.ItemDataRole.CheckStateRole)
            has_box = d.get("k") == "file"
            if has_box:
                p.setPen(QPen(QColor(c["mute"]), 1.2))
                p.setBrush(QColor(c["acc"]) if state == Qt.CheckState.Checked else QBrush(Qt.BrushStyle.NoBrush))
                p.drawRoundedRect(ind, 4, 4)
                if state == Qt.CheckState.Checked:
                    p.drawPixmap(ind.toRect().adjusted(2, 2, -2, -2), pix(svg_icon("check", "#ffffff"), 12))
            # the name and a detail line beside the checkbox
            if has_box:
                text_left = ind.right() + 10 if not self._rtl() else row.left() + 12
                text_right = (row.right() - 12) if not self._rtl() else (ind.left() - 10)
            else:
                text_left, text_right = row.left() + 12, row.right() - 12
            if sel or hover:
                if self._rtl():
                    text_left = row.left() + self.TRASH + 22
                else:
                    text_right = row.right() - self.TRASH - 22
            width = max(10.0, text_right - text_left)
            name = idx.data(Qt.ItemDataRole.DisplayRole) or ""
            fn = QFont(opt.font)
            fn.setPointSize(10)
            fn.setBold(d.get("k") == "src")
            p.setFont(fn)
            p.setPen(QColor(c["ink"]))
            shown = QFontMetrics(fn).elidedText(name, Qt.TextElideMode.ElideRight, int(width))
            align = (Qt.AlignmentFlag.AlignRight if self._rtl() else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignAbsolute
            p.drawText(QRectF(text_left, row.top() + 7, width, 18), align | Qt.AlignmentFlag.AlignVCenter, shown)
            detail = self._detail(d, idx)
            if detail:
                df = QFont(opt.font)
                df.setPointSize(8)
                p.setFont(df)
                p.setPen(QColor(c["mute"]))
                p.drawText(QRectF(text_left, row.top() + 25, width, 15), align | Qt.AlignmentFlag.AlignVCenter,
                           QFontMetrics(df).elidedText(detail, Qt.TextElideMode.ElideRight, int(width)))
            if (sel or hover) and d.get("k") in ("file", "src"):
                tr = self.trash_rect(opt.rect)
                p.drawPixmap(tr.toRect(), pix(svg_icon("trash", "#dc2626" if c.get("mode") != "dark" else "#ef4444"), self.TRASH))
            p.restore()

        def _detail(self, d, idx):
            if d.get("k") == "src":
                return T("Folder source", "منبع پوشه‌ای")
            name = idx.data(Qt.ItemDataRole.DisplayRole) or ""
            ext = name.rsplit(".", 1)[-1].upper() if "." in name else ""
            return ext

        def editorEvent(self, event, model, option, index):
            d = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole) or {}
            if index.column() == 0 and d.get("k") in ("file", "src"):
                if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    pos = QPointF(event.position())
                    if self.trash_rect(option.rect).adjusted(-5, -5, 5, 5).contains(pos):
                        self.swallow = True
                        self.on_action(d, "delete")
                        return True
                    if d.get("k") == "file" and self.check_rect(option.rect).adjusted(-5, -5, 5, 5).contains(pos):
                        core_on = core.is_on(d["path"]) if d.get("path") else False   # the core is the source of truth
                        _klog("ui.checkbox", path=d.get("path"), core_on=core_on, action="toggle")
                        self.on_action(d, "toggle")               # setData on the row did not change it, so the window toggles the core
                        self.swallow = True
                        return True
                if event.type() == QEvent.Type.MouseButtonRelease and self.swallow:
                    self.swallow = False
                    return True
            return super().editorEvent(event, model, option, index)

    class ThemedDialog(QDialog):
        """Base for the app's popups. It sets the window's colours itself, so it looks the same however it is opened."""

        def __init__(self, parent, title, width=420):
            super().__init__(parent)
            c = tok()
            self.setWindowTitle(title)
            self.setModal(True)
            self.setMinimumWidth(width)
            self.setStyleSheet(
                "QDialog{background:%s;}" % c["paper"] +
                "QLabel{color:%s;background:transparent;font-size:13px;}" % c["ink"] +
                "QLabel#popupTitle{font-size:15px;font-weight:700;}" +
                "QLabel#popupHint{color:%s;font-size:12px;}" % c["mute"] +
                "QLineEdit{background:%s;color:%s;border:1px solid %s;border-radius:9px;padding:8px 11px;}" % (c["soft"], c["ink"], c["line"]) +
                "QLineEdit:focus{border:1px solid %s;}" % c["acc"])
            self.lay = QVBoxLayout(self)
            self.lay.setContentsMargins(22, 20, 22, 18)
            self.lay.setSpacing(12)
            self.body = QVBoxLayout()
            self.body.setSpacing(8)
            self.btns = QHBoxLayout()
            self.btns.setSpacing(8)
            self.btns.addStretch(1)
            self.lay.addLayout(self.body)
            self.lay.addLayout(self.btns)

        def add_button(self, text, primary=False):
            b = QPushButton(text)
            if primary:
                b.setObjectName("primary")
                b.setDefault(True)
            self.btns.addWidget(b)
            return b

    class ChatNameDialog(ThemedDialog):
        """Renames a chat."""

        def __init__(self, parent, current):
            super().__init__(parent, T("Rename chat", "تغییر نام گفت‌وگو"))
            title = QLabel(T("Rename chat", "تغییر نام گفت‌وگو"))
            title.setObjectName("popupTitle")
            hint = QLabel(T("The name appears in the chat history list.", "نام در فهرست تاریخچه گفت‌وگو دیده می‌شود."))
            hint.setObjectName("popupHint")
            hint.setWordWrap(True)
            self.edit = QLineEdit(current or "")
            self.edit.setMaxLength(80)
            self.edit.setPlaceholderText(T("Chat name", "نام گفت‌وگو"))
            self.edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft if LANG == "fa" else Qt.LayoutDirection.LeftToRight)
            self.edit.returnPressed.connect(self.accept)
            cancel = self.add_button(T("Cancel", "انصراف"))
            cancel.clicked.connect(self.reject)
            save = self.add_button(T("Save", "ذخیره"), primary=True)
            save.clicked.connect(self.accept)
            self.body.addWidget(title)
            self.body.addWidget(hint)
            self.body.addWidget(self.edit)
            self.edit.setFocus()
            self.edit.selectAll()

        def value(self):
            return self.edit.text().strip()

    class EditQuestionDialog(ThemedDialog):
        """Edits a question. Saving asks it again and replaces the answers that followed it."""

        def __init__(self, parent, text):
            super().__init__(parent, T("Edit question", "ویرایش پرسش"), width=460)
            c = tok()
            self.setStyleSheet(self.styleSheet() + "QPlainTextEdit{background:%s;color:%s;border:1px solid %s;"
                               "border-radius:9px;padding:8px 11px;}QPlainTextEdit:focus{border:1px solid %s;}"
                               % (c["soft"], c["ink"], c["line"], c["acc"]))
            title = QLabel(T("Edit question", "ویرایش پرسش"))
            title.setObjectName("popupTitle")
            hint = QLabel(T("The answers after this question will be replaced.",
                            "پاسخ‌های بعد از این پرسش جایگزین می‌شوند."))
            hint.setObjectName("popupHint")
            hint.setWordWrap(True)
            self.edit = QPlainTextEdit(text)
            self.edit.setMinimumHeight(110)
            self.edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft if LANG == "fa" else Qt.LayoutDirection.LeftToRight)
            cancel = self.add_button(T("Cancel", "انصراف"))
            cancel.clicked.connect(self.reject)
            save = self.add_button(T("Send", "ارسال"), primary=True)
            save.clicked.connect(self.accept)
            self.body.addWidget(title)
            self.body.addWidget(hint)
            self.body.addWidget(self.edit)
            self.edit.setFocus()
            self.edit.moveCursor(QTextCursor.MoveOperation.End)

        def value(self):
            return self.edit.toPlainText().strip()

    class ThemedMessage(ThemedDialog):
        """A message with one or two buttons. Replaces the default message boxes."""

        def __init__(self, parent, text, ok_text, cancel_text=None, danger=False):
            super().__init__(parent, "Knowledge Bank")
            msg = QLabel(text)
            msg.setWordWrap(True)
            msg.setMinimumWidth(360)
            self.body.addWidget(msg)
            if cancel_text:
                cancel = self.add_button(cancel_text)
                cancel.clicked.connect(self.reject)
            ok = self.add_button(ok_text, primary=not danger)
            if danger:                                        # destructive actions get the warning colour
                c = tok()
                red = "#ef4444" if c.get("mode") == "dark" else "#dc2626"
                ok.setStyleSheet("QPushButton{background:%s;color:#ffffff;border:none;border-radius:9px;"
                                 "padding:8px 16px;font-weight:600;}" % red)
                ok.setDefault(True)
            ok.clicked.connect(self.accept)

    class Toast(QFrame):
        """A short message near the bottom of the window. It hides itself after a moment."""

        def __init__(self, parent):
            super().__init__(parent)
            self.setObjectName("toast")
            self.label = QLabel()
            self.label.setObjectName("toastText")
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay = QHBoxLayout(self)
            lay.setContentsMargins(18, 10, 18, 10)
            lay.addWidget(self.label)
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(24)
            shadow.setOffset(0, 6)
            shadow.setColor(QColor(0, 0, 0, 70))
            self.setGraphicsEffect(shadow)
            self.timer = QTimer(self)
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.hide)
            self.hide()

        def show_text(self, text, ms=2200):
            c = tok()
            self.setStyleSheet("QFrame#toast{background:%s;border:1px solid %s;border-radius:12px;}"
                               "QLabel#toastText{color:%s;font-size:13px;font-weight:600;background:transparent;}"
                               % (c["paper"], c["line"], c["ink"]))
            self.label.setText(text)
            self.label.setLayoutDirection(Qt.LayoutDirection.RightToLeft if LANG == "fa" else Qt.LayoutDirection.LeftToRight)
            self.adjustSize()
            parent = self.parentWidget()
            self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 130)   # above the composer
            self.raise_()
            self.show()
            self.timer.start(ms)

    class BubbleFitter(QObject):
        """Re-fits a question bubble when its conversation column changes size."""

        def __init__(self, fit):
            super().__init__()
            self.fit = fit

        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Type.Resize:
                self.fit()
            return False

    class Win(QMainWindow):
        def __init__(self):
            super().__init__()
            self.turns = []
            self.busy = False
            self.jobs = {}                      # chat id -> the turn whose answer is still being written
            self.search_busy = False
            self.tree_sig = None
            self.expanded = set()
            self.guard = False
            self.icon_widgets = []        # recoloured when the theme changes
            self.tune = None                  # the answer settings panel, created the first time it is used
            self.viewer = Viewer(self)
            self.dl = DlDialog(self)
            self.setAcceptDrops(True)
            self.resize(1280, 820)
            self.setMinimumSize(520, 560)
            self.build()
            self.restyle()
            self.texts()
            bridge.delta.connect(self.on_delta)
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.tick)
            self.timer.start(700)
            self.anim_phase = 0
            self.caret_on = True
            self.anim_timer = QTimer(self)                 # blinks the caret and animates the dots while an answer is written
            self.anim_timer.timeout.connect(self.animate)
            self.anim_timer.start(420)
            self.last_dirty = -1
            self.tick()
            self.render_all()
            try:
                hints.colorSchemeChanged.connect(lambda *_: self.on_system_scheme())
            except Exception:
                pass
            QTimer.singleShot(900, self.on_system_scheme)
            QTimer.singleShot(3000, self.on_system_scheme)
            start_watchdog()

        # ---------- helpers
        def reg_icon(self, w, name, role="ink"):
            self.icon_widgets.append((w, name, role))
            return w

        def mk_btn(self, text="", icon_name=None, obj=None, role=None, tip=None):
            b = QPushButton(text)
            b.setAccessibleName(text or tip or icon_name or "")   # screen readers read this for icon-only buttons
            if tip:
                b.setToolTip(tip)
            if obj:
                b.setObjectName(obj)
            if icon_name:
                self.reg_icon(b, icon_name, role or ("accink" if obj == "primary" else "ink"))
                b.setIconSize(QSize(16, 16))
            if tip:
                b.setToolTip(tip)
            return b

        def mk_card(self, icon_name, title_attr):
            f = QFrame()
            f.setObjectName("card")
            lay = QVBoxLayout(f)
            lay.setContentsMargins(14, 12, 14, 14)
            lay.setSpacing(8)
            head = QHBoxLayout()
            ic = QLabel()
            self.reg_icon(ic, icon_name, "acc")
            t = QLabel()
            t.setObjectName("cardTitle")
            setattr(self, title_attr, t)
            head.addWidget(ic)
            head.addWidget(t)
            head.addStretch(1)
            lay.addLayout(head)
            return f, lay, head

        def mk_badge(self, kind=""):
            b = QLabel()
            b.setObjectName("badge")
            b.setProperty("kind", kind)
            return b

        def set_kind(self, w, kind):
            if w.property("kind") != kind:
                w.setProperty("kind", kind)
                w.style().unpolish(w)
                w.style().polish(w)

        def restyle(self):
            c = apply_theme()
            self._last_mode = c["mode"]
            for (w, name, role) in self.icon_widgets:
                col = c[role] if role in c else c["ink"]
                if isinstance(w, QLabel):
                    w.setPixmap(pix(svg_icon(name, col), 18))
                else:
                    w.setIcon(icon(name, col, 16))
            self.logo.setPixmap(pix(svg_icon("logo", c["accink"]), 22))
            self.hero.setPixmap(pix(svg_icon("docs", c["acc"]), 30))
            for n, b in self.swatches.items():
                b.setStyleSheet("QPushButton{background:%s;border:2px solid %s;border-radius:10px;padding:0}"
                                "QPushButton:hover{border-color:%s}" % (ACCENTS[n][4], c["ink"] if core.settings.get("accent") == n else c["paper"], c["mute"]))
            for m, b in self.theme_btns.items():
                b.setChecked(core.settings.get("theme", "system") == m)
            self.viewer.restyle()
            self.tree_sig = None
            self.render_all()
            self.dl.sig = None

        def resizeEvent(self, e):
            """Adaptive layout: the sidebar folds away on narrow windows and comes back when there is room."""
            super().resizeEvent(e)
            wide = self.width() >= 1000
            if wide != getattr(self, "_wide", None):
                self._wide = wide
                if not getattr(self, "_side_user_hidden", False):
                    self.side.setVisible(wide)
                    self.show_side.setVisible(not wide)

        def on_system_scheme(self):
            if core.settings.get("theme", "system") == "system":
                if getattr(self, "_last_mode", None) != resolved_mode():
                    self._last_mode = resolved_mode()
                    self.restyle()

        # ---------- layout
        def build(self):
            split = QSplitter()
            split.setChildrenCollapsible(False)
            self.setCentralWidget(split)
            self.split = split
            # --- sidebar
            self.side = QScrollArea()
            self.side.setObjectName("sideScroll")
            self.side.setWidgetResizable(True)
            self.side.setFrameShape(QFrame.Shape.NoFrame)
            self.side.setMinimumWidth(300)
            self.side.setMaximumWidth(400)
            self.side.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            inner = QWidget()
            inner.setObjectName("sideInner")
            inner.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)   # keep in step with the panel width
            sl = QVBoxLayout(inner)
            sl.setContentsMargins(14, 14, 14, 14)
            sl.setSpacing(12)
            head = QHBoxLayout()
            self.logo = QLabel()
            self.logo.setObjectName("logo")
            self.logo.setFixedSize(40, 40)
            self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tv = QVBoxLayout()
            tv.setSpacing(0)
            self.title = QLabel()
            self.title.setObjectName("appTitle")
            self.tagline = QLabel()
            self.tagline.setObjectName("mute")
            self.tagline.setWordWrap(True)
            tv.addWidget(self.title)
            tv.addWidget(self.tagline)
            self.hide_side = QToolButton()
            self.reg_icon(self.hide_side, "chevron-right" if LANG == "fa" else "chevron-left", "mute")
            self.hide_side.clicked.connect(lambda: (setattr(self, "_side_user_hidden", True), self.side.setVisible(False), self.show_side.setVisible(True)))
            head.addWidget(self.logo)
            head.addLayout(tv, 1)
            head.addWidget(self.hide_side)
            sl.addLayout(head)
            chat_card = QWidget()
            cl = QVBoxLayout(chat_card)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(6)
            self.chat_title_lbl = QLabel()
            self.chat_title_lbl.setObjectName("cardTitle")
            cl.addWidget(self.chat_title_lbl)
            self.chat_new = self.mk_btn("", "file", "primary")
            self.chat_new.clicked.connect(self.new_chat)
            cl.addWidget(self.chat_new)
            self.chat_search = QLineEdit()
            self.chat_search.setClearButtonEnabled(True)
            self.chat_search.textChanged.connect(lambda _t: self.refresh_chat_box())
            cl.addWidget(self.chat_search)
            self.chat_list = QListWidget()
            self.chat_list.setMinimumHeight(200)
            self.chat_list.setFrameShape(QFrame.Shape.NoFrame)
            self.chat_list.setSpacing(2)
            self.chat_list.setMouseTracking(True)
            self.chat_list.setStyleSheet("QListWidget{background:transparent;border:none;outline:0}")
            self.chat_list.setItemDelegate(ChatDelegate(self.chat_list, self.chat_action))
            self.chat_list.itemClicked.connect(lambda it: self.on_chat_picked(it.data(Qt.ItemDataRole.UserRole)))
            self.chat_list.itemActivated.connect(lambda it: self.on_chat_picked(it.data(Qt.ItemDataRole.UserRole)))
            cl.addWidget(self.chat_list)
            sl.addWidget(chat_card)
            # toolbar: theme switch, language, accent swatches
            tb = FlowLayout(6, 6)
            seg = QFrame()
            seg.setObjectName("seg")
            sg = QHBoxLayout(seg)
            sg.setContentsMargins(3, 3, 3, 3)
            sg.setSpacing(2)
            self.theme_btns = {}
            grp = QButtonGroup(self)
            grp.setExclusive(True)
            for m, ic in (("light", "sun"), ("system", "monitor"), ("dark", "moon")):
                b = QToolButton()
                b.setCheckable(True)
                self.reg_icon(b, ic, "ink")
                b.clicked.connect(lambda _=False, mm=m: self.on_theme(mm))
                grp.addButton(b)
                sg.addWidget(b)
                self.theme_btns[m] = b
            self.lang_cb = QComboBox()
            self.lang_cb.addItem("فارسی", "fa")
            self.lang_cb.addItem("English", "en")
            self.lang_cb.setCurrentIndex(0 if LANG == "fa" else 1)
            self.lang_cb.currentIndexChanged.connect(self.on_lang)
            tb.addWidget(seg)
            tb.addWidget(self.lang_cb)
            self.swatches = {}
            for n in ACCENTS:
                b = QPushButton()
                b.setFixedSize(20, 20)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _=False, nn=n: self.on_accent(nn))
                tb.addWidget(b)
                self.swatches[n] = b
            sl.addLayout(tb)
            self.lib_title = QLabel()
            self.lib_title.setObjectName("cardTitle")
            sl.addWidget(self.lib_title)
            sl.addStretch(1)                                  # keeps the controls above at the top
            # data chip
            chip = QFrame()
            chip.setObjectName("chipbar")
            ch = QHBoxLayout(chip)
            ch.setContentsMargins(10, 6, 10, 6)
            dbi = QLabel()
            self.reg_icon(dbi, "db", "mute")
            dl = QLabel("./data")
            dl.setStyleSheet("font-family:monospace")
            self.py_badge = self.mk_badge()
            ch.addWidget(dbi)
            ch.addWidget(dl)
            ch.addStretch(1)
            ch.addWidget(self.py_badge)
            sl.addWidget(chip)
            # sources card
            c1, l1, h1 = self.mk_card("layers", "h_src")
            self.watch = self.mk_badge("ok")
            h1.addWidget(self.watch)
            self.hint_src = QLabel()
            self.hint_src.setObjectName("mute")
            self.hint_src.setWordWrap(True)
            l1.addWidget(self.hint_src)
            br = QHBoxLayout()
            self.b_dir = self.mk_btn("", "folder-plus", "primary")
            self.b_files = self.mk_btn("", "file-plus")
            self.b_sync = self.mk_btn("", "refresh")
            self.b_dir.clicked.connect(self.add_dir)
            self.b_files.clicked.connect(self.add_files)
            self.b_sync.clicked.connect(self.do_sync)
            br.addWidget(self.b_dir, 1)
            br.addWidget(self.b_files, 1)
            br.addWidget(self.b_sync)
            l1.addLayout(br)
            self.tree = QTreeWidget()
            self.tree.setColumnCount(2)
            self.tree.setHeaderHidden(True)
            self.tree.setIconSize(QSize(20, 20))
            self.tree.setIndentation(14)
            self.tree.setUniformRowHeights(True)
            self.tree.setExpandsOnDoubleClick(False)
            self.tree.setMinimumHeight(220)
            hd = self.tree.header()
            hd.setStretchLastSection(False)
            hd.setSectionResizeMode(0, hd.ResizeMode.Stretch)
            hd.setSectionResizeMode(1, hd.ResizeMode.Fixed)
            self.tree.setColumnWidth(1, 52)
            self.tree.setMouseTracking(True)
            self.tree.setItemDelegate(FileRowDelegate(self.tree, self.row_action, RowDelegate(self.tree)))
            self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)   # the row has to fit the sidebar
            self.tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
            self.tree.itemExpanded.connect(self.on_expand)
            self.tree.itemCollapsed.connect(self.on_collapse)
            self.tree.itemChanged.connect(self.on_item_changed)
            self.tree.itemDoubleClicked.connect(self.on_dbl)
            l1.addWidget(self.tree, 1)
            self.note_lib = QLabel()
            self.note_lib.setObjectName("mute")
            self.note_lib.setWordWrap(True)
            l1.addWidget(self.note_lib)
            sl.addWidget(c1, 1)
            # meaning card
            c2, l2, h2 = self.mk_card("sparkle", "h_mean")
            self.mean_badge = self.mk_badge()
            self.mean_badge.setMinimumWidth(78)                                              # leaves space for "100%"
            h2.addWidget(self.mean_badge)
            self.hint_mean = QLabel()
            self.hint_mean.setObjectName("mute")
            self.hint_mean.setWordWrap(True)
            l2.addWidget(self.hint_mean)
            sr = QHBoxLayout()
            self.mean_dot = QLabel()
            self.mean_dot.setObjectName("dot")
            self.mean_state = QLabel()
            line_h = max(16, int(QFontMetrics(self.font()).height()))
            self.mean_state.setMinimumHeight(3 * line_h + 4)   # leaves space for three lines
            self.mean_state.setWordWrap(True)
            sr.addWidget(self.mean_dot, 0, Qt.AlignmentFlag.AlignTop)
            sr.addWidget(self.mean_state, 1)
            l2.addLayout(sr)
            self.mean_bar = QProgressBar()
            self.mean_bar.setTextVisible(False)
            self.mean_bar.setRange(0, 1000)
            l2.addWidget(self.mean_bar)
            mr = QHBoxLayout()
            self.b_mean = self.mk_btn("", "sparkle", "primary")
            self.b_pause = self.mk_btn("", "pause")
            self.b_mean.clicked.connect(self.build_meaning)
            self.b_pause.clicked.connect(self.toggle_pause)
            mr.addWidget(self.b_mean, 1)
            mr.addWidget(self.b_pause)
            l2.addLayout(mr)
            sl.addWidget(c2)
            # data files card
            c3, l3, h3 = self.mk_card("download", "h_data")
            self.hint_data = QLabel()
            self.hint_data.setObjectName("mute")
            self.hint_data.setWordWrap(True)
            l3.addWidget(self.hint_data)
            self.rows = {}
            for comp in ("embed", "gen", "rerank"):
                r = QHBoxLayout()
                nm = QLabel()
                badge = self.mk_badge()
                b = self.mk_btn("", "download")
                b.clicked.connect(lambda _=False, cc=comp: self.comp_action(cc))
                r.addWidget(nm, 1)
                r.addWidget(badge)
                r.addWidget(b)
                l3.addLayout(r)
                self.rows[comp] = (nm, badge, b)
            self.dl_bar = QProgressBar()
            self.dl_bar.setTextVisible(False)
            self.dl_bar.setRange(0, 1000)
            l3.addWidget(self.dl_bar)
            self.note_dl = QLabel()
            self.note_dl.setObjectName("mute")
            self.note_dl.setWordWrap(True)
            l3.addWidget(self.note_dl)
            self.ai_chk = QCheckBox()
            self.ai_chk.toggled.connect(self.on_ai)
            l3.addWidget(self.ai_chk)

            self.b_manage = self.mk_btn("", "sliders")
            self.b_manage.clicked.connect(self.open_dl)
            l3.addWidget(self.b_manage)
            sl.addWidget(c3)
            # developer card: label, name, links, version
            c4 = QFrame()
            c4.setObjectName("card")
            l4 = QVBoxLayout(c4)
            l4.setContentsMargins(14, 12, 14, 12)
            l4.setSpacing(6)
            self.dev_label = QLabel()
            self.dev_label.setObjectName("devlabel")
            self.dev_name = QLabel("Shayan Rahmati")
            self.dev_name.setObjectName("cardTitle")
            l4.addWidget(self.dev_label)
            l4.addWidget(self.dev_name)
            fl = FlowLayout(6, 6)
            for (ic, text, url) in DEV_LINKS:
                b = self.mk_btn(text, ic, "link", "ink", url)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
                fl.addWidget(b)
            l4.addLayout(fl)
            self.ver = QLabel()
            self.ver.setObjectName("devver")
            l4.addWidget(self.ver)
            sl.addWidget(c4)
            self.side.setWidget(inner)
            # --- main area
            main = QWidget()
            main.setObjectName("mainArea")
            ml = QVBoxLayout(main)
            ml.setContentsMargins(16, 12, 16, 14)
            ml.setSpacing(10)
            tr = QHBoxLayout()
            self.show_side = QToolButton()
            self.reg_icon(self.show_side, "menu", "ink")
            self.show_side.setVisible(False)
            self.show_side.clicked.connect(lambda: (setattr(self, "_side_user_hidden", False), self.side.setVisible(True), self.show_side.setVisible(False)))
            self.stat = self.mk_badge()
            self.tune_b = self.mk_btn("", "sliders")
            self.tune_b.clicked.connect(self.open_tune)
            tr.addWidget(self.show_side)
            tr.addWidget(self.stat)
            tr.addStretch(1)
            tr.addWidget(self.tune_b)
            ml.addLayout(tr)
            self.scroll = QScrollArea()
            self.scroll.setObjectName("threadScroll")
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QFrame.Shape.NoFrame)
            wrap = QWidget()
            wrap.setObjectName("threadWrap")
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(0, 0, 0, 0)
            self.thread_in = QWidget()
            self.thread_in.setObjectName("threadIn")
            self.thread_in.setMaximumWidth(860)
            self.tl = QVBoxLayout(self.thread_in)
            self.tl.setContentsMargins(4, 0, 4, 0)
            self.tl.setSpacing(6)
            wl.addStretch(1)
            wl.addWidget(self.thread_in, 100)
            wl.addStretch(1)
            self.scroll.setWidget(wrap)
            ml.addWidget(self.scroll, 1)
            # empty state
            self.empty = QWidget()
            ev = QVBoxLayout(self.empty)
            ev.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ev.setSpacing(10)
            self.hero = QLabel()
            self.hero.setObjectName("heroIcon")
            self.hero.setFixedSize(84, 84)
            self.hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.empty_t = QLabel()
            self.empty_t.setObjectName("appTitle")
            self.empty_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.empty_s = QLabel()
            self.empty_s.setObjectName("mute")
            self.empty_s.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.empty_s.setWordWrap(True)
            er = QHBoxLayout()
            self.e_dir = self.mk_btn("", "folder-plus", "primary")
            self.e_files = self.mk_btn("", "file-plus")
            self.e_dir.clicked.connect(self.add_dir)
            self.e_files.clicked.connect(self.add_files)
            er.addStretch(1)
            er.addWidget(self.e_dir)
            er.addWidget(self.e_files)
            er.addStretch(1)
            self.starter_row = QHBoxLayout()
            self.starter_row.setSpacing(8)
            self.starter_row.addStretch(1)
            self.starter_btns = []
            for en_text, fa_text in STARTERS:
                sb = QPushButton()
                sb.clicked.connect(lambda _=False, b=sb: self.use_starter(b.text()))
                self.starter_btns.append((sb, en_text, fa_text))
                self.starter_row.addWidget(sb)
            self.starter_row.addStretch(1)
            self.empty_meta = QLabel()
            self.empty_meta.setObjectName("mute")
            self.empty_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ev.addStretch(1)
            ev.addWidget(self.hero, 0, Qt.AlignmentFlag.AlignCenter)
            ev.addWidget(self.empty_t)
            ev.addWidget(self.empty_s)
            ev.addLayout(er)
            ev.addLayout(self.starter_row)
            ev.addWidget(self.empty_meta)
            ev.addStretch(2)
            self.tl.addWidget(self.empty)
            self.tl.addStretch(1)
            # composer
            comp = QFrame()
            comp.setObjectName("composer")
            cl = QVBoxLayout(comp)
            cl.setContentsMargins(10, 6, 10, 8)
            cl.setSpacing(4)
            self.q = Composer()
            self.q.asked.connect(self.do_ask)
            cl.addWidget(self.q)
            br2 = QHBoxLayout()
            self.hint_keys = QLabel()
            self.hint_keys.setObjectName("mute")
            self.b_ask = self.mk_btn("", "send", "sendBtn", "accink")
            self.b_ask.clicked.connect(lambda _=False: self.do_ask())
            self.b_stop = self.mk_btn("", "stop", "stopBtn", "acc")
            self.b_stop.clicked.connect(lambda _=False: core.abort_generation())
            self.b_stop.setVisible(False)
            self.smart_chk = QPushButton()
            self.smart_chk.setCheckable(True)
            self.smart_chk.setObjectName("chipToggle")
            self.smart_chk.setToolTip(T("When on, answers are written by the AI model. When off, you get the passages.",
                                        "با روشن بودن، پاسخ را مدل هوشمند می‌نویسد. با خاموش بودن، بندهای مرتبط نشان داده می‌شوند."))
            self.smart_chk.toggled.connect(self.on_smart)
            self.grounded_box = QPushButton()
            self.grounded_box.setCheckable(True)
            self.grounded_box.setObjectName("chipToggle")
            self.grounded_box.setChecked(bool(core.settings.get("grounded", True)))
            self.grounded_box.setText(T("Based on sources", "بر اساس منابع"))
            self.grounded_box.setToolTip(T("On: answers come only from your passages. Off: the model may also answer from its own knowledge.",
                                           "روشن: پاسخ فقط از بندهای شما می‌آید. خاموش: مدل می‌تواند از دانش خودش هم پاسخ دهد."))
            self.grounded_box.toggled.connect(self.toggle_grounded)
            br2.addWidget(self.smart_chk)
            br2.addWidget(self.grounded_box)
            br2.addStretch(1)
            br2.addWidget(self.b_ask)
            br2.addWidget(self.b_stop)
            cl.addLayout(br2)
            cw = QHBoxLayout()
            cw.addStretch(1)
            comp.setMaximumWidth(860)
            cw.addWidget(comp, 100)
            cw.addStretch(1)
            ml.addLayout(cw)
            split.addWidget(self.side)
            split.addWidget(main)
            split.setStretchFactor(0, 0)
            split.setStretchFactor(1, 1)
            split.setSizes([340, 940])

        def texts(self):
            qapp.setLayoutDirection(Qt.LayoutDirection.RightToLeft if LANG == "fa" else Qt.LayoutDirection.LeftToRight)
            self.setWindowTitle(T("Knowledge Bank", "بانک دانش"))
            self.title.setText(T("Knowledge Bank", "بانک دانش"))
            self.tagline.setText(T("Private, offline answers from your own documents", "پاسخ خصوصی و بدون اینترنت از اسناد خودتان"))
            for m, (en, fa) in {"light": ("Light", "روشن"), "system": ("System", "سیستم"), "dark": ("Dark", "تیره")}.items():
                self.theme_btns[m].setToolTip(T(en, fa))
            for n, (en, fa) in {"blue": ("Blue", "آبی"), "violet": ("Violet", "بنفش"), "teal": ("Teal", "فیروزه‌ای"),
                                "green": ("Green", "سبز"), "amber": ("Amber", "کهربایی"), "rose": ("Rose", "گل‌رز")}.items():
                self.swatches[n].setToolTip(T(en, fa))
                self.swatches[n].setAccessibleName(T("Accent: ", "رنگ اصلی: ") + T(en, fa))
            self.hide_side.setToolTip(T("Hide sidebar", "پنهان‌کردن نوار کناری"))
            arrow = "chevron-right" if LANG == "fa" else "chevron-left"
            for k, (w, name, role) in enumerate(self.icon_widgets):
                if w is self.hide_side:
                    self.icon_widgets[k] = (w, arrow, role)
            self.hide_side.setIcon(icon(arrow, tok()["mute"], 16))
            self.show_side.setToolTip(T("Show sidebar", "نمایش نوار کناری"))
            self.h_src.setText(T("Sources", "منابع"))
            self.hint_src.setText(T("Folders and files are read straight from disk. Changes are noticed automatically. You can also drop them onto this window.",
                                    "پوشه‌ها و فایل‌ها مستقیم از دیسک خوانده می‌شوند و تغییراتشان خودکار دیده می‌شود. می‌توانید پوشه‌ها را روی همین پنجره بکشید و رها کنید."))
            self.b_dir.setText(T("Add folder", "افزودن پوشه"))
            self.b_files.setText(T("Add files", "افزودن فایل"))
            self.b_sync.setToolTip(T("Rescan now", "بررسی دوباره"))
            self.h_mean.setText(T("Meaning search", "جست‌وجوی معنایی"))
            self.hint_mean.setText(T("Finds passages by meaning, even when the words differ.", "بندها را بر اساس معنا پیدا می‌کند، حتی با واژه‌های متفاوت."))
            self.b_mean.setText(T("Build meaning index", "ساخت نمایه‌ی معنایی"))
            self.h_data.setText(T("Data files", "فایل‌های داده"))
            self.hint_data.setText(T("Downloaded once; after that everything works offline.", "یک‌بار دانلود می‌شوند؛ بعد از آن بدون اینترنت کار می‌کند."))
            self.rows["embed"][0].setText(T("Meaning search", "جست‌وجوی معنایی"))
            self.rows["gen"][0].setText(T("AI answers", "پاسخ هوشمند"))
            self.rows["rerank"][0].setText(T("Passage ranking", "رتبه‌بندی بندها"))
            self.ai_chk.setText(T("Write an AI answer for every question", "نوشتن پاسخ هوشمند برای هر پرسش"))
            self.smart_chk.setText(T("Smart answer", "پاسخ هوشمند"))
            self.grounded_box.setText(T("Based on sources", "بر اساس منابع"))
            self.grounded_box.setToolTip(T("On: answers come only from your passages. Off: the model may also answer from its own knowledge.",
                                           "روشن: پاسخ فقط از بندهای شما می‌آید. خاموش: مدل می‌تواند از دانش خودش هم پاسخ دهد."))
            self.tune_b.setText(T("Answer settings", "تنظیمات پاسخ"))
            self.tune_b.setToolTip(T("Choose how long answers are", "طول پاسخ‌ها را انتخاب کنید"))
            self.b_manage.setText(T("Downloads & packages…", "دانلودها و بسته‌ها…"))
            self.dev_label.setText(T("Crafted by", "ساخته‌شده توسط"))
            self.ver.setText("Knowledge Bank · v" + VERSION)
            self.lib_title.setText(T("Library", "کتابخانه"))
            self.e_dir.setText(T("Add folder", "افزودن پوشه"))
            self.e_files.setText(T("Add files", "افزودن فایل"))
            for sb, en_text, fa_text in self.starter_btns:
                sb.setText(T(en_text, fa_text))
            self.chat_title_lbl.setText(T("Chat history", "تاریخچه گفت‌وگو"))
            self.chat_new.setText(T("New chat", "گفت‌وگوی تازه"))
            self.chat_new.setToolTip(T("New chat", "گفت‌وگوی تازه"))
            self.chat_search.setPlaceholderText(T("Search chats", "جست‌وجوی گفت‌وگوها"))
            self.chat_list.setToolTip(T("Saved chats, newest first", "گفت‌وگوهای ذخیره‌شده، جدیدترین اول"))
            self.refresh_chat_box()
            self.q.setPlaceholderText("")          # the empty-state heading already says this
            self.b_ask.setToolTip(T("Send (Enter)", "ارسال (Enter)"))
            self.b_stop.setToolTip(T("Stop answer", "توقف پاسخ"))
            self.hint_keys.setText(T("Enter = ask  ·  Shift+Enter = new line", "Enter = پرسش  ·  Shift+Enter = خط تازه"))
            self.q.setToolTip(self.hint_keys.text())
            self.empty_t.setText(T("Ask your documents anything", "از اسنادتان بپرسید"))
            self.empty_s.setText(T("Add a folder, then ask a question or search for a word.", "یک پوشه اضافه کنید و بعد سؤال بپرسید، یا واژه‌ای را جست‌وجو کنید."))
            self.e_dir.setText(T("Add folder", "افزودن پوشه"))
            self.e_files.setText(T("Add files", "افزودن فایل"))
            self.empty_meta.setText(T("Everything stays on this computer.", "همه‌چیز روی همین رایانه می‌ماند."))
            self.watch.setText(T("watching", "پایش"))
            self.dl.texts()
            self.q.adjust()

        def on_lang(self):
            global LANG
            LANG = self.lang_cb.currentData()
            core.settings["lang"] = LANG
            core.save_settings()
            self.texts()
            self.viewer.restyle()
            self.tree_sig = None
            self.tick()
            self.render_all()

        def on_theme(self, m):
            core.settings["theme"] = m
            core.save_settings()
            self._last_mode = resolved_mode()
            self.restyle()

        def on_accent(self, n):
            core.settings["accent"] = n
            core.save_settings()
            self.restyle()

        def set_answer_length(self, key):
            core.settings["answer_length"] = key
            core.save_settings()

        def open_tune(self):
            if self.tune is None:
                self.tune = TuneDialog(self)
            self.tune.refresh()
            self.tune.show()
            self.tune.raise_()

        def on_ai(self, on):
            core.settings["ai"] = bool(on)
            core.save_settings()
            self.sync_smart()

        def toggle_grounded(self, on):
            """The 'Based on sources' checkbox in the prompt section. Saved and logged like the other answer settings."""
            if not on and not core.settings.get("ai", True):
                self.keep_one_on(self.grounded_box)
                return
            core.settings["grounded"] = bool(on)
            core.save_settings()
            from kb_log import log as _klog
            _klog("settings.change", key="grounded", value=bool(on))

        def keep_one_on(self, box):
            """Smart answer and Based on sources cannot both be off: the box the user just cleared is ticked again."""
            box.blockSignals(True)
            box.setChecked(True)
            box.blockSignals(False)
            self.notify(T("Smart answer and Based on sources cannot both be off.",
                          "پاسخ هوشمند و بر اساس منابع نمی‌توانند همزمان خاموش باشند."))

        def on_smart(self, on):
            """The Smart answer switch in the prompt section. It is the same setting as AI answers in Answer settings."""
            if not on and not core.settings.get("grounded", True):
                self.keep_one_on(self.smart_chk)
                return
            core.settings["ai"] = bool(on)
            core.save_settings()
            self.sync_smart()
            self.toast(T("Smart answers on", "پاسخ هوشمند روشن است") if on else
                       T("Smart answers off: you get the passages", "پاسخ هوشمند خاموش است: بندها نشان داده می‌شوند"))

        def sync_smart(self):
            """Keeps the prompt switch and the settings checkbox showing the current setting."""
            on = bool(core.settings.get("ai"))
            for box in (self.smart_chk, self.ai_chk):
                box.blockSignals(True)
                box.setChecked(on)
                box.blockSignals(False)

        def open_dl(self):
            self.dl.show()
            self.dl.raise_()
            self.dl.activateWindow()

        # ---------- drag and drop
        def dragEnterEvent(self, e):
            if e.mimeData().hasUrls():
                e.acceptProposedAction()

        def dropEvent(self, e):
            ps = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            if ps:
                self.add_paths(ps)

        # ---------- sources
        def add_paths(self, paths):
            added = False
            for p in paths:
                try:
                    core.add_source(p)
                    added = True
                except Exception as e:
                    self.notify(str(e))
            if added:
                self.tree_sig = None
                threading.Thread(target=core.sync, daemon=True).start()

        def add_dir(self):
            p = QFileDialog.getExistingDirectory(self, T("Choose a folder", "یک پوشه انتخاب کنید"))
            if p:
                self.add_paths([p])

        def add_files(self):
            flt = "Documents (%s);;All files (*)" % " ".join("*." + e for e in sorted(READ_EXT))
            ps, _ = QFileDialog.getOpenFileNames(self, T("Choose files", "فایل‌ها را انتخاب کنید"), "", flt)
            if ps:
                self.add_paths(ps)

        def do_sync(self):
            threading.Thread(target=lambda: core.sync(force=True), daemon=True).start()

        def row_action(self, d, name):
            if name == "toggle":
                path = d.get("path")
                if not path:
                    return
                now_on = core.is_on(path)
                _klog("ui.toggle", path=path, was_on=now_on, now_on=not now_on)
                core.set_sel(path, not now_on)
                QTimer.singleShot(0, self.rebuild_tree)
                return
            if name != "delete":
                return
            if d.get("k") == "file":
                self.remove_file_row(d)
            elif d.get("k") == "src":
                self.remove_source_row(d)

        def remove_file_row(self, d):
            if not self.confirm(T("Remove this file from the bank? The file on disk is not touched.",
                                  "این فایل از بانک حذف شود؟ فایل روی دیسک دست‌نخورده می‌ماند."),
                                T("Remove", "حذف"), T("Cancel", "انصراف"), danger=True):
                return
            core.forget_file(d["path"])               # wipes the file's text, chunks and meaning vectors, and its list entry
            self.tree_sig = None
            self.toast(T("File removed from the bank", "فایل از بانک حذف شد"))

        def remove_source_row(self, d):
            if self.confirm(T("Remove this source from the bank? Your files are not touched.",
                              "این منبع از بانک حذف شود؟ فایل‌های شما دست‌نخورده می‌مانند."),
                             T("Remove", "حذف"), T("Cancel", "انصراف"), danger=True):
                core.remove_source(d["sid"])
                self.expanded = {k for k in self.expanded if not k.startswith("%d:" % d["sid"])}
                self.tree_sig = None
                self.toast(T("Source removed", "منبع حذف شد"))
                threading.Thread(target=core.sync, daemon=True).start()

        def mk_item(self, parent, name, cnt, state, data, icn):
            c = tok()
            it = QTreeWidgetItem(parent)
            it.setText(0, name)
            it.setText(1, cnt)
            it.setIcon(0, icn)
            if data.get("k") in ("src", "dir"):           # folders are shown as headings
                f = it.font(0)
                f.setBold(True)
                it.setFont(0, f)
            it.setForeground(1, QBrush(QColor(c["acc"] if data.get("k") in ("src", "dir") else c["mute"])))
            it.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it.setData(0, Qt.ItemDataRole.UserRole, data)
            if state is not None:
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(0, state)
            return it

        def rebuild_tree(self):
            self.guard = True
            try:
                self.tree.clear()
                for s in core.sources:
                    data = {"root": True, "sid": s["id"], "dir": "", "path": posix(s["path"]), "key": "%d:" % s["id"]}
                    if s["kind"] == "dir":
                        it = self.mk_item(self.tree, s["name"], "", None, dict(data, k="src"), folder_icon())
                        QTreeWidgetItem(it)        # placeholder, so the expander arrow shows
                    else:
                        on = core.is_on(posix(s["path"]))
                        self.mk_item(self.tree, s["name"], "", Qt.CheckState.Checked if on else Qt.CheckState.Unchecked,
                                     dict(data, k="file", status="ok"), file_icon(s["name"]))
            finally:
                self.guard = False
            for i in range(self.tree.topLevelItemCount()):
                it = self.tree.topLevelItem(i)
                d = it.data(0, Qt.ItemDataRole.UserRole)
                if d.get("k") == "src" and d["key"] in self.expanded:
                    it.setExpanded(True)

        def load_children(self, it):
            d = it.data(0, Qt.ItemDataRole.UserRole)
            if not d or d.get("k") not in ("src", "dir"):
                return
            self.guard = True
            try:
                it.takeChildren()
                r = core.tree(d["sid"], d["dir"])
                for sd in r["dirs"]:
                    st = Qt.CheckState.Checked if sd["on"] else (Qt.CheckState.PartiallyChecked if sd["partial"] else Qt.CheckState.Unchecked)
                    c = self.mk_item(it, sd["name"], fd(sd["count"]), st,
                                     {"k": "dir", "sid": d["sid"], "dir": sd["dir"], "path": sd["path"], "key": "%d:%s" % (d["sid"], sd["dir"])},
                                     folder_icon())
                    QTreeWidgetItem(c)
                for f in r["files"]:
                    st = Qt.CheckState.Checked if f["on"] else Qt.CheckState.Unchecked
                    (_klog("ui.row", source=f["path"], shown_on=f["on"], core_on=core.is_on(f["path"]), built_from="expand") if f["on"] != core.is_on(f["path"]) else None)
                    cnt = T("no text", "بدون متن") if f["status"] == "empty" else fd(f["chunks"])
                    fi = self.mk_item(it, f["name"], cnt, st, {"k": "file", "path": f["path"], "status": f["status"]}, file_icon(f["name"]))
                    fi.setToolTip(0, f["path"] + ("\n" + T("No readable text in this file.", "متنی برای خواندن نیست.") if f["status"] == "empty" else ""))
                    if f["status"] == "empty":                    # unreadable files use the warning colour, so they stand out
                        fi.setForeground(0, QBrush(QColor(tok()["warn"])))
                if r["more"]:
                    self.mk_item(it, "+" + fd(r["more"]), "", None, {"k": "more"}, QIcon())
            finally:
                self.guard = False
            for i in range(it.childCount()):
                c = it.child(i)
                cd = c.data(0, Qt.ItemDataRole.UserRole)
                if cd and cd.get("k") == "dir" and cd["key"] in self.expanded:
                    c.setExpanded(True)

        def on_expand(self, it):
            d = it.data(0, Qt.ItemDataRole.UserRole)
            if d and d.get("key"):
                self.expanded.add(d["key"])
            if not self.guard:
                self.load_children(it)

        def on_collapse(self, it):
            d = it.data(0, Qt.ItemDataRole.UserRole)
            if d and d.get("key"):
                self.expanded.discard(d["key"])

        def on_item_changed(self, it, col):
            d0 = it.data(0, Qt.ItemDataRole.UserRole) or {}
            (_klog("ui.item_changed", path=d0.get("path"), kind=d0.get("k"), col=col,
                  check=str(it.checkState(0))) if not self.guard else None)
            if self.guard or col != 0:
                return
            d = it.data(0, Qt.ItemDataRole.UserRole)
            if not d or d.get("k") not in ("dir", "file"):
                return
            on = it.checkState(0) != Qt.CheckState.Unchecked
            core.set_sel(d["path"], on)
            QTimer.singleShot(0, self.rebuild_tree)           # redraw from the core's state, not from the row
            self.guard = True
            try:
                if d["k"] == "dir":
                    st = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
                    it.setCheckState(0, st)
                    for i in range(it.childCount()):
                        ch = it.child(i)
                        if ch.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                            ch.setCheckState(0, st)
            finally:
                self.guard = False

        def on_dbl(self, it, col):
            d = it.data(0, Qt.ItemDataRole.UserRole)
            if d and d.get("k") == "file" and d.get("status", "ok") == "ok":
                self.open_file(d["path"], 0, [])

        def open_file(self, path, ci, terms):
            try:
                self.viewer.show_doc(path, ci, terms)
            except Exception as e:
                self.notify(str(e))

        # ---------- status tick
        def comp_action(self, role):
            cs = core.comp_state(role)
            if not cs["files_ok"] or not cs["engine_ok"]:
                core.dm.start_role(role)
            if cs["pip_missing"]:
                core.start_pip(cs["pip_missing"])
            self.open_dl()
            self.tick()

        def settext(self, w, t):
            if w.text() != t:
                w.setText(t)

        def vis(self, widget, shown):
            """Shows or hides a widget only when its state changes, so a refresh does not reset it every time."""
            seen = self.__dict__.setdefault("_vis", {})
            key = id(widget)
            if seen.get(key) != bool(shown):
                seen[key] = bool(shown)
                widget.setVisible(bool(shown))

        def tick(self):
            s = core.snap
            if not s:
                return
            P, st = s["prog"], s["stats"]
            Y, M, I = P["sync"], P["meaning"], P["pip"]
            dls = s["downloads"]
            active = [i for i in dls if i["state"] in ("running", "queued")]
            self.settext(self.py_badge, "Python " + s["py"])
            self.settext(self.stat, "%s %s · %s %s" % (fd(st["files"]), T("files", "فایل"), fd(st["chunks"]), T("passages", "بند")))
            sig = (tuple(x["id"] for x in core.sources), st["files"], st["empty"], LANG, core.dirty)
            if sig != self.tree_sig and not Y["busy"]:
                self.tree_sig = sig
                self.rebuild_tree()
            busy_any = Y["busy"] or M["busy"] or bool(active) or I["busy"]
            self.timer.setInterval(500 if busy_any else 1500)
            self.settext(self.watch, T("reading…", "در حال خواندن…") if Y["busy"] else T("watching", "پایش"))
            self.set_kind(self.watch, "acc" if Y["busy"] else "ok")
            if Y["busy"]:
                self.settext(self.note_lib, T("Reading files… ", "در حال خواندن فایل‌ها… ") + "%s/%s %s" % (fd(Y["done"]), fd(Y["total"]), Y["msg"]))
            elif Y["err"]:
                self.settext(self.note_lib, Y["err"])
            elif st["empty"]:
                self.settext(self.note_lib, fd(st["empty"]) + T(" files had no readable text (not added).", " فایل، متن خواندنی نداشت و اضافه نشد."))
            else:
                self.settext(self.note_lib, "")
            # data files card
            for role in ("embed", "gen", "rerank"):
                cs = s[role]
                nm, badge, btn = self.rows[role]
                act = [i for i in active if i["role"] in (role, "engine")]
                if cs["ready"]:
                    self.settext(badge, "✓ " + T("ready", "آماده"))
                    self.set_kind(badge, "ok")
                    self.vis(btn, False)
                elif act:
                    tot = sum(i["total"] or i["est"] for i in act) or 1
                    self.settext(badge, fd(int(100 * sum(i["done"] for i in act) / tot)) + "%")
                    self.set_kind(badge, "acc")
                    self.vis(btn, False)
                elif I["busy"] and cs["pip_missing"]:
                    self.settext(badge, T("installing…", "در حال نصب…"))
                    self.set_kind(badge, "acc")
                    self.vis(btn, False)
                else:
                    self.vis(btn, True)
                    self.settext(badge, T("not downloaded", "دانلود نشده") if not cs["files_ok"] else T("needs setup", "نیاز به نصب"))
                    self.settext(btn, T("Download", "دانلود") if (not cs["files_ok"] or not cs["engine_ok"]) else T("Install", "نصب"))
                    self.set_kind(badge, "warn")
            if active:
                tot_active = sum(i["total"] or i["est"] for i in active)
                self.vis(self.dl_bar, True)
                self.dl_bar.setRange(0, 1000)
                self.dl_bar.setValue(int(1000 * sum(i["done"] for i in active) / tot_active) if tot_active else 0)
                sp = sum(i["speed"] for i in active)
                self.settext(self.note_dl, "%s · %s/s" % (active[0]["title"], fmt_size(sp)))
            elif I["busy"]:
                self.vis(self.dl_bar, True)
                if I["total"]:
                    self.dl_bar.setRange(0, 1000)
                    self.dl_bar.setValue(int(1000 * I["done"] / I["total"]))
                else:
                    self.dl_bar.setRange(0, 0)
                self.settext(self.note_dl, T("Installing packages… ", "در حال نصب بسته‌ها… ") + (I["log"] or ""))
            else:
                self.vis(self.dl_bar, False)
                err = next((i["err"].splitlines()[0] for i in dls if i["state"] == "error" and i["err"]), "") or I["err"]
                self.settext(self.note_dl, err)
            self.ai_chk.setEnabled(s["gen"]["ready"])
            self.sync_smart()
            # meaning card
            self.vis(self.b_mean, False)
            self.vis(self.b_pause, False)
            self.vis(self.mean_bar, False)
            if not s["embed"]["ready"]:
                self.settext(self.mean_state, T("Download the search model first (Data files).", "ابتدا مدل جست‌وجو را دانلود کنید (فایل‌های داده)."))
                self.settext(self.mean_badge, "—")
                self.set_kind(self.mean_badge, "warn")
                self.set_kind(self.mean_dot, "warn")
            elif M["busy"]:
                self.vis(self.mean_bar, True)
                self.mean_bar.setValue(int(1000 * M["done"] / M["total"]) if M["total"] else 0)
                self.settext(self.mean_state, T("Reading your documents… ", "در حال خواندن اسناد… ") + "%s / %s · %s" % (fd(M["done"]), fd(M["total"]), fmt_eta(round_eta(M.get("eta")))))
                self.settext(self.mean_badge, fd(int(100 * M["done"] / M["total"]) if M["total"] else 0) + "%")
                self.set_kind(self.mean_badge, "acc")
                self.set_kind(self.mean_dot, "acc")
                self.vis(self.b_pause, True)
                self.settext(self.b_pause, T("Resume", "ادامه") if M["paused"] else T("Pause", "توقف"))
            elif s["meaning"]["ready"] and s["meaning"]["complete"]:
                self.settext(self.mean_state, T("Ready — searching by meaning.", "آماده — جست‌وجوی معنایی فعال است."))
                self.settext(self.mean_badge, T("ready", "آماده"))
                self.set_kind(self.mean_badge, "ok")
                self.set_kind(self.mean_dot, "ok")
            else:
                self.vis(self.b_mean, True)
                self.b_mean.setEnabled(st["chunks"] > 0)
                self.settext(self.mean_state, M["err"] or (T("Not built yet. Word search works meanwhile.", "هنوز ساخته نشده؛ فعلاً جست‌وجوی واژه‌ای کار می‌کند.")
                                                          if st["chunks"] else T("Add documents first.", "ابتدا سند اضافه کنید.")))
                self.settext(self.mean_badge, "—")
                self.set_kind(self.mean_badge, "warn")
                self.set_kind(self.mean_dot, "warn")
            self.vis(self.empty, not self.turns)

        def build_meaning(self):
            core.start_meaning()
            self.tick()

        def toggle_pause(self):
            P = core.prog["meaning"]
            P["paused"] = not P["paused"]
            self.tick()

        # ---------- conversation
        def set_busy(self, on):
            self.busy = on
            self.b_ask.setEnabled(not on)

        def refresh_busy(self):
            """Input is locked only for the chat on screen. While that chat's answer is being written,
            the Stop button takes the place of the send button."""
            cid = getattr(self, "_chat_id", None)
            job = self.jobs.get(cid) if cid else None
            writing = bool(job is not None and job.get("ai_state") == "busy")
            self.b_stop.setVisible(writing)
            self.b_ask.setVisible(not writing)
            self.set_busy(bool(self.search_busy or cid in self.jobs))

        def refresh_chat_box(self):
            """Fills the chat list: chats grouped under Today, Yesterday and Earlier, filtered by the search box.
            The open chat stays selected."""
            cur = getattr(self, "_chat_id", None)
            lst = self.chat_list
            query = self.chat_search.text().strip().lower() if hasattr(self, "chat_search") else ""
            lst.blockSignals(True)
            lst.clear()
            chats = core.chats.chats()
            if query:
                chats = [c_ for c_ in chats if query in ((c_.get("title") or "").lower())]
            if not chats:
                if query:
                    text = T("No chats match your search.", "گفت‌وگویی با این جست‌وجو پیدا نشد.")
                else:
                    text = T("No saved chats yet. Ask a question to start one.",
                             "هنوز گفت‌وگویی ذخیره نشده. با یک پرسش شروع کنید.")
                hint = QListWidgetItem()
                hint.setData(Qt.ItemDataRole.UserRole, None)
                hint.setData(Qt.ItemDataRole.UserRole + 1, text)
                hint.setData(Qt.ItemDataRole.UserRole + 3, "hint")
                hint.setFlags(Qt.ItemFlag.NoItemFlags)
                lst.addItem(hint)
            today = time.strftime("%Y-%m-%d", time.localtime())
            yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
            last_group = None
            for c_ in chats:
                day = time.strftime("%Y-%m-%d", time.localtime(c_.get("updated") or 0))
                group = "today" if day == today else "yesterday" if day == yesterday else "earlier"
                if group != last_group:
                    label = {"today": T("Today", "امروز"), "yesterday": T("Yesterday", "دیروز"),
                             "earlier": T("Earlier", "قبلی")}[group]
                    head = QListWidgetItem()
                    head.setData(Qt.ItemDataRole.UserRole, None)
                    head.setData(Qt.ItemDataRole.UserRole + 1, label)
                    head.setData(Qt.ItemDataRole.UserRole + 3, "header")
                    head.setFlags(Qt.ItemFlag.NoItemFlags)
                    lst.addItem(head)
                    last_group = group
                title = (c_.get("title") or "").strip() or T("Untitled chat", "گفت‌وگوی بی‌عنوان")
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(c_.get("updated") or 0))
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, c_["id"])
                item.setData(Qt.ItemDataRole.UserRole + 1, title)
                item.setData(Qt.ItemDataRole.UserRole + 2, when)
                lst.addItem(item)
                if c_["id"] == cur:
                    lst.setCurrentItem(item)
            if not cur:
                lst.setCurrentRow(-1)
            total = sum(lst.sizeHintForRow(i) for i in range(lst.count())) + lst.spacing() * lst.count() + 6
            lst.setFixedHeight(min(max(total, 70), 420))          # grow with the content, up to a limit
            lst.blockSignals(False)

        def on_chat_picked(self, cid):
            """Opens a saved chat (cid), or starts a new one when cid is None."""
            if cid == getattr(self, "_chat_id", None):
                return
            if cid is None:
                self.new_chat()
            else:
                self.load_chat(cid)

        def clear_chat_view(self):
            for t in self.turns:
                if t.get("w"):
                    t["w"].deleteLater()
                t["w"] = None
                t["refs"] = {}                    # a turn still being written keeps its state; its widgets are gone
            self.turns = []
            self.empty.setVisible(True)

        def new_chat(self):
            self._chat_id = None
            self.clear_chat_view()
            self.refresh_busy()
            self.refresh_chat_box()

        def load_chat(self, cid):
            """Shows a saved chat with each answer's passages and citations. Passage-only answers appear as passages, and an AI answer can still be written for them."""
            self.clear_chat_view()
            self._chat_id = cid
            msgs = core.chats.messages(cid)
            i = 0
            while i < len(msgs):
                m = msgs[i]
                if m["role"] != "user":
                    i += 1
                    continue
                ans = msgs[i + 1] if i + 1 < len(msgs) and msgs[i + 1]["role"] == "assistant" else None
                r = {"mode": "words", "terms": [], "note": "", "bullets": [], "sources": [], "hits": [],
                     "context": [], "ids": []}
                if ans and ans.get("extra"):
                    r.update({k: v for k, v in ans["extra"].items() if k in r})
                is_ai = bool(ans) and ans["kind"] == "answer"
                self.turns.append({
                    "q": m["content"], "kind": "ask", "restored": True, "cid": cid, "hist": msgs[:i], "user_msg": m["id"],
                    "saved_msg": ans["id"] if ans else None, "r": r,
                    "ai_text": ans["content"] if is_ai else "", "ai_state": "done" if is_ai else None,
                    "ai_spans": [], "ai_grounded": True, "ai_lang_ok": True, "ai_no_sources": not r["context"],
                    "note": "", "err": False, "pass": False, "w": None, "refs": {}})
                i += 2 if ans else 1
            live = self.jobs.get(cid)
            if live is not None and live.get("user_msg") is not None:   # this chat's answer is still being written: show that turn
                for k, t in enumerate(self.turns):
                    if t.get("user_msg") == live.get("user_msg"):
                        self.turns[k] = live
                        break
            self.empty.setVisible(not self.turns)
            for t in self.turns:
                self.show_turn(t, scroll=False)
            self.refresh_busy()
            QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))
            self.refresh_chat_box()

        def delete_chat(self, cid=None):
            cid = cid or getattr(self, "_chat_id", None)
            if not cid or self.busy or cid in self.jobs:
                return
            if not self.confirm(T("Delete this chat? This cannot be undone.",
                                  "این گفت‌وگو حذف شود؟ این کار قابل بازگشت نیست."),
                                T("Delete", "حذف"), T("Cancel", "انصراف"), danger=True):
                return
            core.chats.delete(cid)
            if cid == getattr(self, "_chat_id", None):
                self.new_chat()
            else:
                self.refresh_chat_box()
            self.toast(T("Chat deleted", "گفت‌وگو حذف شد"))

        def toast(self, text):
            """Shows a short message at the bottom of the window. A new message replaces the one showing."""
            if getattr(self, "_toast", None) is None:
                self._toast = Toast(self)
            self._toast.show_text(text)

        def turn_btn(self, icon_name, tip, fn):
            """A small icon button under a message. fn receives the button."""
            b = QToolButton()
            b.setObjectName("turnAct")
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIcon(icon(icon_name, tok()["ink"], 16))
            b._tip = tip
            b.clicked.connect(lambda _=False: fn(b))
            return b

        def copy_text(self, text, b=None):
            """Copies text to the clipboard. The button briefly says Copied."""
            QApplication.clipboard().setText(text or "")
            self.toast(T("Copied", "کپی شد"))
            if b is not None:
                b.setToolTip(T("Copied", "کپی شد"))
                QTimer.singleShot(1500, lambda: b.setToolTip(b._tip))

        def ask_edit(self, text):
            """The edited question, or None if the user cancelled."""
            dlg = EditQuestionDialog(self, text)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                return dlg.value()
            return None

        def edit_question(self, t):
            """Replaces a question and asks it again. The answers that followed are removed."""
            if self.busy:
                self.notify(T("Wait for the answer to finish first.", "پس از پایان پاسخ، ویرایش کنید."))
                return
            new = self.ask_edit(t["q"])
            if not new or new == t["q"]:
                return
            idx = self.turns.index(t)
            self._branch_from = t.get("user_msg")          # the new question becomes a sibling of this one
            for x in self.turns[idx:]:
                if x.get("w"):
                    x["w"].deleteLater()
            self.turns = self.turns[:idx]
            draft = self.q.toPlainText()
            self.q.setPlainText(new)
            self.do_ask()
            self.q.setPlainText(draft)

        def switch_version(self, t, step):
            """Moves to another version of a question, and shows the conversation that continues from it."""
            if self.busy:
                self.notify(T("Wait for the answer to finish first.", "پس از پایان پاسخ، نسخه را عوض کنید."))
                return
            pos, total, sibs = core.chats.branches(t["user_msg"])
            if not (0 <= pos - 1 + step < total):
                return
            core.chats.switch_branch(t["cid"], sibs[pos - 1 + step])
            self.load_chat(t["cid"])

        def regenerate(self, t):
            """Writes the answer again. With Smart answer on, the AI model writes it from the same passages;
            with it off, the answer is the passages. The new answer replaces the saved one."""
            if not core.settings.get("ai"):
                if t.get("r") is None:
                    return
                self.save_answer(t, self.passage_text(t["r"]), t["r"].get("sources"), self.chat_extra(t["r"]), "passages")
                t["ai_state"] = None
                t["ai_text"] = ""
                self.show_turn(t)
                self.toast(T("Smart answers are off: showing the passages.",
                             "پاسخ هوشمند خاموش است: بندها نشان داده می‌شوند."))
                return
            if not core.gen_ready():
                self.notify(T("The answer model is not ready yet.", "مدل پاسخ هنوز آماده نیست."))
                return
            t["ai_state"] = None
            t["ai_text"] = ""
            self.run_gen(t)

        def use_starter(self, text):
            """Puts a starter question in the input, ready to send, with the cursor at the end."""
            self.q.setPlainText(text)
            self.q.setFocus()
            cur = self.q.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            self.q.setTextCursor(cur)

        def chat_action(self, cid, name):
            """Runs an action from a row's icon."""
            {"rename": self.rename_chat, "export": self.export_chat, "delete": self.delete_chat}[name](cid)

        def notify(self, text, title=None):
            ThemedMessage(self, text, T("OK", "باشه")).exec()

        def confirm(self, text, yes_text, no_text, danger=False):
            return ThemedMessage(self, text, yes_text, no_text, danger).exec() == QDialog.DialogCode.Accepted

        def rename_chat(self, cid=None):
            cid = cid or getattr(self, "_chat_id", None)
            if not cid:
                return
            name = self.ask_name(core.chats.title(cid))
            if name and core.chats.rename(cid, name):
                self.refresh_chat_box()
                self.toast(T("Chat renamed", "نام گفت‌وگو تغییر کرد"))

        def make_name_dialog(self, current):
            return ChatNameDialog(self, current)

        def ask_name(self, current):
            """The new chat name, or None if the user cancelled."""
            dlg = self.make_name_dialog(current)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                return dlg.value()
            return None

        def export_chat(self, cid=None):
            cid = cid or getattr(self, "_chat_id", None)
            if not cid:
                return
            path, _ = QFileDialog.getSaveFileName(self, T("Export chat", "خروجی گفت‌وگو"), "chat.md",
                                                  "Markdown (*.md)")
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(core.chats.export_markdown(cid))
            except OSError as e:
                self.notify(T("Could not save the file: ", "ذخیره فایل ناموفق بود: ") + str(e))
                return
            self.toast(T("Chat exported", "خروجی گفت‌وگو ذخیره شد"))

        def start(self, kind):
            q = self.q.toPlainText().strip()
            if not q or self.busy:
                return None
            if not core.booted:
                self.notify(T("Still loading your bank, one moment…", "بانک در حال بارگذاری است؛ لحظه‌ای صبر کنید…"))
                return None
            if not core.ix.N:
                self.notify(T("Add documents first.", "ابتدا سند اضافه کنید."))
                return None
            self.q.clear()
            t = {"q": q, "kind": kind, "r": None, "ai_text": "", "ai_state": None, "note": T("Searching…", "در حال جست‌وجو…"),
                 "pass": False, "w": None, "refs": {}}
            self.turns.append(t)
            self.empty.setVisible(False)
            self.search_busy = False
            self.set_busy(True)
            self.show_turn(t)
            return t

        def do_ask(self):
            t = self.start("ask")
            if t:
                cid = self.chat_id()
                t["cid"] = cid
                t["hist"] = core.chats.messages(cid)          # history from before this question
                parent = core.chats.parent_of(self._branch_from) if getattr(self, "_branch_from", None) else "auto"
                t["user_msg"] = core.chats.add(cid, "user", t["q"], parent=parent)
                self._branch_from = None
                if t["user_msg"] is None:
                    self.notify(T("This question could not be saved to the chat history. The answer is still shown. "
                                  "Details are in data/logs/chat_errors.txt.",
                                  "این پرسش در تاریخچه ذخیره نشد. پاسخ نمایش داده می‌شود. جزئیات در data/logs/chat_errors.txt است."))
                self.refresh_chat_box()
                if cid:
                    self.jobs[cid] = t
                    _klog("ui.job_start", chat=str(cid)[:8], open_chat=str(getattr(self, "_chat_id", ""))[:8], running=len(self.jobs))
                self.refresh_busy()
                bg(lambda: core.ask(t["q"]), lambda res: self.got(t, res))

        def chat_id(self):
            if not getattr(self, "_chat_id", None):
                self._chat_id = core.chats.new_chat()
            return self._chat_id

        def got(self, t, res):
            t["note"] = ""
            if res[0] == "err":
                t["note"] = loc(res[1])
                t["err"] = True
            else:
                t["r"] = res[1]
                if core.is_followup_question(t["q"]):
                    # Stage 1: a follow-up with no topic reuses the passages of the answer it follows
                    i_ = self.turns.index(t) if t in self.turns else -1
                    prev = self.turns[i_ - 1].get("r") if i_ > 0 else None
                    if prev and prev.get("context"):
                        t["r"] = dict(res[1], context=prev["context"], ids=prev.get("ids", []), note="")
            r = t["r"]
            ai_later = bool(r and t["kind"] == "ask" and core.settings.get("ai") and core.gen_ready())
            if not ai_later and t.get("cid") is not None:
                self.jobs.pop(t["cid"], None)
            self.refresh_busy()                           # busy only while the AI answer is written
            if t in self.turns:
                self.show_turn(t)
            if ai_later:
                self.run_gen(t)
            elif r and t["kind"] == "ask":
                text = self.passage_text(r)
                if core.settings.get("ai") and not r.get("bullets") and not r.get("context"):
                    # Smart answer is on but there are no passages to show, and the answer model could not write one.
                    # Say why, instead of saving the empty passage placeholder.
                    text = self.not_ready_text()
                self.save_answer(t, text, r.get("sources"), self.chat_extra(r), "passages")

        def not_ready_text(self):
            """Why there is no answer: the answer model is missing or not running. Shown instead of an empty passage line."""
            st = core.comp_state("gen")
            if not st.get("files_ok"):
                return T("There is no answer: the answer model is not downloaded yet. Open Downloads & models to finish it, "
                         "or turn Smart answer off to see the passages.",
                         "پاسخی نیست: مدل پاسخ هنوز دانلود نشده است. از بخش دانلودها و مدل‌ها آن را کامل کنید، "
                         "یا پاسخ هوشمند را خاموش کنید تا بندها دیده شوند.")
            return T("There is no answer: the answer model is not running. Open Downloads & models to check it.",
                     "پاسخی نیست: مدل پاسخ اجرا نمی‌شود. از بخش دانلودها و مدل‌ها بررسی کنید.")

        def passage_text(self, r):
            """The passage-only answer, saved when no AI answer is written."""
            return " ".join(b["text"] for b in (r or {}).get("bullets", [])) or "(no matching passage)"

        def chat_extra(self, r):
            """What a saved answer keeps, so a reopened chat shows the same citations and can be regenerated."""
            r = r or {}
            keep = {k: r.get(k) for k in ("mode", "terms", "note", "bullets", "sources", "hits", "context", "ids")}
            keep["general"] = not r.get("context")       # no passage was used: general knowledge, kept out of later prompts
            return keep

        def save_answer(self, t, text, sources, extra=None, kind="answer"):
            """Saves the turn's answer once. A later AI answer replaces the saved passage-only one."""
            cid = t.get("cid")
            if not cid or not text:
                return
            if t.get("saved_msg"):
                ok = core.chats.update(t["saved_msg"], text, sources, kind, extra)
            else:
                t["saved_msg"] = core.chats.add(cid, "assistant", text, sources, kind, extra)
                ok = t["saved_msg"] is not None
            if not ok:
                self.toast(T("Could not save this answer to the chat history.",
                             "این پاسخ در تاریخچه ذخیره نشد."))
            self.refresh_chat_box()

        def run_gen(self, t):
            t["ai_state"] = "busy"
            self.refresh_busy()                           # released when the answer finishes or fails
            t["ai_text"] = ""
            t["ai_preview"] = ""
            if core.engine.is_running("gen"):
                self.set_turn_note(t, T("Writing the answer…", "در حال نوشتن پاسخ…"))
            elif "gen" in core.engine.started_once:      # it ran before and stopped, so this is a restart, not a first start
                self.set_turn_note(t, T("Restarting the answer model…", "در حال راه‌اندازی دوباره مدل پاسخ…"))
            else:
                self.set_turn_note(t, T("Starting the answer model; the first answer can take a little longer.",
                                        "مدل پاسخ در حال راه‌اندازی است؛ پاسخ اول کمی بیشتر طول می‌کشد."))
            last = [0.0]

            def on_delta(text):
                now = time.time()
                if now - last[0] > 0.12:
                    last[0] = now
                    bridge.delta.emit(t, text)

            def done(res):
                if t.get("cid") is not None:
                    self.jobs.pop(t["cid"], None)
                    _klog("ui.job_done", chat=str(t["cid"])[:8], open_chat=str(getattr(self, "_chat_id", ""))[:8],
                          visible=t in self.turns, running=len(self.jobs), status=res[0])
                self.refresh_busy()
                if res[0] == "ok" and res[1].get("aborted"):
                    partial = (res[1].get("text") or "").strip()
                    t["ai_state"] = "stopped"
                    t["ai_preview"] = ""
                    if partial:
                        # keep the text written so far; it is not checked, so it carries no citations
                        t["ai_text"] = partial
                        extra = self.chat_extra(t["r"])
                        extra["checked"] = False
                        extra["general"] = False
                        self.save_answer(t, partial, [], extra, "answer")
                        self.set_turn_note(t, T("Stopped. The answer so far is kept (not checked).",
                                                "متوقف شد. پاسخ تا این لحظه نگه داشته شد (بررسی نشده)."))
                    else:
                        self.save_answer(t, self.passage_text(t["r"]), t["r"].get("sources"), self.chat_extra(t["r"]), "passages")
                        self.set_turn_note(t, T("Stopped. The passages are shown; press Write an AI answer to try again.",
                                                "متوقف شد. بندها نمایش داده می‌شوند؛ برای تلاش دوباره، پاسخ هوشمند را بنویسید."))
                    if t in self.turns:
                        self.update_ai(t)
                    return
                if res[0] == "err":
                    t["ai_state"] = "error"
                    self.save_answer(t, self.passage_text(t["r"]), t["r"].get("sources"), self.chat_extra(t["r"]), "passages")
                    self.set_turn_note(t, T("AI failed: ", "پاسخ هوشمند ناموفق: ") + res[1], True)
                else:
                    t["ai_state"] = "done"
                    t["ai_text"] = res[1]["text"]
                    extra = self.chat_extra(t["r"])
                    extra["checked"] = bool(res[1].get("verified"))   # every sentence was supported by a passage
                    if res[1].get("no_answer"):
                        # "the documents do not say" is not an answer: keep it out of later prompts, as general answers are
                        extra["general"] = True
                    self.save_answer(t, t["ai_text"] or self.passage_text(t["r"]), t["r"].get("sources"),
                                     extra, "answer" if t["ai_text"] else "passages")
                    t["ai_grounded"] = res[1]["grounded"]
                    t["ai_no_sources"] = not (t.get("r") or {}).get("context")   # no passage matched this question
                    t["ai_lang_ok"] = res[1].get("lang_ok", True)
                    t["ai_spans"] = res[1].get("spans", [])
                    if res[1].get("fallback"):
                        self.set_turn_note(t, T("The model's reply was empty, so the most relevant passage is shown.",
                                                "پاسخ مدل خالی بود؛ مرتبط‌ترین بند نمایش داده شد."))
                    else:
                        grounded_turn = core.grounded_mode() and bool((t.get("r") or {}).get("context"))
                        self.set_turn_note(t, "" if grounded_turn else T(
                            "Not from your documents: written from the model's general knowledge. It is not checked and may be wrong.",
                            "از اسناد شما نیست؛ از دانش عمومی مدل نوشته شده است و بررسی نشده است؛ ممکن است نادرست باشد."))
                    self.update_ai(t)
            bg(lambda: core.gen_stream(t["q"], t["r"]["context"], on_delta, t.get("hist")), done)

        def on_delta(self, t, text):
            # The words appear as they are written, as a muted draft. The checked answer replaces the draft when it is complete.
            if t.get("ai_state") == "busy":
                t["ai_preview"] = text
                now = time.time()
                if now - t.get("_ui_at", 0) < 0.25:      # redraw at most 4 times a second: every token re-laid-out froze the window
                    return
                t["_ui_at"] = now
                if t in self.turns:
                    self.update_ai(t)

        def set_turn_note(self, t, text, err=False):
            t["note"] = text
            t["err"] = err
            n = t.get("refs", {}).get("note")
            if n is not None:
                try:
                    n.setText(text)
                    n.setAlignment(Qt.AlignmentFlag.AlignRight if dir_of(text) == "rtl" else Qt.AlignmentFlag.AlignLeft)
                    n.setVisible(bool(text))
                except RuntimeError:
                    # the widget was deleted when the chat was redrawn during the answer; drop the stale reference
                    t.get("refs", {})["note"] = None

        def ai_html(self, t):
            if t.get("ai_state") == "busy" and not t.get("ai_text"):
                return self.draft_html(t)
            c = tok()
            warn = ""
            if not t.get("ai_lang_ok", True):
                warn += '<span style="color:%s">\u26a0 %s</span><br>' % (c["warn"], T(
                    "This answer is not in the language of your question.", "این پاسخ به زبان پرسش شما نیست."))
            if t.get("ai_no_sources"):
                # no passage matched on purpose, so say where the answer comes from rather than that a check failed
                warn += '<span style="color:%s">%s</span><br>' % (c["mute"], T(
                    "No passage in your documents matched this question, so no answer was written.",
                    "هیچ بندی از اسناد شما به این سؤال مربوط نبود؛ پاسخی نوشته نشد."))
            elif not t.get("ai_grounded", True):
                warn += '<span style="color:%s">⚠ %s</span><br>' % (c["warn"], T("Part of this answer was not found in your passages. Please check the sources.",
                                                                                 "بخشی از این پاسخ در بندهای شما نیست؛ منابع را بررسی کنید."))
            ti = self.turns.index(t) if t in self.turns else 0
            def badge(k, sp):
                # the citation after a paragraph or bullet; clicking it opens the passage (see on_link, "ai:<turn>:<k>")
                pct = ""
                shown = core.match_percent(sp.get("score"))
                if shown is not None:
                    pct = ' <span style="color:%s;font-size:8pt">%s%%</span>' % (c["mute"], fd(shown))
                return ' <a href="ai:%d:%d" style="color:%s;text-decoration:none"><b>[%s]</b></a>%s' % (
                    ti, k, c["cite"], fd(sp["n"]), pct)
            e = answer_html(t["ai_text"] or "", t.get("ai_spans") or [], badge, c)
            return rt(warn + e, dir_of(t["ai_text"] or t["q"])).replace("<div ", '<div style="font-size:12pt" ', 1)

        def update_ai(self, t):
            r = t.get("refs", {})
            fr, lb = r.get("ai_frame"), r.get("ai_label")
            if fr is None:
                return
            busy = t.get("ai_state") == "busy"
            if not t["ai_text"] and not busy:
                fr.setVisible(False)
                return
            try:
                html_ = self.ai_html(t)
                if html_ != r.get("_html"):          # identical redraws are skipped: they cause the flicker
                    # Keep the reader's place: a taller label must not move the view. Follow the answer down only
                    # when the reader was already at the bottom.
                    sb = self.scroll.verticalScrollBar() if getattr(self, "scroll", None) else None
                    was_bottom = sb is not None and sb.value() >= sb.maximum() - 4
                    kept = sb.value() if sb is not None else 0
                    r["_html"] = html_
                    lb.setText(html_)
                    if sb is not None:
                        sb.setValue(kept)
                        if was_bottom:               # the range grows only after the layout pass, so follow on the next tick
                            QTimer.singleShot(0, lambda: sb.setValue(sb.maximum()))
                fr.setVisible(True)
            except RuntimeError:
                # the bubble was deleted when the chat was redrawn during the answer; the redraw builds a new one
                r["ai_frame"], r["ai_label"] = None, None

        def animate(self):
            """Drives the live draft: the caret blinks and the dots move while an answer is being written."""
            self.anim_phase += 1
            self.caret_on = not self.caret_on
            for t in list(self.turns):
                # a streaming answer is redrawn by its own tokens (throttled), not by the timer, so it does not flicker
                if t.get("ai_state") == "busy" and not t.get("ai_preview"):
                    self.update_ai(t)

        def draft_html(self, t):
            """The live draft while the answer is written. It is muted and marked as a draft: it is checked before it is shown as the answer."""
            c = tok()
            text = t.get("ai_preview") or ""
            if text:
                # the draft is Markdown too: headings, bold and lists appear as they are written
                caret = "\u258d" if self.caret_on else "\u00a0"
                body = answer_html(text, [], lambda k, sp: "", c) + '<span style="color:%s">%s</span>' % (c["acc"], caret)
            else:
                body = '<span style="color:%s">%s%s</span>' % (c["mute"], esc(T("Writing", "در حال نوشتن")),
                                                             "." * (1 + self.anim_phase % 3))
            # The draft keeps one direction while it is written: the interface language's (Farsi: right side, as the
            # "Writing" label is). Taking it from the first words made the bubble jump sides. The final answer uses its own direction.
            return rt(body, dir_of(T("Writing", "در حال نوشتن"))).replace("<div ", '<div style="font-size:12pt" ', 1)

        def on_link(self, s):
            kind, _, rest = s.partition(":")
            try:
                bits = rest.split(":")
                t = self.turns[int(bits[0])]
                r = t["r"] or {}
                terms = r.get("terms", [])
                if kind == "bul":                       # a sentence of the answer, with its own passage
                    b = r["bullets"][int(bits[1])]
                    return self.open_file(b["path"], b["idx"], [b["text"]] + terms)
                if kind == "ai":                        # an AI sentence, with the passage it matched and the sentence highlighted
                    sp = (t.get("ai_spans") or [])[int(bits[1])]
                    if sp.get("path") is not None:
                        return self.open_file(sp["path"], sp["idx"], [sp["sent"]] + terms)
                if kind in ("cite", "src", "ai"):
                    n = int(bits[1])
                    for sr in r.get("sources", []):
                        if sr["n"] == n:
                            return self.open_file(sr["path"], sr.get("idx", 0), terms)
                elif kind == "gen":
                    self.run_gen(t)
            except Exception:
                traceback.print_exc()

        def label(self, html_text, selectable=True):
            lb = QLabel(html_text)
            lb.setTextFormat(Qt.TextFormat.RichText)
            lb.setWordWrap(True)
            lb.setOpenExternalLinks(False)
            lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction if selectable else Qt.TextInteractionFlag.NoTextInteraction)
            lb.linkActivated.connect(self.on_link)
            lb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            return lb

        def fill_passages(self, t, box, ti):
            c = tok()
            r = t["r"]
            bv = box.layout()
            for h in r["hits"]:
                hc = QFrame()
                hc.setObjectName("hit")
                hv = QVBoxLayout(hc)
                hv.setContentsMargins(12, 8, 12, 10)
                hv.setSpacing(4)
                top = QHBoxLayout()
                ic = QLabel()
                ic.setPixmap(file_icon(h["name"], 18).pixmap(18, 18))
                nm = ElideLabel(h["name"])
                num = QLabel("#" + fd(h["idx"] + 1))
                num.setObjectName("mute")
                ob = QPushButton(T("Open file", "باز کردن فایل"))
                ob.setObjectName("ghost")
                ob.clicked.connect(lambda _=False, hh=h, terms=r["terms"]: self.open_file(hh["path"], hh["idx"], terms))
                top.addWidget(ic)
                top.addWidget(nm, 1)
                top.addWidget(num)
                top.addWidget(ob)
                hv.addLayout(top)
                txt = h["text"] if len(h["text"]) <= 900 else h["text"][:900] + "…"
                hv.addWidget(self.label(rt(hl(txt, r["terms"], c).replace("\n", "<br>"), dir_of(txt))))
                bv.addWidget(hc)

        def add_ai_block(self, t, av, refs, ti):
            """The AI answer box, or the offer to write one. Used with and without passages."""
            fr = QFrame()
            fr.setObjectName("ai")
            fv = QVBoxLayout(fr)
            fv.setContentsMargins(14, 10, 14, 10)
            fv.setSpacing(4)
            lab = QLabel("✦ " + T("AI answer, written only from your files", "پاسخ هوشمند، فقط بر پایه‌ی فایل‌های شما"))
            lab.setObjectName("mute")
            fv.addWidget(lab)
            al = self.label("")
            fv.addWidget(al)
            av.addWidget(fr)
            refs["ai_frame"], refs["ai_label"] = fr, al
            fr.setVisible(False)
            if t["ai_text"]:
                al.setText(self.ai_html(t))
                fr.setVisible(True)
            elif t["ai_state"] is None and core.gen_ready() and not core.settings.get("ai"):
                av.addWidget(self.label('<a href="gen:%d">%s</a>' % (ti, esc(T("Write an AI answer", "نوشتن پاسخ هوشمند")))))

        def build_turn(self, t, ti):
            c = tok()
            refs = t["refs"] = {}
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 8, 0, 4)
            v.setSpacing(8)
            qd = dir_of(t["q"])
            row = QHBoxLayout()
            bub = QFrame()
            bub.setObjectName("bubbleQ")
            bl = QVBoxLayout(bub)
            bl.setContentsMargins(14, 9, 14, 9)
            ql = QLabel(rt(esc(t["q"]).replace("\n", "<br>"), qd))
            ql.setObjectName("qtext")
            ql.setTextFormat(Qt.TextFormat.RichText)
            ql.setWordWrap(True)
            ql.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            ql.setMaximumWidth(640)
            bl.addWidget(ql)
            # the bubble is as wide as its text, up to the room available and a readable line length
            pad = 28                                          # 14 px on each side inside the bubble
            natural = QFontMetrics(ql.font()).boundingRect(0, 0, 10000, 10000,
                                                           int(Qt.TextFlag.TextWordWrap), t["q"]).width()

            def fit_bubble():
                room = max(0, w.width() - 16)
                cap = max(60, min(640, room) - pad - 16)     # 16 px spare: rich text is a little wider than plain metrics
                want = min(natural + 16, cap)                # a short question stays short
                bub.setMaximumWidth(cap + pad)
                bub.setMinimumWidth(min(max(want, 60), cap) + pad)
                ql.setMaximumWidth(cap)

            ql.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            fit_bubble()
            w._bubble_fitter = BubbleFitter(fit_bubble)
            w.installEventFilter(w._bubble_fitter)
            # the question goes on the start side of the layout: right in Persian (right-to-left), left in English
            bub.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)   # keeps its own width
            start = Qt.AlignmentFlag.AlignRight if LANG == "fa" else Qt.AlignmentFlag.AlignLeft
            row.addWidget(bub, 0, start | Qt.AlignmentFlag.AlignAbsolute)
            row.addStretch(1)
            v.addLayout(row)
            qa = QHBoxLayout()
            qa.setSpacing(4)
            qa.addWidget(self.turn_btn("copy", T("Copy question", "کپی پرسش"), lambda b: self.copy_text(t["q"], b)))
            qa.addWidget(self.turn_btn("pencil", T("Edit question", "ویرایش پرسش"), lambda b: self.edit_question(t)))
            if t.get("user_msg") and t.get("cid"):
                pos, total, _sibs = core.chats.branches(t["user_msg"])
                if total > 1:                                 # there are other versions of this question
                    prev_b = QToolButton()
                    prev_b.setText("‹")
                    next_b = QToolButton()
                    next_b.setText("›")
                    for btn, step, tip in ((prev_b, -1, T("Previous version", "نسخه‌ی قبلی")),
                                           (next_b, 1, T("Next version", "نسخه‌ی بعدی"))):
                        btn.setAutoRaise(True)
                        btn.setToolTip(tip)
                        btn.setAccessibleName(tip)
                        btn.setEnabled(0 <= pos - 1 + step < total)
                        btn.clicked.connect(lambda _=False, tt=t, st=step: self.switch_version(tt, st))
                    count = QLabel("%d / %d" % (pos, total))
                    count.setObjectName("popupHint")
                    qa.addWidget(prev_b)
                    qa.addWidget(count)
                    qa.addWidget(next_b)
            qa.addStretch(1)
            v.addLayout(qa)
            r = t["r"]
            note = self.label("", False)
            note.setObjectName("mute")
            note.setText(esc(t["note"]))
            note.setVisible(bool(t["note"]))
            refs["note"] = note
            if not r:
                v.addWidget(note)
                if t["note"] and not t.get("err"):
                    pb = QProgressBar()
                    pb.setRange(0, 0)
                    pb.setTextVisible(False)
                    pb.setMaximumWidth(220)
                    v.addWidget(pb)
                return w
            ans = QFrame()
            ans.setObjectName("ans")
            av = QVBoxLayout(ans)
            av.setContentsMargins(16, 14, 16, 14)
            av.setSpacing(10)
            head = QHBoxLayout()
            avatar = QLabel()
            avatar.setObjectName("avatar")
            avatar.setFixedSize(28, 28)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setPixmap(pix(svg_icon("sparkle", c["accink"]), 15))
            bd = self.mk_badge("acc" if r["mode"] == "meaning" else "")
            mode = T("Search by meaning", "جست‌وجوی معنایی") if r["mode"] == "meaning" else T("Search by words", "جست‌وجوی واژه‌ای")
            bd.setText(mode)
            head.addWidget(avatar)
            head.addWidget(bd)
            head.addStretch(1)
            av.addLayout(head)
            if r.get("note"):
                wn = QLabel(r["note"])
                wn.setObjectName("mute")
                wn.setWordWrap(True)
                av.addWidget(wn)
            av.addWidget(note)
            if t["kind"] == "ask":
                if not r["bullets"] and not t.get("restored"):
                    av.addWidget(self.label(rt(esc(T("No matching passage was found in your files.", "بند مرتبطی در فایل‌های شما پیدا نشد.")), "rtl" if LANG == "fa" else "ltr")))
                self.add_ai_block(t, av, refs, ti)
                if r["bullets"]:
                    hd = QLabel(T("From your files", "از فایل‌های شما"))
                    hd.setObjectName("mute")
                    av.addWidget(hd)
                    for bk, b in enumerate(r["bullets"]):
                        d = dir_of(b["text"])
                        txt = "• %s <a href=\"bul:%d:%d\" style=\"color:%s;text-decoration:none\"><b>[%s]</b></a>" % (
                            hl(b["text"], r["terms"], c), ti, bk, c["cite"], fd(b["n"]))
                        if b["lead"]:
                            lf = QFrame()
                            lf.setObjectName("lead")
                            l2 = QVBoxLayout(lf)
                            l2.setContentsMargins(12, 8, 12, 8)
                            l2.addWidget(self.label(rt("<b>" + txt + "</b>", d)))
                            av.addWidget(lf)
                        else:
                            av.addWidget(self.label(rt(txt, d)))
                    sl_ = QLabel(T("Sources", "منابع"))
                    sl_.setObjectName("mute")
                    av.addWidget(sl_)
                    sc = QWidget()
                    fl = FlowLayout(6, 6)
                    sc.setLayout(fl)
                    for s_ in r["sources"]:
                        nm = s_["name"] if len(s_["name"]) <= 38 else s_["name"][:35] + "…"
                        b = QPushButton("[%s]  %s" % (fd(s_["n"]), nm))
                        b.setObjectName("chip")
                        b.setIcon(file_icon(s_["name"], 16))
                        b.setIconSize(QSize(16, 16))
                        b.setToolTip(s_["path"])
                        b.setCursor(Qt.CursorShape.PointingHandCursor)
                        b.clicked.connect(lambda _=False, p=s_["path"], ix_=s_.get("idx", 0), terms=r["terms"]: self.open_file(p, ix_, terms))
                        fl.addWidget(b)
                    av.addWidget(sc)
            elif not r["hits"]:
                av.addWidget(self.label(rt(esc(T("Nothing found.", "چیزی پیدا نشد.")), "rtl" if LANG == "fa" else "ltr")))
            if r["hits"]:
                box = QWidget()
                bv = QVBoxLayout(box)
                bv.setContentsMargins(0, 0, 0, 0)
                bv.setSpacing(8)
                built = [False]

                def ensure(on, tt=t, bx=box, tii=ti):
                    tt["pass"] = on
                    if on and not built[0]:         # passages are built only when opened, which keeps answers light
                        built[0] = True
                        self.fill_passages(tt, bx, tii)
                    bx.setVisible(on)
                if t["kind"] == "ask":
                    tg = QToolButton()
                    tg.setObjectName("passToggle")
                    tg.setCheckable(True)
                    tg.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                    tg.setText(T("Passages", "بندها") + " (%s)" % fd(len(r["hits"])))
                    tg.setIcon(icon("chevron-down", c["mute"], 14))
                    tg.toggled.connect(ensure)
                    av.addWidget(tg)
                    tg.setChecked(bool(t["pass"]))
                    box.setVisible(bool(t["pass"]))
                else:
                    ensure(True)
                av.addWidget(box)
            v.addWidget(ans)
            aa = QHBoxLayout()
            aa.setSpacing(4)
            aa.addWidget(self.turn_btn("copy", T("Copy answer", "کپی پاسخ"),
                                       lambda b: self.copy_text(t.get("ai_text") or self.passage_text(t["r"]), b)))
            aa.addWidget(self.turn_btn("refresh", T("Regenerate answer", "تولید دوباره پاسخ"), lambda b: self.regenerate(t)))
            aa.addStretch(1)
            v.addLayout(aa)
            return w

        def show_turn(self, t, scroll=True):
            ti = self.turns.index(t)
            new = self.build_turn(t, ti)
            old = t.get("w")
            if old is not None:
                self.tl.replaceWidget(old, new)
                old.deleteLater()
            else:
                self.tl.insertWidget(self.tl.count() - 1, new)
            t["w"] = new
            if scroll:
                QTimer.singleShot(60, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

        def render_all(self):
            for t in self.turns:
                if t.get("w") is not None:
                    self.show_turn(t, scroll=False)
            self.empty.setVisible(not self.turns)

    def font_watch():
        """Applies Vazirmatn as soon as it appears on disk. The download can take a long time on a
        first run, so this keeps checking (cheaply) until the font is in use."""
        if FONT_STATE["loaded"]:
            return
        if apply_vazirmatn(core, qapp, QFont, QFontDatabase, QFontInfo) and win_ref:
            win_ref[0].restyle()        # re-applies the stylesheet so every widget picks up the new font
            win_ref[0].render_all()
    font_timer = QTimer()
    font_timer.timeout.connect(font_watch)
    font_timer.start(2000)
    keep.append(font_timer)
    win_ref = []

    win = Win()
    win_ref.append(win)
    win.show()
    threading.Thread(target=core.sync, daemon=True).start()
    return qapp.exec()
