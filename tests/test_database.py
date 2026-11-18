from job_agent.database import Database
from job_agent.scoring.scorer import score_offer, enrich_location


def prep(settings, o):
    enrich_location(o, settings)
    return score_offer(o, settings)


def test_nueva_y_ya_vista(settings, offer):
    db = Database(settings.db_path)
    o = prep(settings, offer())
    assert db.upsert(o) == "new"
    assert db.upsert(prep(settings, offer())) == "seen"
    assert len(db.query()) == 1


def test_duplicado_entre_portales(settings, offer):
    db = Database(settings.db_path)
    db.upsert(prep(settings, offer(url="https://a/1", source="a")))
    ev = db.upsert(prep(settings, offer(url="https://b/9", source="b")))
    assert ev == "duplicate"
    rows = db.query()
    assert len(rows) == 1 and "https://b/9" in rows[0]["also_on"]


def test_modificada_tras_comunicar(settings, offer):
    db = Database(settings.db_path)
    db.upsert(prep(settings, offer()))
    db.mark_reported([r["id"] for r in db.query()])
    ev = db.upsert(prep(settings, offer(salary_text="22000 € anual bruto")))
    assert ev == "modified"
    r = db.query()[0]
    assert r["status"] == "modificada" and "salario" in r["change_note"]


def test_cierre_y_republicacion(settings, offer):
    db = Database(settings.db_path)
    db.upsert(prep(settings, offer(source="x")))
    for _ in range(3):
        db.mark_missing(["x"], set(), threshold=3)
    assert db.query()[0]["status"] == "cerrada"
    assert db.upsert(prep(settings, offer(source="x"))) == "republished"
    assert db.query()[0]["status"] == "republicada"


def test_fuente_con_error_no_cierra(settings, offer):
    db = Database(settings.db_path)
    db.upsert(prep(settings, offer(source="x")))
    for _ in range(5):
        db.mark_missing([], set(), threshold=3)   # la fuente falló => no figura en ok_sources
    assert db.query()[0]["status"] == "nueva"


def test_borrar_historial(settings, offer):
    db = Database(settings.db_path)
    db.upsert(prep(settings, offer()))
    db.clear_history()
    assert db.query() == []
