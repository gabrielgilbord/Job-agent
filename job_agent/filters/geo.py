"""Geografía de Gran Canaria: detección de municipio, tiempo de viaje desde San Mateo y descarte de otras islas.

Los tiempos son estimaciones de conducción por carretera (OSRM, red viaria real, sin tráfico)
calculadas desde el casco de Vega de San Mateo. En hora punta hacia Las Palmas/Telde suma ~10 min.
"""
from __future__ import annotations

import re

from ..textutil import norm

# minutos de coche desde Vega de San Mateo (OSRM, nov-2026)
TRAVEL_MIN = {
    "Vega de San Mateo": 0, "Santa Brígida": 14, "Valsequillo de Gran Canaria": 20, "Teror": 24,
    "Valleseco": 24, "Telde": 33, "Las Palmas de Gran Canaria": 35, "Tejeda": 34, "Arucas": 38,
    "Artenara": 40, "Firgas": 42, "Ingenio": 45, "Santa Lucía de Tirajana": 45, "Moya": 47,
    "Agüimes": 51, "Santa María de Guía": 53, "Gáldar": 54, "San Bartolomé de Tirajana": 58,
    "Agaete": 62, "Mogán": 82, "La Aldea de San Nicolás": 97,
}

# alias/localidades/barrios -> municipio (normalizados al comparar)
ALIASES = {
    "Las Palmas de Gran Canaria": ["las palmas de gran canaria", "las palmas de g c", "las palmas gc", "lpgc", "tamaraceite",
                                    "siete palmas", "guanarteme", "las canteras", "triana", "vegueta", "mesa y lopez",
                                    "el sebadal", "la isleta", "escaleritas", "tafira", "schamann", "puerto de la luz",
                                    "alcaravaneras", "ciudad jardin", "las arenas", "los alisios", "la minilla",
                                    "almatriche", "marzagan", "7 palmas"],
    "Vega de San Mateo": ["vega de san mateo", "san mateo"],
    "Santa Brígida": ["santa brigida", "la atalaya", "monte lentiscal"],
    "Telde": ["telde", "jinamar", "la garita", "melenara", "salinetas", "el mirador", "lomo blanco",
              "ojos de garza", "gando", "aeropuerto de gran canaria", "la majadilla", "hoya pozuelo"],
    "Valsequillo de Gran Canaria": ["valsequillo"],
    "Teror": ["teror"],
    "Arucas": ["arucas", "banaderos", "cardones", "bañaderos"],
    "Firgas": ["firgas"],
    "Santa María de Guía": ["santa maria de guia", "guia de gran canaria"],
    "Gáldar": ["galdar", "sardina del norte"],
    "Ingenio": ["ingenio", "carrizal", "el carrizal"],
    "Agüimes": ["aguimes", "arinaga", "cruce de arinaga", "playa de arinaga"],
    "Moya": ["moya"],
    "Valleseco": ["valleseco"],
    "Tejeda": ["tejeda"],
    "Artenara": ["artenara"],
    "Agaete": ["agaete", "puerto de las nieves"],
    "La Aldea de San Nicolás": ["la aldea", "san nicolas de tolentino", "aldea de san nicolas"],
    "Mogán": ["mogan", "puerto rico", "arguineguin", "amadores", "taurito", "playa del cura", "tauro", "patalavaca"],
    "San Bartolomé de Tirajana": ["san bartolome de tirajana", "maspalomas", "playa del ingles", "san agustin", "meloneras",
                                   "bahia feliz", "el tablero", "san fernando de maspalomas", "sonnenland", "pasito blanco",
                                   "costa canaria", "campo internacional"],
    "Santa Lucía de Tirajana": ["santa lucia de tirajana", "vecindario", "doctoral", "sardina del sur", "pozo izquierdo",
                                 "cruce de sardina", "atlantico vecindario"],
}

# Establecimientos conocidos cuyo anuncio suele llevar una localidad genérica o la de la sede
KNOWN_PLACES = {
    "paradisus gran canaria": "San Bartolomé de Tirajana", "barcelo margaritas": "San Bartolomé de Tirajana",
    "livvo koala": "San Bartolomé de Tirajana", "livvo fataga": "Las Palmas de Gran Canaria",
    "livvo puerto de mogan": "Mogán", "occidental roca negra": "Agaete", "roca negra": "Agaete",
    "santa catalina": "Las Palmas de Gran Canaria", "occidental las canteras": "Las Palmas de Gran Canaria",
    "occidental las palmas": "Las Palmas de Gran Canaria", "ac hotel gran canaria": "Las Palmas de Gran Canaria",
    "kiabi alisios": "Las Palmas de Gran Canaria", "los alisios": "Las Palmas de Gran Canaria",
    "el mirador": "Telde", "las terrazas": "Telde", "la ballena": "Las Palmas de Gran Canaria",
    "las arenas": "Las Palmas de Gran Canaria", "siete palmas": "Las Palmas de Gran Canaria",
    "atlantico vecindario": "Santa Lucía de Tirajana", "el muelle": "Las Palmas de Gran Canaria",
    "seaside palm beach": "San Bartolomé de Tirajana", "lopesan costa meloneras": "San Bartolomé de Tirajana",
    "lopesan villa del conde": "San Bartolomé de Tirajana", "lopesan baobab": "San Bartolomé de Tirajana",
    "riu palace maspalomas": "San Bartolomé de Tirajana", "radisson blu mogan": "Mogán", "anfi del mar": "Mogán",
}

GENERIC_GC = ["gran canaria", "las palmas", "provincia de las palmas"]

