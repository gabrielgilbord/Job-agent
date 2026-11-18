"""Correo electrónico por SMTP (p. ej. Gmail con «contraseña de aplicación»)."""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage


class EmailNotifier:
    name = "email"

    def __init__(self, settings):
        self.host = settings.secret("SMTP_HOST")
        self.port = int(settings.secret("SMTP_PORT") or 587)
        self.user = settings.secret("SMTP_USER")
        self.password = settings.secret("SMTP_PASSWORD")
        self.to = [x.strip() for x in (settings.secret("EMAIL_TO") or "").split(",") if x.strip()]
        self.sender = settings.secret("EMAIL_FROM") or self.user

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password and self.to)

    def _send(self, subject: str, html: str | None, text: str):
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, self.sender, ", ".join(self.to)
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        ctx = ssl.create_default_context()
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=60) as s:
                s.login(self.user, self.password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=60) as s:
                s.starttls(context=ctx)
                s.login(self.user, self.password)
                s.send_message(msg)

    def send_report(self, subject, html, short_text, html_path):
        self._send(subject, html, re.sub(r"<[^>]+>", "", short_text))

    def send_alert(self, text):
        self._send("🔥 Oferta de empleo excelente", None, re.sub(r"<[^>]+>", "", text))
