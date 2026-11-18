import re
import unicodedata
from html import unescape


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s: str | None) -> str:
    """minúsculas, sin tildes, sin signos, espacios simples."""
    if not s:
        return ""
    s = strip_accents(unescape(str(s))).lower()
    s = re.sub(r"[^a-z0-9ñ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def has_any(text_norm: str, terms) -> list[str]:
    """Devuelve los términos (normalizados) encontrados como palabra/frase completa."""
    found = []
    for t in terms:
        tn = norm(t)
        if tn and re.search(r"(?<![a-z0-9])" + re.escape(tn) + r"(?![a-z0-9])", text_norm):
            found.append(t)
    return found
