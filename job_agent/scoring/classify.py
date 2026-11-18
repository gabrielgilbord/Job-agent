"""Clasificación de ofertas en categorías A-E y descarte de puestos que no encajan."""
from __future__ import annotations

from ..textutil import norm, has_any

# Términos fuertes en el TÍTULO por categoría (orden = prioridad de asignación)
TITLE_TERMS = {
    "D": ["visual merchandiser", "visual merchandising", "visual", "escaparatista", "escaparatismo", "decoracion", "decorador",
          "decoradora", "interiorismo", "interiorista", "mobiliario", "muebles", "iluminacion", "home staging", "showroom",
          "diseno de interiores", "tienda de decoracion"],
    "C": ["comercio internacional", "comercio exterior", "exportacion", "importacion", "export", "import", "aduanas",
          "transitario", "freight", "administrativo comercial", "administrativa comercial", "administrativo a comercial",
          "administracion de ventas", "gestion de pedidos", "back office", "backoffice", "logistica", "supply chain",
          "atencion al cliente internacional", "customer service internacional", "sales support", "order management",
          "ejecutivo de cuentas", "key account assistant", "trade marketing"],
    "B": ["recepcionista", "recepcion hotel", "front office", "front desk", "receptionist", "guest relations", "guest service",
          "guest experience", "concierge", "conserje de hotel", "night auditor", "auditor de noche", "agente de reservas",
          "reservas", "reservations", "agente de viajes", "asesor de viajes", "asesora de viajes", "travel agent",
          "travel consultant", "informacion turistica", "informador turistico", "informadora turistica", "atencion al visitante",
          "jefe de recepcion", "jefa de recepcion", "revenue", "guia turistico", "guia de excursiones", "excursion guide",
          "coordinador de servicios turisticos", "turismo", "touroperador", "touroperacion", "transfer", "rent a car",
          "alquiler de vehiculos", "sales advisor club", "customer experience"],
    "A": ["dependiente", "dependienta", "dependiente a", "vendedor", "vendedora", "asesor comercial", "asesora comercial",
          "asesor de ventas", "asesora de ventas", "sales advisor", "sales associate", "sales assistant", "retail assistant",
          "retail", "encargado", "encargada", "segundo encargado", "segunda encargada", "store manager", "responsable de tienda",
          "jefe de tienda", "jefa de tienda", "subdirector de tienda", "director de tienda", "team manager", "team leader tienda",
          "atencion al cliente", "customer service", "comercial de tienda", "personal de tienda", "cajero", "cajera",
          "reponedor", "promotor", "promotora", "beauty advisor", "asesor de belleza", "optica", "teleoperador", "teleoperadora"],
    "E": ["administrativo", "administrativa", "auxiliar administrativo", "auxiliar administrativa", "administrativo a",
          "recepcion", "asistente de oficina", "office assistant", "office manager", "secretaria", "secretario",
          "gestor de clientes", "gestora de clientes", "coordinador de atencion al cliente", "coordinadora de atencion al cliente",
          "organizacion de eventos", "eventos", "event", "asistente de operaciones", "operations assistant", "azafata", "azafato",
          "informacion", "auxiliar de eventos", "coordinadora", "coordinador", "assistant", "asistente"],
}

# Puestos que NO encajan (título). Se ignoran si el título contiene un término fuerte de la candidata listado en KEEP_OVERRIDES.
EXCLUDE_TITLE = [
    "camarero", "camarera", "cocinero", "cocinera", "cocineros", "cocina", "fregador", "fregadora", "subgobernante", "jefe de sala", "jefa de sala", "camerero", "chef", "jefe de partida", "jefa de partida", "ayudante de cocina",
    "pastelero", "panadero", "pizzero", "friegaplatos", "steward", "limpieza", "limpiador", "limpiadora", "camarera de pisos",
    "camarero de pisos", "gobernanta", "gobernante", "valet", "lavanderia", "socorrista", "mantenimiento", "electricista",
    "fontanero", "frigorista", "mecanico", "conductor", "conductora", "chofer", "repartidor", "repartidora", "rider",
    "mozo", "carretillero", "peon", "operario", "operaria", "albanil", "jardinero", "programador", "desarrollador",
    "developer", "ingeniero", "ingeniera", "software", "devops", "sysadmin", "data scientist", "data engineer", "enfermero",
    "enfermera", "medico", "medica", "fisioterapeuta", "auxiliar de enfermeria", "tcae", "farmaceutico", "farmaceutica",
    "masajista", "terapeuta", "spa therapist", "beauty therapist", "esteticista", "peluquero", "peluquera", "monitor",
    "monitora", "animador", "animadora", "animacion", "profesor", "profesora", "cuidador", "cuidadora", "vigilante",
    "seguridad", "contable", "fiscal", "nominas", "payroll", "abogado", "abogada", "jefe de sector", "jefa de sector",
    "maitre", "sumiller", "bartender", "barman", "bar manager", "restaurant manager", "f b", "food beverage", "sous chef",
    "director de hotel", "director general", "arquitecto", "arquitecta", "delineante", "disenador grafico",
    "disenadora grafica", "comercial autonomo", "agente inmobiliario", "asesor inmobiliario", "asesor financiero",
    "agente de seguros", "puerta fria", "captador", "captadora", "fundraiser", "rrhh", "recursos humanos", "human resources",
    "it support", "soporte tecnico", "tecnico de sistemas", "electromecanico", "soldador", "cristalero", "carpintero",
]
KEEP_OVERRIDES = ["night auditor", "recepcionista", "visual merchandiser"]

OPERATIVE_HOSPITALITY = {"camarero", "camarera", "cocinero", "cocinera", "cocineros", "cocina", "fregador", "fregadora", "subgobernante", "jefe de sala", "jefa de sala", "camerero", "chef", "ayudante de cocina", "limpieza",
                         "camarera de pisos", "camarero de pisos", "gobernanta", "friegaplatos", "steward", "limpiador",
                         "limpiadora", "jefe de partida", "jefa de partida", "bartender", "barman"}


def classify(title: str, description: str = "", accept_hospitality: bool = False) -> tuple[str, str]:
    """Devuelve (categoria, motivo_descarte). Categoria '' si se descarta."""
    t = norm(title)
    keep = has_any(t, KEEP_OVERRIDES)
    excl = has_any(t, EXCLUDE_TITLE)
    if accept_hospitality:
        excl = [e for e in excl if e not in OPERATIVE_HOSPITALITY]
    if excl and not keep:
        return "", f"puesto fuera de perfil ({excl[0]})"
    for cat in ("D", "C", "B", "A", "E"):
        if has_any(t, TITLE_TERMS[cat]):
            return cat, ""
    if has_any(t, ["comercial", "sales executive", "sales manager", "key account", "ejecutivo comercial",
                   "ejecutiva comercial", "account manager", "business development"]):
        return "C", ""
    # Sin pistas en el título: mirar el comienzo de la descripción con más exigencia
    d = norm(description)[:600]
    for cat in ("D", "C", "B", "A"):
        hits = has_any(d, TITLE_TERMS[cat])
        if len(hits) >= 2:
            return cat, ""
    return "", "sin relación clara con el perfil"
