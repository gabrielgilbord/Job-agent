#!/usr/bin/env python3
"""Agente de búsqueda de empleo — Gran Canaria.

Uso:
  python main.py run                 # búsqueda + informe + notificación (ahora mismo)
  python main.py run --scheduled     # igual, pero solo si toca (08:30 Canarias, una vez al día)
  python main.py run --no-notify     # genera el informe sin enviarlo
  python main.py alerts              # búsqueda rápida: solo avisa de ofertas > 90
  python main.py dashboard           # panel de control local en http://127.0.0.1:8765
  python main.py test-notify         # envía un mensaje de prueba a los canales configurados
  python main.py reset-history       # borra todo el historial (pide confirmación)
"""
import argparse
import sys

from job_agent.config import load_settings
from job_agent.pipeline import run


def main(argv=None):
    ap = argparse.ArgumentParser(description="Agente de empleo Gran Canaria")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scheduled", action="store_true")
    r.add_argument("--no-notify", action="store_true")
    sub.add_parser("alerts")
    d = sub.add_parser("dashboard")
    d.add_argument("--port", type=int, default=8765)
    sub.add_parser("test-notify")
    rh = sub.add_parser("reset-history")
    rh.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    s = load_settings()

    if a.cmd == "run":
        res = run(s, "daily", notify=not a.no_notify, scheduled=a.scheduled)
        if res.skipped_reason:
            print("Omitido:", res.skipped_reason)
        else:
            print(f"Encontradas {res.found} · relevantes {res.relevant} · nuevas {res.events['new']} · "
                  f"informe: {res.report_path}")
            for e in res.errors:
                print("  ! ", e)
    elif a.cmd == "alerts":
        res = run(s, "alerts")
        print(f"Alertas: {res.events}")
    elif a.cmd == "dashboard":
        from job_agent.dashboard.app import serve
        serve(s, port=a.port)
    elif a.cmd == "test-notify":
        from job_agent import notifications
        chans = notifications.notifiers(s)
        if not chans:
            print("No hay ningún canal configurado (revisa .env o los secretos de GitHub).")
            return 1
        errs = notifications.send_alert(s, "✅ Prueba del agente de empleo: las notificaciones funcionan.")
        print("Errores:" if errs else "Enviado por: " + ", ".join(c.name for c in chans), *errs)
        return 1 if errs else 0
    elif a.cmd == "reset-history":
        if not a.yes and input("¿Borrar TODO el historial? escribe 'si': ").strip().lower() != "si":
            return 0
        from job_agent.database import Database
        Database(s.db_path).clear_history()
        print("Historial borrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
