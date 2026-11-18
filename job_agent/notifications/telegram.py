"""Telegram: el canal más sencillo y gratuito. Mensaje resumen + informe HTML adjunto."""
from __future__ import annotations

import requests


class TelegramNotifier:
    name = "telegram"

    def __init__(self, settings, session=None):
        self.token = settings.secret("TELEGRAM_BOT_TOKEN")
        self.chat_ids = [c.strip() for c in (settings.secret("TELEGRAM_CHAT_ID") or "").split(",") if c.strip()]
        self.session = session or requests.Session()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_ids)

    def _api(self, method: str, **kw):
        r = self.session.post(f"https://api.telegram.org/bot{self.token}/{method}", timeout=60, **kw)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not r.ok or not data.get("ok", False):
            raise RuntimeError(f"Telegram {method}: {data.get('description', r.status_code)}")
        return data

    def send_text(self, text: str):
        for cid in self.chat_ids:
            self._api("sendMessage", data={"chat_id": cid, "text": text, "parse_mode": "HTML",
                                           "disable_web_page_preview": "true"})

    def send_report(self, subject, html, short_text, html_path):
        self.send_text(short_text)
        for cid in self.chat_ids:
            with open(html_path, "rb") as fh:
                self._api("sendDocument", data={"chat_id": cid, "caption": subject[:1000]},
                          files={"document": (html_path.name, fh, "text/html")})

    def send_alert(self, text):
        self.send_text(text)
