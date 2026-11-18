"""Portales de empleo de empresas que usan SmartRecruiters (API pública de publicaciones).

Ejemplos verificados con tiendas en Gran Canaria: Primark, Kiabi. Lista editable en config.yaml.
"""
from __future__ import annotations

from ..models import Offer
from ..textutil import html_to_text, norm
from .base import Source

API = "https://api.smartrecruiters.com/v1/companies/{company}/postings"


class SmartRecruitersSource(Source):
    name = "smartrecruiters"
    delay = 1.0

    def fetch(self) -> list[Offer]:
        out = []
        for company in self.cfg.get("empresas", []):
            offset = 0
            while True:
                r = self.session.get(API.format(company=company),
                                     params={"country": "es", "limit": 100, "offset": offset}, timeout=30)
                r.raise_for_status()
                data = r.json()
                items = data.get("content", [])
                for p in items:
                    loc = p.get("location") or {}
                    region = norm(f"{loc.get('region')} {loc.get('city')} {loc.get('postalCode')}")
                    # filtro previo barato: solo Canarias (provincia Las Palmas) antes de pedir el detalle
                    if not (str(loc.get("postalCode", "")).startswith("35") or "cn" in region.split()
                            or "las palmas" in region or "canari" in region):
                        continue
                    out.append(self._detail(company, p))
                offset += len(items)
                if not items or offset >= data.get("totalFound", 0) or offset >= 1000:
                    break
                self.pause()
        return out

    def _detail(self, company: str, p: dict) -> Offer:
        loc = p.get("location") or {}
        desc, reqs = "", ""
        try:
            self.pause()
            d = self.session.get(f"{API.format(company=company)}/{p['id']}", timeout=30).json()
            sec = (d.get("jobAd") or {}).get("sections") or {}
            desc = html_to_text(" \n".join((sec.get(k) or {}).get("text", "") for k in
                                           ("companyDescription", "jobDescription", "additionalInformation")))
            reqs = html_to_text((sec.get("qualifications") or {}).get("text", ""))
        except Exception:  # el detalle es opcional
            pass
        toe = ((p.get("typeOfEmployment") or {}).get("label") or "").lower()
        return Offer(
            source="smartrecruiters", source_id=str(p.get("id")), title=(p.get("name") or "").strip(),
            url=f"https://jobs.smartrecruiters.com/{company}/{p.get('id')}",
            company=(p.get("company") or {}).get("name") or company,
            location_text=", ".join(x for x in [loc.get("city"), loc.get("address"), loc.get("region")] if x),
            postal_code=str(loc.get("postalCode") or ""), description=desc, requirements=reqs,
            workday="completa" if "full" in toe else "parcial" if "part" in toe else "",
            contract="temporal" if "temporary" in toe else "",
            published_at=(p.get("releasedDate") or "")[:19], remote=False,
        )
