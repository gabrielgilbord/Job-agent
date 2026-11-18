"""Interpretación de salarios publicados -> rango anual bruto aproximado. Nunca inventa: si no se entiende, None."""
from __future__ import annotations

import re

from ..textutil import norm


def _num(s: str) -> float | None:
    s = s.strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        s = re.sub(r"[.,]", "", s)
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_salary(text: str) -> tuple[float | None, float | None, str]:
    """Devuelve (min_anual, max_anual, nota). Nota indica conversión aplicada."""
    if not text:
        return None, None, ""
    t = norm(text.replace("k", "000") if re.search(r"\d+\s?k\b", text.lower()) else text)
    raw = re.findall(r"\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?", text.replace("€", " ").replace("$", " "))
    nums = [n for n in (_num(x) for x in raw) if n and n >= 5]
    if not nums:
        return None, None, ""
    lo, hi = min(nums[:2]), max(nums[:2])
    note = ""
    if "hora" in t or lo < 40:
        lo, hi, note = lo * 1800, hi * 1800, "estimado desde €/hora"
    elif lo < 5000 or "mes" in t or "mensual" in t:
        lo, hi, note = lo * 14, hi * 14, "estimado ×14 pagas"
        if "neto" in t:
            lo, hi, note = lo * 1.2, hi * 1.2, "estimado desde neto mensual"
    if lo < 6000 or hi > 200000:
        return None, None, ""
    return round(lo), round(hi), note
