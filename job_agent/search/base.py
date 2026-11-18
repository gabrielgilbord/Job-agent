"""Utilidades comunes de las fuentes: sesión HTTP con reintentos y pausas educadas."""
from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..models import Offer

log = logging.getLogger("job_agent.search")
UA = "JobAgentGC/1.0 (busqueda personal de empleo; uso no comercial)"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


class SourceUnavailable(Exception):
    """La fuente no está configurada (p. ej. falta la API key). No es un error."""


def make_session(user_agent: str = UA) -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "POST"), respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": user_agent, "Accept-Language": "es-ES,es;q=0.9"})
    return s


class Source:
    name = "base"
    delay = 1.5  # segundos entre peticiones a la misma fuente

    def __init__(self, settings, session: requests.Session | None = None):
        self.settings = settings
        self.cfg = settings.fuentes.get(self.name, {}) or {}
        self.session = session or make_session()

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("activa", True))

    def search_terms(self) -> list[str]:
        terms = []
        for cat in self.settings.categorias.values():
            terms.extend(cat.get("terminos", []))
        return list(dict.fromkeys(terms))

    def pause(self):
        time.sleep(self.delay)

    def fetch(self) -> list[Offer]:  # pragma: no cover - implementado en subclases
        raise NotImplementedError
