from job_agent.filters.geo import detect_municipality


def test_municipio_directo():
    assert detect_municipality("Telde, Las Palmas") == ("Telde", "ok")
    assert detect_municipality("Vecindario") == ("Santa Lucía de Tirajana", "ok")


def test_otra_isla_en_titulo_gana_a_la_ubicacion():
    assert detect_municipality("Las Palmas de Gran Canaria", "Front Office Agent - Sol Fuerteventura")[1] == "otra_isla"


def test_codigo_postal():
    assert detect_municipality("", "", "35220") == ("Telde", "ok")
    assert detect_municipality("", "", "35500")[1] == "otra_isla"   # Lanzarote
    assert detect_municipality("", "", "38639")[1] == "otra_isla"   # Tenerife


def test_peninsula_fuera():
    assert detect_municipality("Madrid")[1] == "fuera"


def test_generico_y_establecimiento_conocido():
    assert detect_municipality("Gran Canaria")[1] == "generico"
    assert detect_municipality("Las Palmas de Gran Canaria", "Recepcionista - Paradisus Gran Canaria")[0] == \
        "San Bartolomé de Tirajana"


def test_la_palma_no_confunde_las_palmas():
    assert detect_municipality("Las Palmas de Gran Canaria")[1] == "ok"
    assert detect_municipality("Santa Cruz de La Palma")[1] == "otra_isla"
