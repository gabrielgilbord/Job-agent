from datetime import datetime
from zoneinfo import ZoneInfo

from job_agent import notifications
from job_agent.database import Database
from job_agent.pipeline import run, should_run_scheduled
from job_agent.search.base import Source, SourceUnavailable
from conftest import make_offer

TZ = ZoneInfo("Atlantic/Canary")


class FakeOK(Source):
    name = "fake_ok"

    def fetch(self):
        return [make_offer(url="https://ok/1"), make_offer(title="Camarero", url="https://ok/2"),
                make_offer(title="Asesora de decoración", url="https://ok/3", company="Deco Telde", location_text="Telde"),
                make_offer(title="Dependienta", url="https://ok/4", location_text="Adeje, Tenerife")]


class FakeBroken(Source):
    name = "fake_broken"

    def fetch(self):
        raise ConnectionError("portal caído")


class FakeNoKey(Source):
    name = "fake_nokey"

    def fetch(self):
        raise SourceUnavailable("sin clave")


def test_busqueda_e_informe_con_fuente_caida(settings):
    res = run(settings, notify=False, sources=[FakeBroken, FakeOK, FakeNoKey], now=datetime(2026, 11, 18, 8, 30, tzinfo=TZ))
    assert res.found == 4 and res.relevant == 2          # camarero y Tenerife descartados
    assert any("fake_broken" in e for e in res.errors)   # el error se registra…
    html = open(res.report_path, encoding="utf-8").read()  # …pero el informe se genera igual
    assert "INFORME DIARIO DE EMPLEO" in html and "Asesora de decoración" in html
    assert "Camarero" not in html


def test_no_repite_ofertas_al_dia_siguiente(settings):
    run(settings, notify=False, sources=[FakeOK], now=datetime(2026, 11, 18, 8, 30, tzinfo=TZ))
    res = run(settings, notify=False, sources=[FakeOK], now=datetime(2026, 11, 19, 8, 30, tzinfo=TZ))
    assert res.events["new"] == 0
    assert "Sin novedades relevantes" in open(res.report_path, encoding="utf-8").read()


def test_programacion_hora_canaria(settings):
    db = Database(settings.db_path)
    assert not should_run_scheduled(settings, db, datetime(2026, 1, 15, 7, 30, tzinfo=TZ))[0]   # invierno, 07:30 UTC
    assert should_run_scheduled(settings, db, datetime(2026, 1, 15, 8, 30, tzinfo=TZ))[0]
    assert should_run_scheduled(settings, db, datetime(2026, 7, 15, 8, 30, tzinfo=TZ))[0]       # verano
    db.close()
    run(settings, notify=False, sources=[FakeOK], now=datetime(2026, 7, 15, 8, 30, tzinfo=TZ))
    db = Database(settings.db_path)
    assert not should_run_scheduled(settings, db, datetime(2026, 7, 15, 9, 30, tzinfo=TZ))[0]   # ya enviado hoy


def test_notificaciones(settings, monkeypatch):
    sent = []

    class FakeChan:
        name = "fake"
        configured = True

        def send_report(self, subject, html, text, path):
            sent.append(("report", subject))

        def send_alert(self, text):
            sent.append(("alert", text))

    class BrokenChan(FakeChan):
        name = "broken"

        def send_report(self, *a):
            raise RuntimeError("SMTP caído")

    monkeypatch.setattr(notifications, "notifiers", lambda s: [BrokenChan(), FakeChan()])
    res = run(settings, notify=True, sources=[FakeOK], now=datetime(2026, 11, 18, 8, 30, tzinfo=TZ))
    assert ("report" in [k for k, _ in sent])            # el canal bueno envía aunque otro falle
    assert any("broken" in e for e in res.errors)
    # al fallar un canal, las ofertas siguen pendientes para reenviarse mañana
    db = Database(settings.db_path)
    assert db.to_report(0)


def test_sin_canales_configurados_no_rompe(settings):
    assert notifications.notifiers(settings) == []
    assert notifications.send_report(settings, "x", "<p>x</p>", "x", "x") == []


def test_panel_de_control(settings):
    from job_agent.dashboard.app import create_app
    run(settings, notify=False, sources=[FakeOK], now=datetime(2026, 11, 18, 8, 30, tzinfo=TZ))
    c = create_app(settings).test_client()
    assert c.get("/").status_code == 200
    assert c.post("/flag/1", data={"f": "favorite"}).status_code == 302
    assert b'class="fav"' in c.get("/?fav=1").data
