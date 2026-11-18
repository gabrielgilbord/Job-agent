"""Notificaciones por correo electrónico (único canal)."""
from __future__ import annotations

import logging

from .email import EmailNotifier

log = logging.getLogger("job_agent.notify")


def notifiers(settings) -> list:
    n = EmailNotifier(settings)
    return [n] if n.configured else []


def send_report(settings, subject: str, html: str, text: str, html_path) -> list[str]:
    """Envía el informe. Devuelve lista de errores (vacía si todo OK o si no hay correo configurado)."""
    errors = []
    chans = notifiers(settings)
    if not chans:
        log.warning("Correo no configurado: el informe solo queda en %s y en el panel web", html_path)
    for n in chans:
        try:
            n.send_report(subject, html, text, html_path)
            log.info("Informe enviado por %s", n.name)
        except Exception as e:
            log.exception("Fallo enviando por %s", n.name)
            errors.append(f"{n.name}: {e}")
    return errors


def send_alert(settings, subject: str, html: str, text: str) -> list[str]:
    errors = []
    for n in notifiers(settings):
        try:
            n.send_alert(subject, html, text)
        except Exception as e:
            errors.append(f"{n.name}: {e}")
    return errors
