"""Orquestación de una ejecución: buscar → filtrar → puntuar → guardar → informar → notificar."""
from __future__ import annotations

import logging
import logging.handlers
from dataclasses import dataclass, field
from datetime import datetime

from . import notifications
from .config import Settings
from .database import Database
from .reports.report import ReportData, render_html, render_telegram, render_alert, local_now
from .scoring.scorer import score_offer, enrich_location
from .search import ALL_SOURCES
from .search.base import SourceUnavailable

log = logging.getLogger("job_agent")


def setup_logging(settings: Settings, verbose: bool = False):
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("job_agent")
    if root.handlers:
        return
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(settings.logs_dir / "agent.log", maxBytes=1_000_000, backupCount=3,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)


@dataclass
class RunResult:
    found: int = 0
    relevant: int = 0
    events: dict = field(default_factory=lambda: {"new": 0, "seen": 0, "modified": 0, "republished": 0, "duplicate": 0})
    closed: int = 0
    errors: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    report_path: str = ""
    skipped_reason: str = ""


def should_run_scheduled(settings: Settings, db: Database, now: datetime | None = None) -> tuple[bool, str]:
    """Para el disparador programado: ejecutar solo una vez al día, a partir de la hora local configurada.
    GitHub Actions lanza el flujo a dos horas UTC (07:30 y 08:30) para cubrir horario de invierno y verano;
    esta comprobación hace que solo se ejecute el que coincide con las 08:30 en Canarias."""
    tz = settings.busqueda.get("zona_horaria", "Atlantic/Canary")
    now = now or local_now(tz)
    hh, mm = (int(x) for x in str(settings.busqueda.get("hora_local", "08:30")).split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if db.daily_report_done(now.date().isoformat()):
        return False, "el informe de hoy ya se envió"
    if now < target.replace(minute=max(0, mm - 15)):
        return False, f"aún no son las {hh:02d}:{mm:02d} en Canarias (son las {now:%H:%M})"
    return True, ""


def collect(settings: Settings, db: Database, run_id: int, res: RunResult, sources=None):
    offers = []
    ok_sources = []
    for cls in (sources or ALL_SOURCES):
        src = cls(settings)
        if not src.enabled:
            res.sources.append(f"{src.name}: desactivada")
            continue
        try:
            got = src.fetch()
            offers.extend(got)
            ok_sources.append(src.name)
            res.sources.append(f"{src.name}: {len(got)}")
            db.log_source(run_id, src.name, True, len(got))
            log.info("%s → %d ofertas", src.name, len(got))
        except SourceUnavailable as e:
            res.sources.append(f"{src.name}: sin configurar")
            db.log_source(run_id, src.name, False, 0, str(e))
            log.info("%s omitida (%s)", src.name, e)
        except Exception as e:  # una fuente caída no detiene el resto
            res.errors.append(f"{src.name}: {type(e).__name__}: {str(e)[:160]}")
            res.sources.append(f"{src.name}: ERROR")
            db.log_source(run_id, src.name, False, 0, str(e)[:500])
            log.exception("Fallo en la fuente %s", src.name)
    return offers, ok_sources


def process(settings: Settings, offers) -> list:
    """Filtra por geografía y perfil, puntúa y elimina duplicados dentro de la propia ejecución."""
    max_min = settings.busqueda.get("tiempo_desplazamiento_max_min", 60)
    kept = {}
    for o in offers:
        if not o.url or not o.title:
            continue
        state = enrich_location(o, settings)
        if state in ("otra_isla", "fuera", "desconocido"):
            continue
        score_offer(o, settings)
        if not o.category or o.score <= 0:
            continue
        if o.travel_min is not None and o.travel_min > max_min and o.score < 80:
            continue  # lejos y no excepcional
        if o.geo_tier == "baja" and o.score < 75:
            continue
        key = o.fingerprint if o.company else o.url
        prev = kept.get(key)
        if prev is None or o.score > prev.score:
            kept[key] = o
    return sorted(kept.values(), key=lambda x: -x.score)


def run(settings: Settings, mode: str = "daily", notify: bool = True, scheduled: bool = False, sources=None,
        now: datetime | None = None) -> RunResult:
    setup_logging(settings)
    tz = settings.busqueda.get("zona_horaria", "Atlantic/Canary")
    now = now or local_now(tz)
    db = Database(settings.db_path)
    res = RunResult()
    try:
        if scheduled and mode == "daily":
            go, why = should_run_scheduled(settings, db, now)
            if not go:
                res.skipped_reason = why
                log.info("Ejecución programada omitida: %s", why)
                return res
        run_id = db.start_run(mode, now.date().isoformat())
        offers, ok_sources = collect(settings, db, run_id, res, sources)
        res.found = len(offers)
        relevant = process(settings, offers)
        res.relevant = len(relevant)
        seen_urls = set()
        for o in relevant:
            ev = db.upsert(o)
            res.events[ev] += 1
            seen_urls.add(o.url)
        # las ofertas vistas pero descartadas por el filtro también cuentan como "siguen publicadas"
        seen_urls |= {o.url for o in offers}
        db.conn.commit()
        res.closed = db.mark_missing(ok_sources, seen_urls, int(settings.busqueda.get("dias_sin_ver_para_cerrar", 3)))

        # Alerta inmediata (> umbral)
        thr = int(settings.busqueda.get("puntuacion_alerta_inmediata", 90))
        alerts = db.pending_alerts(thr)
        if alerts and notify:
            errs = notifications.send_alert(settings, render_alert(alerts))
            res.errors.extend(errs)
            if not errs:
                db.mark_alerted([a["id"] for a in alerts])

        if mode == "daily":
            min_score = int(settings.busqueda.get("puntuacion_minima_informe", 60))
            pending = db.to_report(min_score)
            data = ReportData(
                date=now, pending=pending, new_total=db.count_new_since_last_report(),
                companies=db.companies_to_follow(), followed=settings.raw.get("empresas_a_seguir", []),
                errors=res.errors, sources_summary=res.sources, closed_today=res.closed)
            html = render_html(data)
            settings.reports_dir.mkdir(parents=True, exist_ok=True)
            path = settings.reports_dir / f"informe_{now:%Y-%m-%d}.html"
            path.write_text(html, encoding="utf-8")
            (settings.reports_dir / "ultimo_informe.html").write_text(html, encoding="utf-8")
            res.report_path = str(path)
            send_errors = []
            if notify:
                subject = (f"Empleo GC {now:%d/%m}: {len(data.rows)} ofertas interesantes"
                           if data.rows else f"Empleo GC {now:%d/%m}: sin novedades relevantes")
                send_errors = notifications.send_report(settings, subject, html, render_telegram(data), path)
                res.errors.extend(send_errors)
            if not send_errors:
                # todo lo pendiente (también lo < mínimo) pasa a "comunicada" para no repetirlo mañana
                ids = [r["id"] for r in db.conn.execute(
                    "SELECT id FROM offers WHERE status IN ('nueva','modificada','republicada')").fetchall()]
                db.mark_reported(ids)
        all_failed = not ok_sources
        db.finish_run(run_id, res.found, res.relevant, res.events["new"], res.errors, ok=not all_failed)
        log.info("Fin: %d encontradas, %d relevantes, eventos=%s, cerradas=%d, errores=%d",
                 res.found, res.relevant, res.events, res.closed, len(res.errors))
        return res
    finally:
        db.close()
