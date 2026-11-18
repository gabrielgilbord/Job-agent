"""Panel de control local mínimo (Flask, una sola página). Ejecuta: python main.py dashboard"""
from __future__ import annotations

import threading
from html import escape

from flask import Flask, redirect, request, url_for

from ..database import Database
from ..pipeline import run
from ..reports.report import CAT_NAMES, _place

PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Panel · Empleo Gran Canaria</title><style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f4f1ec;margin:0;color:#2b2a28}}
header{{background:#1f4e5f;color:#fff;padding:14px 22px}}header h1{{margin:0;font-size:19px}}
main{{padding:16px 22px}}form.f{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}}select,input,button{{padding:6px 8px;
border-radius:6px;border:1px solid #cfc8bb;font-size:14px}}button{{background:#1f4e5f;color:#fff;border:0;cursor:pointer}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;font-size:14px}}
th,td{{padding:8px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}}th{{background:#ebe5d9}}
.s{{font-weight:700}}.fav{{background:#fff8e1}}.dis{{opacity:.45}}a.b{{text-decoration:none;font-size:16px}}
.muted{{color:#777;font-size:12px}}</style></head><body>
<header><h1>Panel · Empleo Gran Canaria</h1><div class="muted" style="color:#d6e4e8">Última búsqueda: {last}
{running}</div></header><main>
<form class="f" method="get">
<select name="mun"><option value="">Todas las localidades</option>{muns}</select>
<select name="cat"><option value="">Todas las categorías</option>{cats}</select>
<select name="st"><option value="activas">Activas</option>{sts}</select>
<input name="min" type="number" min="0" max="100" value="{min}" style="width:80px" title="Puntuación mínima">
<label><input type="checkbox" name="fav" value="1" {favc}> Solo favoritas</label>
<button>Filtrar</button></form>
<form method="post" action="/run" style="margin-bottom:12px"><button>▶ Ejecutar búsqueda ahora (sin enviar avisos)</button>
<a href="/informe" style="margin-left:10px">Ver último informe</a></form>
<table><tr><th>Punt.</th><th>Puesto</th><th>Empresa</th><th>Localidad</th><th>Categoría</th><th>Estado</th><th>Detectada</th><th></th></tr>
{rows}</table><p class="muted">{n} ofertas</p></main></body></html>"""

STATUSES = ["nueva", "comunicada", "modificada", "republicada", "cerrada", "todas", "descartadas"]
_running = {"on": False}


def create_app(settings) -> Flask:
    app = Flask(__name__)

    def db():
        return Database(settings.db_path)

    @app.get("/")
    def index():
        d = db()
        mun, cat, st = request.args.get("mun", ""), request.args.get("cat", ""), request.args.get("st", "activas")
        mn, fav = int(request.args.get("min") or 0), request.args.get("fav") == "1"
        where, params = ["score>=?"], [mn]
        if mun:
            where.append("municipality=?"); params.append(mun)
        if cat:
            where.append("category=?"); params.append(cat)
        if st == "activas":
            where.append("status!='cerrada' AND discarded=0")
        elif st == "descartadas":
            where.append("discarded=1")
        elif st != "todas":
            where.append("status=?"); params.append(st)
        if fav:
            where.append("favorite=1")
        rows = d.query(" AND ".join(where), params, order="favorite DESC, score DESC")
        all_m = [r[0] for r in d.conn.execute("SELECT DISTINCT municipality FROM offers WHERE municipality!='' ORDER BY 1")]
        last = d.last_run()
        d.close()
        trs = []
        for r in rows:
            cls = "fav" if r["favorite"] else "dis" if r["discarded"] else ""
            trs.append(
                f'<tr class="{cls}"><td class="s">{r["score"]}</td><td><a href="{escape(r["url"])}" target="_blank">'
                f'{escape(r["title"])}</a><div class="muted">{escape((r["verdict"] or "")[:160])}</div></td>'
                f'<td>{escape(r["company"] or "")}</td><td>{escape(_place(dict(r)))}</td>'
                f'<td>{CAT_NAMES.get(r["category"], "")}</td><td>{r["status"]}</td><td>{(r["first_seen"] or "")[:10]}</td>'
                f'<td><form method="post" action="/flag/{r["id"]}" style="display:inline">'
                f'<button name="f" value="favorite" title="Favorita">{"★" if r["favorite"] else "☆"}</button> '
                f'<button name="f" value="discarded" title="Descartar/recuperar">{"↺" if r["discarded"] else "✕"}</button>'
                f'</form></td></tr>')
        opt = lambda vals, sel: "".join(f'<option value="{escape(k)}" {"selected" if k == sel else ""}>{escape(v)}</option>'
                                        for k, v in vals)
        return PAGE.format(
            last=(f"{last['finished_at'][:16].replace('T', ' ')} UTC · {last['found']} vistas, {last['new_count']} nuevas"
                  if last else "nunca"),
            running=" · ⏳ búsqueda en curso…" if _running["on"] else "",
            muns=opt([(m, m) for m in all_m], mun), cats=opt(list(CAT_NAMES.items()), cat),
            sts=opt([(s, s.capitalize()) for s in STATUSES], st), min=mn, favc="checked" if fav else "",
            rows="".join(trs) or '<tr><td colspan="8">Sin resultados</td></tr>', n=len(rows))

    @app.post("/flag/<int:oid>")
    def flag(oid):
        f = request.form.get("f")
        d = db()
        cur = d.conn.execute(f"SELECT {f} FROM offers WHERE id=?", (oid,)).fetchone() if f in ("favorite", "discarded") else None
        if cur is not None:
            d.set_flag(oid, f, not cur[0])
        d.close()
        return redirect(request.referrer or url_for("index"))

    @app.post("/run")
    def manual_run():
        if not _running["on"]:
            def job():
                _running["on"] = True
                try:
                    run(settings, "manual", notify=False)
                finally:
                    _running["on"] = False
            threading.Thread(target=job, daemon=True).start()
        return redirect(url_for("index"))

    @app.get("/informe")
    def informe():
        p = settings.reports_dir / "ultimo_informe.html"
        return p.read_text(encoding="utf-8") if p.exists() else "Aún no hay informes."

    return app


def serve(settings, port: int = 8765):
    print(f"Panel en http://127.0.0.1:{port}  (Ctrl+C para cerrar)")
    create_app(settings).run(host="127.0.0.1", port=port, debug=False)
