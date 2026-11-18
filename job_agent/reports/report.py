"""Generación del informe diario (HTML visual + resumen de texto para Telegram)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from ..scoring.scorer import label

CAT_NAMES = {"A": "Comercio y ventas", "B": "Turismo", "C": "Comercio internacional y administración",
             "D": "Diseño y decoración", "E": "Otras oportunidades"}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def fecha_es(dt: datetime) -> str:
    return f"{DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month - 1]} de {dt.year}"


def _d(iso: str) -> str:
    if not iso:
        return "desconocida"
    try:
        d = datetime.fromisoformat(iso[:19])
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    except ValueError:
        return iso[:10]


@dataclass
class ReportData:
    date: datetime
    pending: list  # filas sqlite (dict-like) a comunicar, score >= minimo
    new_total: int  # ofertas nuevas detectadas (todas las puntuaciones)
    companies: list = field(default_factory=list)
    followed: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    sources_summary: list = field(default_factory=list)
    closed_today: int = 0

    def __post_init__(self):
        rows = [dict(r) for r in self.pending]
        for r in rows:
            for k in ("reasons", "warnings", "score_breakdown"):
                if isinstance(r.get(k), str):
                    try:
                        r[k] = json.loads(r[k])
                    except ValueError:
                        r[k] = [] if k != "score_breakdown" else {}
        self.rows = rows
        top = [r for r in rows if r["score"] >= 80][:5]
        if not top:
            top = [r for r in rows if r["score"] >= 70][:5]
        ids = {r["id"] for r in top}
        self.top = top
        self.others = [r for r in rows if 70 <= r["score"] < 80 and r["id"] not in ids]
        self.secondary = [r for r in rows if 60 <= r["score"] < 70 and r["id"] not in ids]
        self.design = [r for r in rows if r["category"] == "D"]
        self.studies = [r for r in rows if r["category"] in ("B", "C") and r["score"] >= 65]
        now = self.date.replace(tzinfo=None)
        self.urgent = []
        for r in rows:
            exp = r.get("expires_at") or ""
            try:
                soon = exp and datetime.fromisoformat(exp[:19]) <= now + timedelta(days=5)
            except ValueError:
                soon = False
            if r["score"] >= 70 and (soon or "inmediata" in (r.get("description") or "").lower()):
                self.urgent.append(r)

    @property
    def interesting(self) -> int:
        return len(self.rows)


CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#f4f1ec;color:#2b2a28;margin:0;padding:0}
.wrap{max-width:760px;margin:0 auto;padding:20px}
.hero{background:#1f4e5f;color:#fff;border-radius:14px;padding:22px 24px}
.hero h1{margin:0 0 6px;font-size:22px;letter-spacing:.3px}.hero p{margin:2px 0;opacity:.9}
.stats{display:flex;gap:10px;margin:14px 0 0}.stat{background:rgba(255,255,255,.14);border-radius:10px;padding:8px 14px}
.stat b{display:block;font-size:22px}
h2{font-size:17px;margin:28px 0 10px;color:#1f4e5f;border-bottom:2px solid #e2dccf;padding-bottom:6px}
.card{background:#fff;border-radius:12px;padding:16px 18px;margin:10px 0;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.card h3{margin:0 0 4px;font-size:16px}.muted{color:#6d6a64;font-size:13px}
.score{float:right;font-weight:700;border-radius:20px;padding:4px 10px;font-size:14px;color:#fff}
.s90{background:#1b7f4c}.s80{background:#2d8f6f}.s70{background:#c08a1e}.s60{background:#8a8780}
.kv{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}.kv td{padding:3px 0;vertical-align:top}
.kv td:first-child{color:#6d6a64;width:150px}
.why{background:#f1f7f4;border-left:3px solid #2d8f6f;padding:8px 10px;font-size:14px;margin-top:8px;border-radius:4px}
.warn{color:#9a5b00;font-size:13px}.badge{display:inline-block;font-size:11px;border-radius:6px;padding:1px 7px;
background:#e8e2d6;margin-right:4px}.chg{background:#fde7c4}
.btn{display:inline-block;background:#1f4e5f;color:#fff !important;text-decoration:none;padding:7px 14px;border-radius:8px;
margin-top:10px;font-size:14px}
ul.compact{padding-left:18px}ul.compact li{margin:5px 0}
.foot{font-size:12px;color:#8a8780;margin-top:30px}
"""


def _score_cls(s):
    return "s90" if s >= 90 else "s80" if s >= 80 else "s70" if s >= 70 else "s60"


def _place(r) -> str:
    if r.get("remote") and not r.get("municipality"):
        return "Teletrabajo"
    m = r.get("municipality") or "Gran Canaria (sin concretar)"
    if r.get("travel_min") is not None:
        m += f" · ~{r['travel_min']} min desde San Mateo"
    return m


