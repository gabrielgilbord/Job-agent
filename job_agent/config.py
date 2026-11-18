"""Carga de configuración: config.yaml (preferencias) + variables de entorno (secretos)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"


def _load_dotenv(path: Path) -> None:
    """Lector mínimo de .env (sin dependencias). No sobrescribe variables ya definidas."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Settings:
    raw: dict
    db_path: Path
    reports_dir: Path
    logs_dir: Path
    secrets: dict = field(default_factory=dict)

    # accesos cómodos
    @property
    def candidata(self) -> dict:
        return self.raw.get("candidata", {})

    @property
    def busqueda(self) -> dict:
        return self.raw.get("busqueda", {})

    @property
    def preferencias(self) -> dict:
        return self.raw.get("preferencias", {})

    @property
    def geografia(self) -> dict:
        return self.raw.get("geografia", {})

    @property
    def categorias(self) -> dict:
        return self.raw.get("categorias", {})

    @property
    def fuentes(self) -> dict:
        return self.raw.get("fuentes", {})

    def secret(self, name: str) -> str | None:
        v = self.secrets.get(name)
        return v if v else None


SECRET_NAMES = [
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO", "EMAIL_FROM",
    "ADZUNA_APP_ID", "ADZUNA_APP_KEY",
    "INFOJOBS_CLIENT_ID", "INFOJOBS_CLIENT_SECRET",
    "JOOBLE_API_KEY",
]


def load_settings(config_path: str | Path | None = None, db_path: str | Path | None = None) -> Settings:
    _load_dotenv(ROOT / ".env")
    path = Path(config_path or os.environ.get("JOB_AGENT_CONFIG", DEFAULT_CONFIG))
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    secrets = {n: os.environ.get(n, "").strip() for n in SECRET_NAMES}
    return Settings(
        raw=raw,
        db_path=Path(db_path or os.environ.get("JOB_AGENT_DB", ROOT / "data" / "jobs.db")),
        reports_dir=ROOT / "reports_out",
        logs_dir=ROOT / "logs",
        secrets=secrets,
    )
