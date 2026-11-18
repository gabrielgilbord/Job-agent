from job_agent.scoring.scorer import score_offer, enrich_location
from job_agent.scoring.salary import parse_salary


def scored(settings, o):
    enrich_location(o, settings)
    return score_offer(o, settings)


def test_descarta_puestos_fuera_de_perfil(settings, offer):
    for t in ("Camarero/a de pisos", "Desarrollador Python", "Ayudante de cocina", "Conductor/a"):
        assert scored(settings, offer(title=t)).score == 0


def test_rango_y_desglose(settings, offer):
    o = scored(settings, offer())
    assert 0 <= o.score <= 100
    b = o.score_breakdown
    assert b["estudios"] <= 25 and b["experiencia"] <= 20 and b["ubicacion"] <= 20
    assert b["condiciones"] <= 20 and b["crecimiento"] <= 10 and b["intereses"] <= 5
    assert o.verdict.startswith("Esta oferta merece la pena porque")


def test_coherencia_cercania(settings, offer):
    cerca = scored(settings, offer(location_text="Santa Brígida", url="u1"))
    lejos = scored(settings, offer(location_text="Mogán", url="u2"))
    assert cerca.score > lejos.score


def test_coherencia_condiciones(settings, offer):
    buena = scored(settings, offer(description="Contrato indefinido, jornada completa. Atención al cliente."))
    mala = scored(settings, offer(description="Contrato temporal campaña de Navidad, media jornada. Atención al cliente."))
    assert buena.score > mala.score


def test_titulo_atractivo_no_basta(settings, offer):
    o = scored(settings, offer(title="Asesora comercial", company="", description="Gana dinero. Solo a comisión. Multinivel."))
    assert o.score < 60


def test_idioma_valorable_no_penaliza_como_imprescindible(settings, offer):
    req = scored(settings, offer(description="Imprescindible alemán alto. Contrato indefinido."))
    val = scored(settings, offer(description="Valorable alemán. Contrato indefinido."))
    assert val.score > req.score


def test_no_inventa_salario(settings, offer):
    o = scored(settings, offer())
    assert o.salary_min is None and o.salary_text == ""


def test_parse_salary():
    assert parse_salary("24000-26000$ Anual/Bruto")[:2] == (24000, 26000)
    lo, hi, note = parse_salary("1.300 € brutos/mes")
    assert lo == 18200 and "14" in note
    assert parse_salary("A convenir") == (None, None, "")


def test_practicas_no_remuneradas_descartadas(settings, offer):
    assert scored(settings, offer(title="Prácticas recepción", description="Prácticas no remuneradas")).score == 0
