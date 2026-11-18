"""Adzuna (agregador con API oficial gratuita). Requiere ADZUNA_APP_ID y ADZUNA_APP_KEY.
Alta gratuita: https://developer.adzuna.com/signup
"""
from __future__ import annotations

from ..models import Offer
from ..textutil import html_to_text
from .base import Source, SourceUnavailable

API = "https://api.adzuna.com/v1/api/jobs/es/search/{page}"


class AdzunaSource(Source):
    name = "adzuna"
    delay = 1.2

    def fetch(self) -> list[Offer]:
        app_id, key = self.settings.secret("ADZUNA_APP_ID"), self.settings.secret("ADZUNA_APP_KEY")
        if not (app_id and key):
            raise SourceUnavailable("faltan ADZUNA_APP_ID / ADZUNA_APP_KEY")
        out, seen = [], set()
        for term in self.search_terms():
            r = self.session.get(API.format(page=1), params={
                "app_id": app_id, "app_key": key, "what": term, "where": "Gran Canaria", "results_per_page": 50,
                "max_days_old": 30, "content-type": "application/json"}, timeout=30)
            r.raise_for_status()
            for j in r.json().get("results", []):
                if j.get("id") in seen:
                    continue
                seen.add(j.get("id"))
                sal = ""
                if j.get("salary_min") and not j.get("salary_is_predicted") in ("1", 1, True):
                    sal = f"{int(j['salary_min'])}-{int(j.get('salary_max') or j['salary_min'])} € anual bruto"
                ct = {"permanent": "indefinido", "contract": "temporal"}.get(j.get("contract_type") or "", "")
                wd = {"full_time": "completa", "part_time": "parcial"}.get(j.get("contract_time") or "", "")
                out.append(Offer(
                    source="adzuna", source_id=str(j.get("id")), title=j.get("title", "").strip(),
                    url=j.get("redirect_url", ""), company=(j.get("company") or {}).get("display_name", ""),
                    location_text=", ".join((j.get("location") or {}).get("area", [])[::-1]) or
                                  (j.get("location") or {}).get("display_name", ""),
                    description=html_to_text(j.get("description")), salary_text=sal,
                    salary_min=float(j["salary_min"]) if sal else None,
                    salary_max=float(j.get("salary_max") or j["salary_min"]) if sal else None,
                    contract=ct, workday=wd, published_at=(j.get("created") or "")[:19]))
            self.pause()
        return out