def _salary(r) -> str:
    if r.get("salary_text"):
        return escape(r["salary_text"])
    return "No publicado"


def card(r, full=True) -> str:
    badges = f'<span class="badge">{CAT_NAMES.get(r["category"], "")}</span><span class="badge">{escape(r["source"])}</span>'
    if r["status"] in ("modificada", "republicada"):
        badges += f'<span class="badge chg">{r["status"]}: {escape(r.get("change_note") or "")}</span>'
    head = (f'<div class="card"><span class="score {_score_cls(r["score"])}">{r["score"]}/100</span>'
            f'<h3>{escape(r["title"])}</h3><div class="muted">{escape(r.get("company") or "Empresa no indicada")} · '
            f'{escape(_place(r))}</div><div style="margin-top:6px">{badges}</div>')
    if not full:
        return head + f'<a class="btn" href="{escape(r["url"])}">Ver oferta</a></div>'
    reasons = "".join(f"<li>{escape(x)}</li>" for x in r.get("reasons", [])[:4]) or "<li>Encaja con su perfil</li>"
    warns = "".join(f'<div class="warn">⚠ {escape(x)}</div>' for x in r.get("warnings", [])[:4])
    reqs = escape((r.get("requirements") or "").replace("\n", " · ")[:300]) or "No detallados"
    return head + f"""
<table class="kv">
<tr><td>Por qué encaja</td><td><ul class="compact">{reasons}</ul></td></tr>
<tr><td>Salario</td><td>{_salary(r)}</td></tr>
<tr><td>Contrato</td><td>{escape(r.get("contract") or "No indicado")}</td></tr>
<tr><td>Jornada</td><td>{escape(r.get("workday") or "No indicada")}</td></tr>
<tr><td>Requisitos</td><td>{reqs}</td></tr>
<tr><td>Publicada</td><td>{_d(r.get("published_at"))}</td></tr>
</table>{warns}
<div class="why">{escape(r.get("verdict") or "")}</div>
<a class="btn" href="{escape(r["url"])}">Inscribirse / ver oferta →</a></div>"""


