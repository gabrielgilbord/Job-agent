"""Pruebas contra los portales reales. Se ejecutan con:  RUN_LIVE=1 pytest tests/test_live_sources.py"""
import os

import pytest
import requests

from job_agent.search import TurijobsSource, SmartRecruitersSource

pytestmark = pytest.mark.skipif(not os.environ.get("RUN_LIVE"), reason="pruebas en vivo desactivadas")


@pytest.mark.parametrize("cls", [TurijobsSource, SmartRecruitersSource])
def test_fuente_devuelve_ofertas_con_enlace_valido(settings, cls):
    offers = cls(settings).fetch()
    assert offers, f"{cls.name} no devolvió ofertas"
    o = offers[0]
    assert o.title and o.url.startswith("https://")
    r = requests.get(o.url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
    assert r.status_code < 400
