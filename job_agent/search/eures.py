"""EURES (portal europeo de empleo, API pública). Incluye las ofertas que publican el SEPE / Empléate y el
Servicio Canario de Empleo. Se consulta Canarias (es70) y se quedan solo las de Gran Canaria (NUTS ES705)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..models import Offer
from ..textutil import html_to_text
from .base import Source

API = "https://europa.eu/eures/api/jv-searchengine/public/jv-search/search"
DETAIL = "https://europa.eu/eures/portal/jv-se/jv-details/{id}?lang=es"


def _body(page: int) -> dict:
    return {"resultsPerPage": 50, "page": page, "sortSearch": "MOST_RECENT", "keywords": [], "publicationPeriod": None,
            "occupationUris": [], "skillUris": [], "requiredExperienceCodes": [], "positionScheduleCodes": [],
            "sectorCodes": [], "educationAndQualificationLevelCodes": [], "positionOfferingCodes": [],
            "locationCodes": ["es70"], "euresFlagCodes": [], "otherBenefitsCodes": [], "requiredLanguages": [],
            "minNumberPost": None, "sessionId": "job-agent-gc"}


class EuresSource(Source):
    name = "eures"
    delay = 1.0

    def fetch(self) -> list[Offer]:
        out, page = [], 1
        maxp = int(self.cfg.get("paginas_max", 25))
        while page <= maxp:
            r = self.session.post(API, json=_body(page), timeout=40)
            r.raise_for_status()
            jvs = r.json().get("jvs") or []
            if not jvs:
                break
            for j in jvs:
                locs = (j.get("locationMap") or {}).get("ES") or []
                if not any(l in ("ES705", "ES70") for l in locs):
                    continue  # otra isla
                o = self._to_offer(j)
                if o:
                    out.append(o)
            page += 1
            self.pause()
        return out

    @staticmethod
    def _to_offer(j: dict) -> Offer | None:
        langs = j.get("availableLanguages") or []
        tr = (j.get("translations") or {})
        t = tr.get("es") or {}
        title = (t.get("title") or j.get("title") or "").strip()
        desc = html_to_text(t.get("description") or j.get("description") or "")
        if "es" not in langs and not t:
            return None  # anuncios solo en otros idiomas (suelen ser de reclutadores extranjeros)
        ms = j.get("creationDate")
        pub = datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") if ms else ""
        sched = " ".join(j.get("positionScheduleCodes") or [])
        emp = (j.get("employer") or {}).get("name") or ""
        return Offer(
            source="eures", source_id=str(j.get("id")), title=title, url=DETAIL.format(id=j.get("id")),
            company=emp.strip(), location_text="Gran Canaria", description=desc,
            workday="completa" if "fulltime" in sched else "parcial" if "parttime" in sched else "",
            published_at=pub)
