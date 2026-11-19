"""Envío de correo a través del panel en Vercel (/api/notify).

GitHub Actions se identifica con un token OIDC firmado por GitHub (no hace falta guardar ningún secreto en GitHub).
La función de Vercel comprueba que la petición viene de este repositorio y envía el correo con el SMTP que tiene
configurado en sus variables de entorno.
"""
from __future__ import annotations

import os

import requests

AUDIENCE = "empleo-gc"


class RelayNotifier:
    name = "email (vía panel)"

    def __init__(self, settings):
        base = (settings.busqueda.get("panel_url") or "").rstrip("/")
        self.url = f"{base}/api/notify" if base else ""
        self.req_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
        self.req_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")

    @property
    def configured(self) -> bool:
        return bool(self.url and self.req_url and self.req_token)

    def _oidc(self) -> str:
        r = requests.get(f"{self.req_url}&audience={AUDIENCE}", headers={"Authorization": f"bearer {self.req_token}"},
                         timeout=30)
        r.raise_for_status()
        return r.json()["value"]

    def _send(self, subject: str, html: str | None, text: str):
        payload = {"subject": subject, "html": html or "", "text": text}
        last = None
        for _ in range(3):
            try:
                r = requests.post(self.url, json=payload, headers={"Authorization": f"Bearer {self._oidc()}"}, timeout=60)
                if r.ok:
                    return
                last = RuntimeError(f"notify {r.status_code}: {r.text[:200]}")
                if r.status_code < 500:
                    break
            except requests.RequestException as e:
                last = e
        raise last

    def send_report(self, subject, html, text, html_path):
        self._send(subject, html, text)

    def send_alert(self, subject, html, text):
        self._send(subject, html, text)