def render_html(d: ReportData, panel_url: str = "") -> str:
    p = []
    p.append(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Informe de empleo — {d.date:%d/%m/%Y}</title>
<style>{CSS}</style></head><body><div class="wrap">
<div class="hero"><h1>INFORME DIARIO DE EMPLEO — GRAN CANARIA</h1>
<p>Fecha de búsqueda: {fecha_es(d.date)}, {d.date:%H:%M} (hora canaria)</p>
<div class="stats"><div class="stat"><b>{d.new_total}</b>ofertas nuevas encontradas</div>
<div class="stat"><b>{d.interesting}</b>ofertas interesantes</div>
<div class="stat"><b>{len(d.top)}</b>destacadas</div></div>
{f'<a class="btn" style="background:#fff;color:#1f4e5f !important" href="{escape(panel_url)}">Abrir panel de ofertas</a>' if panel_url else ''}
</div>""")

    if not d.rows:
        p.append('<h2>Sin novedades relevantes</h2><div class="card">Hoy se ha realizado la búsqueda en todas las fuentes '
                 'y no han aparecido ofertas nuevas que merezcan la pena. Mejor no rellenar con ofertas mediocres: '
                 'mañana se vuelve a buscar.</div>')
    else:
        p.append("<h2>🏆 TOP 5 — MEJORES OPORTUNIDADES</h2>")
        p.extend(card(r) for r in d.top)
        if d.others:
            p.append("<h2>Otras ofertas interesantes (70-79)</h2>")
            p.extend(card(r) for r in d.others)
        if d.secondary:
            p.append("<h2>Oportunidades secundarias (60-69)</h2><ul class='compact'>")
            p.extend(f'<li><a href="{escape(r["url"])}">{escape(r["title"])}</a> — {escape(r.get("company") or "")} '
                     f'· {escape(_place(r))} · <b>{r["score"]}</b></li>' for r in d.secondary)
            p.append("</ul>")
        p.append("<h2>🎨 Oportunidades de diseño y decoración</h2>")
        if d.design:
            p.extend(card(r, full=False) for r in d.design)
        else:
            p.append('<div class="muted">Hoy no hay ofertas nuevas de escaparatismo, decoración, mobiliario o visual '
                     'merchandising en la zona.</div>')
        p.append("<h2>🎓 Oportunidades relacionadas con sus estudios</h2>")
        if d.studies:
            p.append("<ul class='compact'>")
            p.extend(f'<li><b>{escape(r["title"])}</b> ({CAT_NAMES[r["category"]]}) — {escape(r.get("company") or "")}, '
                     f'{escape(_place(r))}. <b>{r["score"]}/100</b>. <a href="{escape(r["url"])}">Ver</a></li>'
                     for r in d.studies)
            p.append("</ul>")
        else:
            p.append('<div class="muted">Sin ofertas nuevas de Turismo o Comercio Internacional que encajen hoy.</div>')

    p.append("<h2>🏢 Empresas que merece la pena seguir</h2><ul class='compact'>")
    for c in d.companies:
        cats = ", ".join(CAT_NAMES.get(x, x) for x in (c["cats"] or "").split(",") if x)
        p.append(f"<li><b>{escape(c['company'])}</b> — {c['n']} ofertas compatibles en 90 días (mejor: {c['best']}) · {cats}</li>")
    for f in d.followed[:8]:
        p.append(f'<li><a href="{escape(f.get("web", ""))}">{escape(f.get("nombre", ""))}</a> (portal de empleo a revisar)</li>')
    p.append("</ul>")

    p.append("<h2>📌 Resumen final</h2><div class='card'>")
    if d.rows:
        best3 = d.rows[:3]
        p.append("<b>Las tres mejores del día:</b><ol>" + "".join(
            f'<li><a href="{escape(r["url"])}">{escape(r["title"])}</a> — {escape(r.get("company") or "")} ({r["score"]})</li>'
            for r in best3) + "</ol>")
        b = d.rows[0]
        p.append(f'<p><b>La que más recomiendo:</b> {escape(b["title"])} en {escape(b.get("company") or "empresa no indicada")}. '
                 f'{escape(b.get("verdict") or "")}</p>')
        if d.urgent:
            p.append("<p><b>Inscripción urgente:</b></p><ul>" + "".join(
                f'<li><a href="{escape(r["url"])}">{escape(r["title"])}</a> — caduca {_d(r.get("expires_at"))}</li>'
                for r in d.urgent) + "</ul>")
        else:
            p.append("<p><b>Inscripción urgente:</b> ninguna oferta caduca en los próximos 5 días.</p>")
    else:
        p.append("<p>No hay ofertas nuevas relevantes hoy.</p>")
    p.append("</div>")

    src = " · ".join(d.sources_summary)
    err = ("<br>Incidencias: " + escape("; ".join(d.errors))) if d.errors else ""
    p.append(f'<div class="foot">Fuentes consultadas: {escape(src)}. Ofertas cerradas/caducadas detectadas: '
             f'{d.closed_today}.{err}<br>Las puntuaciones se calculan automáticamente; los datos no publicados '
             f'aparecen como «no indicado». El agente nunca envía candidaturas: la inscripción la haces tú.</div>')
    p.append("</div></body></html>")
    return "\n".join(p)


def render_text(d: ReportData, panel_url: str = "") -> str:
    """Versión en texto plano del correo (para clientes que no muestran HTML)."""
    lines = [f"INFORME DIARIO DE EMPLEO — GRAN CANARIA ({d.date:%d/%m/%Y})",
             f"Nuevas: {d.new_total} · Interesantes: {d.interesting}", ""]
    if not d.rows:
        lines.append("Búsqueda realizada. Hoy no hay ofertas nuevas que merezcan la pena.")
    for i, r in enumerate(d.top, 1):
        lines += [f"{i}. {r['title']} — {r.get('company') or '¿?'} ({r['score']}/100, {label(r['score'])})",
                  f"   {_place(r)} · {r.get('salary_text') or 'salario no publicado'} · {r.get('contract') or '¿contrato?'}",
                  f"   {r['url']}"]
    if d.others:
        lines += ["", "Otras interesantes:"] + [f"- {r['title']} ({r['score']}) {r['url']}" for r in d.others]
    if panel_url:
        lines += ["", f"Panel: {panel_url}"]
    return "\n".join(lines)


def render_alert(rows, panel_url: str = "") -> tuple[str, str]:
    """(html, texto) del aviso inmediato de ofertas excelentes."""
    rows = [dict(r) for r in rows]
    for r in rows:
        for k in ("reasons", "warnings"):
            if isinstance(r.get(k), str):
                try:
                    r[k] = json.loads(r[k])
                except ValueError:
                    r[k] = []
    html = (f'<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="wrap">'
            f'<div class="hero"><h1>🔥 Oferta excelente detectada</h1><p>No esperes al informe de mañana.</p></div>'
            + "".join(card(r) for r in rows)
            + (f'<p><a href="{escape(panel_url)}">Abrir el panel</a></p>' if panel_url else "") + "</div></body></html>")
    text = "\n\n".join(f"{r['title']} — {r.get('company') or ''} ({r['score']}/100)\n{_place(r)}\n{r['url']}" for r in rows)
    return html, text


def local_now(tz: str = "Atlantic/Canary") -> datetime:
    return datetime.now(ZoneInfo(tz))
