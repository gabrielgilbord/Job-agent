"""Historial en SQLite: alta de ofertas, detección de duplicados y ciclo de vida.

Estados:
  nueva        -> detectada y aún no incluida en un informe diario
  comunicada   -> ya apareció en un informe
  modificada   -> cambió salario/contrato/jornada/requisitos tras comunicarse (se vuelve a destacar)
  cerrada      -> dejó de aparecer en su fuente N ejecuciones seguidas o pasó su fecha de caducidad
  republicada  -> estaba cerrada y vuelve a aparecer, o tiene nueva fecha de publicación
Marcas de usuario (panel): favorita, descartada.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Offer

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT,
    company TEXT, title TEXT, location_text TEXT, municipality TEXT, travel_min INTEGER, geo_tier TEXT,
    category TEXT, published_at TEXT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
    salary_text TEXT, salary_min REAL, salary_max REAL, contract TEXT, workday TEXT,
    requirements TEXT, education TEXT, experience TEXT, description TEXT, expires_at TEXT, remote INTEGER DEFAULT 0,
    score INTEGER, score_breakdown TEXT, reasons TEXT, warnings TEXT, verdict TEXT,
    status TEXT NOT NULL DEFAULT 'nueva', change_note TEXT DEFAULT '',
    content_hash TEXT, missed_runs INTEGER DEFAULT 0,
    reported_at TEXT, alerted_at TEXT,
    favorite INTEGER DEFAULT 0, discarded INTEGER DEFAULT 0,
    also_on TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_offers_url ON offers(url);
CREATE INDEX IF NOT EXISTS ix_offers_fp ON offers(fingerprint);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT, finished_at TEXT, mode TEXT, local_date TEXT,
    found INTEGER, relevant INTEGER, new_count INTEGER, errors TEXT, ok INTEGER
);
CREATE TABLE IF NOT EXISTS source_runs (
    run_id INTEGER, source TEXT, ok INTEGER, fetched INTEGER, error TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.commit()
        self.conn.close()

    # ------------------------------------------------------------------ runs
    def start_run(self, mode: str, local_date: str) -> int:
        cur = self.conn.execute("INSERT INTO runs(started_at, mode, local_date, ok) VALUES (?,?,?,0)",
                                (now_iso(), mode, local_date))
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, found: int, relevant: int, new_count: int, errors: list[str], ok: bool):
        self.conn.execute("UPDATE runs SET finished_at=?, found=?, relevant=?, new_count=?, errors=?, ok=? WHERE id=?",
                          (now_iso(), found, relevant, new_count, json.dumps(errors, ensure_ascii=False), int(ok), run_id))
        self.conn.commit()

    def log_source(self, run_id: int, source: str, ok: bool, fetched: int, error: str = ""):
        self.conn.execute("INSERT INTO source_runs VALUES (?,?,?,?,?)", (run_id, source, int(ok), fetched, error))
        self.conn.commit()

    def daily_report_done(self, local_date: str) -> bool:
        r = self.conn.execute("SELECT 1 FROM runs WHERE mode='daily' AND local_date=? AND ok=1", (local_date,)).fetchone()
        return r is not None

    def last_run(self):
        return self.conn.execute("SELECT * FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()

    # ------------------------------------------------------------------ offers
    def _find_existing(self, o: Offer):
        r = self.conn.execute("SELECT * FROM offers WHERE url=?", (o.url,)).fetchone()
        if r:
            return r
        # mismo empresa+puesto+municipio en otra fuente / otra URL => duplicado
        if o.company:
            return self.conn.execute("SELECT * FROM offers WHERE fingerprint=? ORDER BY id LIMIT 1",
                                     (o.fingerprint,)).fetchone()
        return None

    def upsert(self, o: Offer) -> str:
        """Inserta o actualiza. Devuelve el evento: new | seen | modified | republished | duplicate."""
        ts = now_iso()
        ex = self._find_existing(o)
        fields = dict(
            fingerprint=o.fingerprint, source=o.source, source_id=o.source_id, company=o.company, title=o.title,
            location_text=o.location_text, municipality=o.municipality, travel_min=o.travel_min, geo_tier=o.geo_tier,
            category=o.category, published_at=o.published_at, salary_text=o.salary_text, salary_min=o.salary_min,
            salary_max=o.salary_max, contract=o.contract, workday=o.workday, requirements=o.requirements[:4000],
            education=o.education, experience=o.experience, description=o.description[:8000], expires_at=o.expires_at,
            remote=int(o.remote), score=o.score, score_breakdown=json.dumps(o.score_breakdown, ensure_ascii=False),
            reasons=json.dumps(o.reasons, ensure_ascii=False), warnings=json.dumps(o.warnings, ensure_ascii=False),
            verdict=o.verdict, content_hash=o.content_hash,
        )
        if ex is None:
            fields.update(url=o.url, first_seen=ts, last_seen=ts, status="nueva", missed_runs=0)
            cols = ",".join(fields)
            self.conn.execute(f"INSERT INTO offers({cols}) VALUES ({','.join('?' * len(fields))})", list(fields.values()))
            return "new"

        # duplicado en otra fuente/URL: anotar y no crear otra fila
        if ex["url"] != o.url:
            also = set(filter(None, (ex["also_on"] or "").split(" ")))
            also.add(o.url)
            self.conn.execute("UPDATE offers SET also_on=?, last_seen=?, missed_runs=0 WHERE id=?",
                              (" ".join(sorted(also)), ts, ex["id"]))
            if ex["status"] == "cerrada":
                self.conn.execute("UPDATE offers SET status='republicada', change_note=? WHERE id=?",
                                  ("Vuelve a publicarse", ex["id"]))
                return "republished"
            return "duplicate"

        event, status, note = "seen", ex["status"], ex["change_note"] or ""
        if ex["status"] == "cerrada":
            event, status, note = "republished", "republicada", "Vuelve a publicarse"
        elif o.published_at and ex["published_at"] and o.published_at[:10] > ex["published_at"][:10] \
                and ex["status"] != "nueva":
            event, status, note = "republished", "republicada", f"Nueva fecha de publicación ({o.published_at[:10]})"
        elif ex["content_hash"] != o.content_hash and ex["status"] != "nueva":
            changes = []
            if (ex["salary_text"] or "") != o.salary_text or ex["salary_min"] != o.salary_min:
                changes.append(f"salario: «{ex['salary_text'] or 'no publicado'}» → «{o.salary_text or 'no publicado'}»")
            if (ex["contract"] or "") != o.contract:
                changes.append(f"contrato: {ex['contract'] or '?'} → {o.contract or '?'}")
            if (ex["workday"] or "") != o.workday:
                changes.append(f"jornada: {ex['workday'] or '?'} → {o.workday or '?'}")
            if not changes:
                changes.append("requisitos actualizados")
            event, status, note = "modified", "modificada", "; ".join(changes)
        fields.update(last_seen=ts, missed_runs=0, status=status, change_note=note)
        sets = ",".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE offers SET {sets} WHERE id=?", [*fields.values(), ex["id"]])
        return event

    def mark_missing(self, sources_ok: list[str], seen_urls: set[str], threshold: int) -> int:
        """Incrementa missed_runs de ofertas de fuentes que funcionaron hoy y no se vieron; cierra al superar el umbral."""
        closed = 0
        if not sources_ok:
            return 0
        q = f"SELECT id, url, missed_runs, expires_at FROM offers WHERE status!='cerrada' AND source IN ({','.join('?' * len(sources_ok))})"
        today = now_iso()[:10]
        for r in self.conn.execute(q, sources_ok).fetchall():
            if r["url"] in seen_urls:
                continue
            missed = r["missed_runs"] + 1
            if missed >= threshold:
                self.conn.execute("UPDATE offers SET missed_runs=?, status='cerrada', change_note='Ya no aparece publicada' WHERE id=?",
                                  (missed, r["id"]))
                closed += 1
            else:
                self.conn.execute("UPDATE offers SET missed_runs=? WHERE id=?", (missed, r["id"]))
        # caducidad explícita
        cur = self.conn.execute("UPDATE offers SET status='cerrada', change_note='Fecha de caducidad superada' "
                                "WHERE status!='cerrada' AND expires_at!='' AND expires_at IS NOT NULL AND substr(expires_at,1,10) < ?",
                                (today,))
        self.conn.commit()
        return closed + cur.rowcount

    def to_report(self, min_score: int) -> list[sqlite3.Row]:
        """Ofertas pendientes de comunicar: nuevas, modificadas o republicadas (no descartadas por el usuario)."""
        return self.conn.execute(
            "SELECT * FROM offers WHERE status IN ('nueva','modificada','republicada') AND discarded=0 AND score>=? "
            "ORDER BY score DESC, travel_min ASC", (min_score,)).fetchall()

    def pending_alerts(self, min_score: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM offers WHERE status IN ('nueva','modificada','republicada') AND discarded=0 AND score>=? "
            "AND alerted_at IS NULL ORDER BY score DESC", (min_score,)).fetchall()

    def mark_alerted(self, ids: list[int]):
        self.conn.executemany("UPDATE offers SET alerted_at=? WHERE id=?", [(now_iso(), i) for i in ids])
        self.conn.commit()

    def mark_reported(self, ids: list[int]):
        self.conn.executemany("UPDATE offers SET status='comunicada', reported_at=?, change_note='' WHERE id=?",
                              [(now_iso(), i) for i in ids])
        self.conn.commit()

    def count_new_since_last_report(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM offers WHERE status='nueva'").fetchone()[0]

    def companies_to_follow(self, min_score: int = 60, days: int = 90, min_offers: int = 2) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT company, COUNT(*) n, MAX(score) best, GROUP_CONCAT(DISTINCT category) cats FROM offers "
            "WHERE company!='' AND score>=? AND first_seen >= date('now', ?) GROUP BY lower(company) "
            "HAVING n>=? ORDER BY n DESC, best DESC LIMIT 10", (min_score, f"-{days} days", min_offers)).fetchall()

    # ------------------------------------------------------------------ panel
    def query(self, where: str = "1=1", params=(), order="score DESC", limit=500):
        return self.conn.execute(f"SELECT * FROM offers WHERE {where} ORDER BY {order} LIMIT {int(limit)}", params).fetchall()

    def set_flag(self, offer_id: int, flag: str, value: bool):
        assert flag in ("favorite", "discarded")
        self.conn.execute(f"UPDATE offers SET {flag}=? WHERE id=?", (int(value), offer_id))
        self.conn.commit()

    def clear_history(self):
        self.conn.executescript("DELETE FROM offers; DELETE FROM runs; DELETE FROM source_runs;")
        self.conn.commit()
