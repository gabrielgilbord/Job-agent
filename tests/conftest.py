import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from job_agent.config import load_settings  # noqa: E402
from job_agent.models import Offer  # noqa: E402


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "ADZUNA_APP_ID", "INFOJOBS_CLIENT_ID", "JOOBLE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    s = load_settings(db_path=tmp_path / "t.db")
    s.secrets = {k: "" for k in s.secrets}
    s.reports_dir = tmp_path / "reports"
    s.logs_dir = tmp_path / "logs"
    return s


def make_offer(**kw):
    base = dict(source="test", source_id="1", title="Recepcionista de hotel", url="https://ej.com/1",
                company="Hotel Ejemplo", location_text="Las Palmas de Gran Canaria",
                description="Atención al cliente en recepción. Contrato indefinido, jornada completa.")
    base.update(kw)
    return Offer(**base)


@pytest.fixture
def offer():
    return make_offer
