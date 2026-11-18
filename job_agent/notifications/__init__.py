"""Envío de notificaciones. Cada canal es opcional: si no está configurado, se omite sin error."""
from __future__ import annotations

import logging

from .telegram import TelegramNotifier
from .email import EmailNotifier

log = logging.getLogger("job_agent.notify")


def notifiers(settings) -> list:
    out = []
    for cls in (TelegramNotifier, EmailNotifier):
        n = cls(settings)
        if n.configured:
            out.append(n)
    return out


def send_report(settings, subject: str, html: str, short_text: str, html_path) -> list[str]:
    """Envía el informe por todos los canales configurados. Devuelve lista de errores (vacía si todo OK)."""
    errors = []
    chans = notifiers(settings)
    if not chans:
        log.warning("No hay canales de notificación configurados: el informe solo queda en %s", html_path)
    for n in chans:
        try:
            n.send_report(subject, html, short_text, html_path)
            log.info("Informe enviado por %s", n.name)
        except Exception as e:  # un canal caído no debe tumbar el resto
            log.exception("Fallo enviando por %s", n.name)
            errors.append(f"{n.name}: {e}")
    return errors


def send_alert(settings, text: str) -> list[str]:
    errors = []
    for n in notifiers(settings):
        try:
            n.send_alert(text)
        except Exception as e:
            errors.append(f"{n.name}: {e}")
    return errors
