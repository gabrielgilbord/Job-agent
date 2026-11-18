"""Jooble (agregador con API gratuita). Requiere JOOBLE_API_KEY. Alta: https://jooble.org/api/about"""
from __future__ import annotations

from ..models import Offer
from ..textutil import html_to_text
from .base import Source, SourceUnavailable


class JoobleSource(Source):
    name = "jooble"
    delay = 1.2

    def fetch(self) -> list[Offer]:
        key = self.settings.secret("JOOBLE_API_KEY")
        if not key:
            raise SourceUnavailable("falta JOOBLE_API_KEY")
        out, seen = [], set()
        for term in self.search_terms():
            r = self.session.post(f"https://es.jooble.org/api/{key}",
                                  json={"keywords": term, "location": "Gran Canaria", "page": 1}, timeout=30)
            r.raise_for_status()
            for j in r.json().get("jobs", []):
                jid = str(j.get("id") or j.get("link"))
                if jid in seen:
                    continue
                seen.add(jid)
                t = (j.get("type") or "").lower()
                out.append(Offer(
                    source="jooble", source_id=jid, title=(j.get("title") or "").strip(), url=j.get("link", ""),
                    company=j.get("company", "") or "", location_text=j.get("location", "") or "",
                    description=html_to_text(j.get("snippet")), salary_text=j.get("salary", "") or "",
                    workday="completa" if "complet" in t or "full" in t else "parcial" if "parcial" in t or "part" in t else "",
                    published_at=(j.get("updated") or "")[:19]))
            self.pause()
        return out