OTHER_ISLANDS = [
    "tenerife", "lanzarote", "fuerteventura", "la palma", "la gomera", "gomera", "el hierro",
    "santa cruz de tenerife", "adeje", "costa adeje", "arona", "los cristianos", "playa de las americas", "fanabe",
    "puerto de la cruz", "la laguna", "la orotava", "las chafiras", "san miguel de abona", "granadilla", "guia de isora",
    "icod", "los realejos", "candelaria", "el medano", "arrecife", "puerto del carmen", "playa blanca", "costa teguise",
    "puerto calero", "yaiza", "tias", "teguise", "corralejo", "morro jable", "jandia", "caleta de fuste",
    "puerto del rosario", "costa calma", "la oliva", "los llanos de aridane", "santa cruz de la palma", "salinas lanzarote",
    "paradisus salinas", "playa de la arena", "callao salvaje",
]

# código postal (3 primeras cifras) -> municipio (aprox.). 355xx/356xx = Lanzarote/Fuerteventura; 38xxx = prov. Tenerife
CP_PREFIX = {
    "350": "Las Palmas de Gran Canaria", "3510": "San Bartolomé de Tirajana", "3511": "Santa Lucía de Tirajana",
    "3512": "Mogán", "3513": "Mogán", "3514": "Mogán", "3520": "Telde", "3521": "Telde", "3522": "Telde",
    "3523": "Telde", "3524": "Ingenio", "3525": "Ingenio", "3526": "Agüimes", "3527": "Santa Lucía de Tirajana",
    "3528": "San Bartolomé de Tirajana", "3529": "San Bartolomé de Tirajana", "3530": "Santa Brígida",
    "3531": "Santa Brígida", "3532": "Vega de San Mateo", "3533": "Teror", "3534": "Valleseco", "3535": "Artenara",
    "3536": "Tejeda", "3540": "Arucas", "3541": "Arucas", "3542": "Moya", "3543": "Firgas", "3545": "Santa María de Guía",
    "3546": "Gáldar", "3547": "La Aldea de San Nicolás", "3548": "Agaete", "3501": "Las Palmas de Gran Canaria",
    "35118": "Agüimes", "35119": "Agüimes",
}

REMOTE_TERMS = ["teletrabajo 100", "100 remoto", "100 teletrabajo", "full remote", "totalmente remoto", "remoto desde espana",
                "trabajo en remoto", "teletrabajo total"]


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


def detect_municipality(location_text: str, title: str = "", postal_code: str = "") -> tuple[str, str]:
    """Devuelve (municipio | "", estado) con estado en: ok, generico, otra_isla, fuera, desconocido."""
    loc = norm(location_text)
    tit = norm(title)
    both = f"{loc} {tit}"

    # 1. otra isla mencionada en el título o la ubicación => fuera (salvo que la ubicación sea claramente GC y el título no)
    other_in_title = any(_contains(tit, k) for k in OTHER_ISLANDS)
    other_in_loc = any(_contains(loc, k) for k in OTHER_ISLANDS)
    if other_in_title:
        return "", "otra_isla"

    # 2a. establecimiento conocido mencionado en el título
    for place, mun in KNOWN_PLACES.items():
        if _contains(tit, place):
            return mun, "ok"

    # 2b. municipio/localidad concreta (la más específica gana: probar alias largos primero)
    pairs = sorted(((a, m) for m, al in ALIASES.items() for a in al), key=lambda x: -len(x[0]))
    for alias, mun in pairs:
        if _contains(loc, norm(alias)):
            # "las palmas de gran canaria" ya está como alias; "san mateo" puede ser otro municipio peninsular => solo si GC/CN
            if alias == "san mateo" and not any(_contains(loc, g) for g in ("gran canaria", "las palmas", "canarias", "cn")):
                continue
            return mun, "ok"
    if other_in_loc:
        return "", "otra_isla"
    for alias, mun in pairs:
        if len(alias) > 5 and _contains(tit, norm(alias)) and alias not in ("san mateo",):
            return mun, "ok"

    # 3. código postal
    cp = re.sub(r"\D", "", postal_code or "")
    if len(cp) == 5:
        if cp.startswith("38") or cp[:3] in ("355", "356"):
            return "", "otra_isla"
        if cp.startswith("35"):
            for n in (5, 4, 3):
                if cp[:n] in CP_PREFIX:
                    return CP_PREFIX[cp[:n]], "ok"
            return "", "generico"

    # 4. genérico Gran Canaria / Las Palmas
    if any(_contains(both, g) for g in GENERIC_GC) or _contains(loc, "canarias"):
        return "", "generico"
    if not loc:
        return "", "desconocido"
    return "", "fuera"


def is_remote(text: str) -> bool:
    t = norm(text)
    return any(k in t for k in REMOTE_TERMS)


def tier_of(municipality: str, geografia: dict) -> str:
    for tier in ("alta", "media", "baja"):
        if municipality in (geografia.get(tier) or []):
            return tier
    return "baja" if municipality else ""


def travel_minutes(municipality: str) -> int | None:
    return TRAVEL_MIN.get(municipality)


def municipality_from_text(text: str) -> str:
    """Busca un municipio de GC en un texto libre (descripción). Solo alias inequívocos (> 5 letras)."""
    t = norm(text)
    if not t or any(_contains(t, k) for k in ("tenerife", "lanzarote", "fuerteventura")):
        return ""
    for place, mun in KNOWN_PLACES.items():
        if _contains(t, place):
            return mun
    pairs = sorted(((a, m) for m, al in ALIASES.items() for a in al if len(a) > 5 and a not in
                    ("san mateo", "el mirador", "las arenas", "la aldea", "carrizal", "triana", "tafira", "doctoral")),
                   key=lambda x: -len(x[0]))
    for alias, mun in pairs:
        if _contains(t, norm(alias)):
            return mun
    return ""
