"""InfoJobs (API oficial). Requiere INFOJOBS_CLIENT_ID y INFOJOBS_CLIENT_SECRET.
Alta gratuita de aplicación: https://developer.infojobs.net/  (no se hace scraping de la web).
"""
from __future__ import annotations

from ..models import Offer
from .base import Source, SourceUnavailable

API = "https://api.infojobs.net/api/9/offer"


class InfoJobsSource(Source):
    name = "infojobs"
    delay = 1.2

    def fetch(self) -> list[Offer]:
        cid, sec = self.settings.secret("INFOJOBS_CLIENT_ID"), self.settings.secret("INFOJOBS_CLIENT_SECRET")
        if not (cid and sec):
            raise SourceUnavailable("faltan INFOJOBS_CLIENT_ID / INFOJOBS_CLIENT_SECRET")
        out, seen = [], set()
        for term in self.search_terms():
            r = self.session.get(API, params={"q": term, "province": "las-palmas", "maxResults": 50,
                                              "sinceDate": "_7_DAYS", "order": "updated-desc"},
                                 auth=(cid, sec), timeout=30)
            if r.status_code == 401:
                raise RuntimeError("InfoJobs: credenciales no válidas (401)")
            r.raise_for_status()
            for j in r.json().get("offers", []):
                if j.get("id") in seen:
                    continue
                seen.add(j.get("id"))
                val = lambda k: (j.get(k) or {}).get("value", "") if isinstance(j.get(k), dict) else (j.get(k) or "")
                smin, smax, per = val("salaryMin"), val("salaryMax"), val("salaryPeriod")
                sal = f"{smin} - {smax} {per}".strip(" -") if smin or smax else ""
                out.append(Offer(
                    source="infojobs", source_id=str(j.get("id")), title=(j.get("title") or "").strip(),
                    url=j.get("link", ""), company=(j.get("author") or {}).get("name", ""),
                    location_text=", ".join(x for x in [j.get("city"), val("province")] if x),
                    description=j.get("requirementMin", "") or "", salary_text=sal,
                    contract=str(val("contractType")).lower(), workday=str(val("workDay")).lower().replace("jornada ", ""),
                    requirements=j.get("requirementMin", "") or "", education=str(val("study")),
                    experience=str(val("experienceMin")), published_at=(j.get("published") or "")[:19]))
            self.pause()
        return out
