"""Puente con el panel web público (carpeta site/, publicada en Vercel).

- export_data(): escribe site/data.json con las ofertas (sin datos personales de la candidata).
- apply_flags(): lee site/flags.json (favoritas/descartadas que se marcan desde el panel) y lo vuelca a la BD.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .database import Database
from .reports.report import CAT_NAMES

FIELDS = ["id", "title", "company", "municipality", "travel_min", "geo_tier", "category", "score", "status",
          "change_note", "salary_text", "contract", "workday", "published_at", "expires_at", "first_seen", "last_seen",
          "url", "source", "verdict", "remote"]


def read_flags(settings) -> dict:
    p = settings.site_dir / "flags.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"favorite": [int(x) for x in data.get("favorite", [])],
            "discarded": [int(x) for x in data.get("discarded", [])]}


def apply_flags(settings, db: Database):
    """El archivo flags.json manda: lo marcado en el panel se refleja en la base de datos."""
    f = read_flags(settings)
    for col in ("favorite", "discarded"):
        ids = f[col]
        db.conn.execute(f"UPDATE offers SET {col}=0")
        if ids:
            db.conn.execute(f"UPDATE offers SET {col}=1 WHERE id IN ({','.join('?' * len(ids))})", ids)
    db.conn.commit()


def export_data(settings, db: Database, keep_closed_days: int = 30):
    rows = db.conn.execute(
        "SELECT * FROM offers WHERE status!='cerrada' OR last_seen >= date('now', ?) ORDER BY score DESC",
        (f"-{keep_closed_days} days",)).fetchall()
    offers = []
    for r in rows:
        o = {k: r[k] for k in FIELDS}
        o["reasons"] = json.loads(r["reasons"] or "[]")
        o["warnings"] = json.loads(r["warnings"] or "[]")
        o["breakdown"] = json.loads(r["score_breakdown"] or "{}")
        offers.append(o)
    last = db.last_run()
    runs = [dict(x) for x in db.conn.execute(
        "SELECT finished_at, mode, found, relevant, new_count, ok FROM runs WHERE finished_at IS NOT NULL "
        "ORDER BY id DESC LIMIT 15").fetchall()]
    out = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "last_run": dict(last) if last else None,
        "runs": runs,
        "categories": CAT_NAMES,
        "geografia": settings.geografia,
        "offers": offers,
    }
    settings.site_dir.mkdir(parents=True, exist_ok=True)
    (settings.site_dir / "data.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                                                 encoding="utf-8")
