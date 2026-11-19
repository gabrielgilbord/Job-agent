"""Infoempleo: listado público de la provincia de Las Palmas (/trabajo/en_las-palmas/, permitido por robots.txt)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html import unescape

from ..models import Offer
from ..textutil import html_to_text
from .base import Source

BASE = "https://www.infoempleo.com"
LIST = BASE + "/trabajo/en_las-palmas/"


def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


class InfoempleoSource(Source):
    name = "infoempleo"
    delay = 2.0

    def fetch(self) -> list[Offer]:
        out, seen = [], set()
        maxp = int(self.cfg.get("paginas_max", 8))
        for page in range(1, maxp + 1):
            r = self.session.get(LIST if page == 1 else f"{LIST}?pagina={page}", timeout=40)
            r.raise_for_status()
            cards = re.findall(r'<li class="offerblock[^"]*">(.*?)(?=<li class="offerblock|<ul class="pagination|$)',
                               r.text, re.S)
            if not cards:
                break
            for c in cards:
                o = self._parse(c)
                if o and o.source_id not in seen:
                    seen.add(o.source_id)
                    out.append(o)
            m = re.search(r"Mostrando \d+-(\d+) de <strong>(\d+)", r.text)
            if m and int(m.group(1)) >= int(m.group(2)):
                break
            self.pause()
        return out

    @staticmethod
    def _parse(c: str) -> Offer | None:
        a = re.search(r'<h2 class="title[^"]*"><a href="([^"]+)"[^>]*>(.*?)</a>', c, re.S)
        if not a:
            return None
        href, title = a.group(1), _txt(a.group(2))
        oid = re.search(r"/(\d+)/?$", href)
        company = _txt((re.search(r'<p class="company-name">(.*?)</(?:p|div)>', c, re.S) or [None, ""])[1])
        loc_m = re.search(r'class="offer-location-desktop">(.*?)</span>', c, re.S) or \
            re.search(r'class="offer-location[^"]*"[^>]*>(.*?)</div>', c, re.S)
        location = _txt(loc_m.group(1)) if loc_m else ""
        multi = re.search(r'data-location-total="(\d+)"', c)
        if multi and int(multi.group(1)) > 3:
            return None  # ofertas genéricas publicadas en decenas de provincias
        text = _txt(re.sub(r"<svg.*?</svg>", " ", c, flags=re.S))
        contract = next((k for k in ("Indefinido", "Temporal", "Fijo discontinuo", "Autónomo", "Prácticas", "Otros contratos")
                         if k.lower() in text.lower()), "")
        workday = "completa" if "jornada completa" in text.lower() else \
            "parcial" if ("jornada parcial" in text.lower() or "media jornada" in text.lower()) else ""
        sal = re.search(r"(\d[\d.]*\s*(?:-|a)\s*\d[\d.]*\s*€[^·|<]{0,25}|\d[\d.]*\s*€[^·|<]{0,25})", text)
        desc_m = re.search(r'<p class="description[^"]*">(.*?)</p>', c, re.S)
        desc = html_to_text(desc_m.group(1)) if desc_m else text
        exp = re.search(r"(No se requiere experiencia|Experiencia[^·|]{0,40}año[s]?)", text)
        pub = ""
        h = re.search(r"Hace (\d+) (hora|horas|día|días|minutos?)", text)
        if h:
            n = int(h.group(1))
            delta = timedelta(hours=n) if "hora" in h.group(2) else timedelta(days=n) if "d" in h.group(2) else timedelta(minutes=n)
            pub = (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%S")
        return Offer(source="infoempleo", source_id=oid.group(1) if oid else href, title=title,
                     url=BASE + href if href.startswith("/") else href, company=company,
                     location_text=f"{location}, Las Palmas" if "palmas" not in location.lower() else location,
                     description=desc, contract=contract.lower(), workday=workday,
                     salary_text=sal.group(1).strip() if sal else "", experience=exp.group(1) if exp else "",
                     published_at=pub)
