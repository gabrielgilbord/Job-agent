"""Modelo de oferta común a todas las fuentes."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict

from .textutil import norm


@dataclass
class Offer:
    source: str
    source_id: str
    title: str
    url: str
    company: str = ""
    location_text: str = ""
    postal_code: str = ""
    description: str = ""
    salary_text: str = ""          # tal y como aparece publicado
    salary_min: float | None = None  # anual bruto si se puede deducir
    salary_max: float | None = None
    contract: str = ""             # indefinido / temporal / fijo-discontinuo / ...
    workday: str = ""              # completa / parcial / ...
    requirements: str = ""
    education: str = ""
    experience: str = ""
    published_at: str = ""         # ISO, si se conoce
    expires_at: str = ""           # ISO, si se conoce
    remote: bool = False
    # Calculados
    municipality: str = ""
    travel_min: int | None = None
    geo_tier: str = ""
    category: str = ""
    score: int = 0
    score_breakdown: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    verdict: str = ""

    @property
    def fingerprint(self) -> str:
        """Identidad lógica: empresa + puesto + municipio (para detectar duplicados entre portales)."""
        base = "|".join([norm(self.company), norm(self.title), norm(self.municipality or self.location_text)])
        return hashlib.sha1(base.encode()).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        """Huella de las condiciones: si cambia => oferta modificada."""
        base = "|".join([self.salary_text, str(self.salary_min), str(self.salary_max), self.contract,
                         self.workday, norm(self.requirements)[:500]])
        return hashlib.sha1(base.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fingerprint"] = self.fingerprint
        return d
