"""Turijobs (portal de empleo turístico). Lee el listado público de Gran Canaria.

Se usa la página indexable /es/ofertas-trabajo/gran-canaria (permitida en robots.txt) y los datos
estructurados que la propia página incluye. Pausa entre páginas para no sobrecargar el portal.
"""
from __future__ import annotations

import json
import re

from ..models import Offer
from ..textutil import html_to_text
from .base import Source, BROWSER_UA, make_session

BASE = "https://www.turijobs.com"
LIST_URL = BASE + "/es/ofertas-trabajo/gran-canaria"


class TurijobsSource(Source):
    name = "turijobs"
    delay = 2.0

    def __init__(self, settings, session=None):
        super().__init__(settings, session or make_session(BROWSER_UA))

    def _page(self, n: int) -> dict:
        url = LIST_URL if n == 1 else f"{LIST_URL}?page={n}"
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        if not m:
            raise RuntimeError("Turijobs: estructura de página no reconocida")
        return json.loads(m.group(1))["props"]["pageProps"]["searchData"]

    def fetch(self) -> list[Offer]:
        offers, seen = [], set()
        maxp = int(self.cfg.get("paginas_max", 9))
        n, pages = 1, 1
        while n <= min(pages, maxp):
            data = self._page(n)
            pages = int(data.get("pages") or 1)
            for it in data.get("offers", []):
                if it.get("type") == "diffusion_national":
                    continue  # anuncios nacionales patrocinados, no de GC
                oid = str(it.get("id"))
                if oid in seen:
                    continue
                seen.add(oid)
                offers.append(self._to_offer(it))
            n += 1
            if n <= min(pages, maxp):
                self.pause()
        return offers

    @staticmethod
    def _to_offer(it: dict) -> Offer:
        loc = it.get("location") or {}
        req = it.get("requirements") or {}
        tags = it.get("offerDescriptionTags") or []
        card = it.get("cardTags") or []
        salary = next((t for t in tags if re.search(r"\d{3,}.*(bruto|neto|anual|mes|€|\$)", t, re.I)), "")
        contract = next((t for t in card if t.lower() in ("indefinido", "temporal", "fijo - discontinuo", "obra y servicio",
                                                           "becario/prácticas", "temporal + indefinido", "interinidad",
                                                           "autónomo")), "")
        workday = next((t for t in card if "jornada" in t.lower() or "parcial" in t.lower()), "")
        reqs = []
        for k, v in req.items():
            k = {"DEGREE": "Titulación", "EXP_YEARS": "Experiencia", "LANGUAGES": "Idiomas"}.get(k, k.title())
            reqs.append(f"{k}: {', '.join(v) if isinstance(v, list) else v}")
        add = it.get("additionalRequirements") or ""
        company = (it.get("company") or {}).get("brandName") or (it.get("company") or {}).get("enterpriseName") or ""
        if (it.get("company") or {}).get("isConfidential"):
            company = ""
        url = f"{BASE}/es/ofertas-trabajo/{it.get('url')}" if it.get("url") else BASE
        return Offer(
            source="turijobs", source_id=str(it.get("id")), title=(it.get("title") or "").strip(), url=url,
            company=company,
            location_text=", ".join(x for x in [loc.get("cityName"), loc.get("address"), loc.get("regionName")] if x),
            # el CP de Turijobs no es fiable cuando la ciudad es genérica ("Gran Canaria")
            postal_code="" if (loc.get("cityName") or "").strip().lower() in ("gran canaria", "las palmas", "")
            else str(loc.get("zipCode") or ""),
            description=html_to_text(it.get("description")),
            salary_text=salary, contract=contract.replace("Fijo - discontinuo", "fijo-discontinuo").lower(),
            workday=("completa" if "completa" in workday.lower() else "parcial" if workday else ""),
            requirements=("\n".join(reqs) + ("\n" + add if add else "")).strip(),
            education=", ".join(req.get("DEGREE", []) or []), experience=", ".join(req.get("EXP_YEARS", []) or []),
            published_at=(it.get("publicationDate") or "")[:19], expires_at=(it.get("expiringDate") or "")[:19],
        )
