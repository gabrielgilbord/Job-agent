"""Puntuación razonada 0-100 de cada oferta.

Reparto (según especificación):
  estudios 25 · experiencia 20 · ubicación 20 · condiciones 20 · crecimiento 10 · intereses 5
Después se aplican penalizaciones explícitas (requisitos que no cumple, anuncios sospechosos...).
Toda la lógica es determinista y sin coste (no usa modelos de pago).
"""
from __future__ import annotations

import re

from ..filters import geo
from ..models import Offer
from ..textutil import norm, has_any
from .classify import classify
from .salary import parse_salary

LANGS = {"ingles": "inglés", "english": "inglés", "aleman": "alemán", "german": "alemán", "frances": "francés",
         "french": "francés", "italiano": "italiano", "sueco": "sueco", "swedish": "sueco", "noruego": "noruego",
         "norwegian": "noruego", "danes": "danés", "danish": "danés", "neerlandes": "neerlandés", "holandes": "neerlandés",
         "dutch": "neerlandés", "ruso": "ruso", "finlandes": "finlandés", "finnish": "finlandés", "portugues": "portugués",
         "chino": "chino", "polaco": "polaco"}
UNMET_DEGREES = ["arquitectura", "ingenieria", "derecho", "psicologia", "enfermeria", "medicina", "grado en diseno",
                 "titulacion en diseno", "bellas artes", "farmacia", "magisterio", "grado en informatica", "periodismo",
                 "titulacion en interiorismo", "ciclo de diseno de interiores"]
HER_DEGREES = ["turismo", "comercio internacional", "comercio exterior", "gestion de alojamientos", "agencias de viajes",
               "transporte y logistica", "gestion comercial", "marketing", "ciclo formativo", "grado medio", "grado superior",
               "fp", "titulacion universitaria", "grado universitario", "licenciatura", "diplomatura"]
GROWTH_WORDS = ["plan de carrera", "promocion interna", "desarrollo profesional", "crecimiento", "formacion continua",
                "carrera profesional", "posibilidad de promocion", "proyeccion", "plan de formacion", "career"]
BENEFIT_WORDS = ["seguro medico", "descuento", "descuentos", "retribucion flexible", "tickets restaurante", "estabilidad",
                 "buen ambiente", "conciliacion", "horario fijo", "incentivos", "bonus", "comida incluida", "plan de pensiones",
                 "dias libres", "turnos rotativos fijos", "salario competitivo"]
SUSPICIOUS = ["multinivel", "ingresos ilimitados", "se tu propio jefe", "solo a comision", "unicamente a comision",
              "100 a comision", "inversion inicial", "trabaja desde casa y gana", "venta piramidal", "freelance a comision",
              "sin sueldo fijo", "remuneracion a comision"]
SHORT_CONTRACT_TITLE = ["campana de navidad", "campana navidad", "navidad", "campana de verano", "campana", "rebajas",
                        "fin de semana", "fines de semana", "por horas", "extra", "eventual", "verano", "refuerzo", "cubrir baja",
                        "sustitucion", "baja"]
SHORT_CONTRACT_DESC = ["cubrir baja", "cubrir una baja", "baja por maternidad", "baja maternal", "sustitucion de vacaciones",
                       "campana de navidad", "campana navidad", "campana de verano", "contrato de 1 mes", "contrato de un mes",
                       "contrato de 2 meses", "contrato de dos meses", "duracion 1 mes", "duracion de 1 mes",
                       "duracion 2 meses", "duracion de 2 meses", "contrato de 15 dias", "contrato por dias"]
VALUED = ["valorable", "se valora", "se valorara", "deseable", "plus", "nice to have", "preferible", "valoraremos",
          "se tendra en cuenta", "sera un plus"]
OUTSIDE_TITLE = ["austria", "alemania", "germany", "suiza", "switzerland", "francia", "reino unido", "uk", "malta",
                 "mallorca", "ibiza", "menorca", "baleares", "madrid", "barcelona", "valencia", "malaga", "sevilla",
                 "benidorm", "andorra", "portugal", "italia", "grecia", "crucero", "cruise"]
SOFTWARE = ["opera", "opera pms", "marsha", "protel", "sap", "autocad", "sketchup", "revit", "photoshop", "illustrator",
            "amadeus", "galileo", "sabre", "navision", "a3"]
LEADER_TITLES = ["encargado", "encargada", "responsable", "store manager", "jefe", "jefa", "coordinador", "coordinadora",
                 "supervisor", "supervisora", "subdirector", "manager", "gestor", "gestora", "team leader", "segunda encargada",
                 "segundo encargado"]


def _languages(text: str) -> tuple[list, list]:
    """Idiomas exigidos vs. solo valorados, analizando cada frase por separado."""
    required, valued = set(), set()
    for seg in re.split(r"[\n.;•·]|\s-\s", text):
        sn = norm(seg).replace("playa del ingles", "")
        langs = {LANGS[k] for k in LANGS if re.search(rf"(?<![a-z]){k}(?![a-z])", sn)}
        if not langs:
            continue
        (valued if has_any(sn, VALUED) else required).update(langs)
    return sorted(required), sorted(valued - required)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _detect_contract(text: str) -> str:
    t = norm(text)
    if "fijo discontinuo" in t:
        return "fijo-discontinuo"
    if "indefinido" in t or "permanent" in t or "estable" in t and "contrato" in t:
        return "indefinido"
    if "interinidad" in t or "sustitucion" in t:
        return "sustitución/interinidad"
    if "obra y servicio" in t:
        return "obra y servicio"
    if "practicas" in t or "becario" in t or "internship" in t:
        return "prácticas"
    if "temporal" in t or "temporary" in t or "eventual" in t:
        return "temporal"
    return ""


def _detect_workday(text: str) -> str:
    t = norm(text)
    if "jornada completa" in t or "full time" in t or "tiempo completo" in t or "40h" in t or "40 h" in t or "40 horas" in t:
        return "completa"
    m = re.search(r"\b(\d{1,2})\s?h(oras)?(\s|\b)(semanales|semana|a la semana|sem)?", t)
    if "media jornada" in t or "jornada parcial" in t or "part time" in t or "tiempo parcial" in t:
        return "parcial"
    if m and 8 <= int(m.group(1)) < 38 and ("semana" in t[m.start():m.end() + 12]):
        return f"parcial ({m.group(1)} h/sem)"
    if "fin de semana" in t or "fines de semana" in t:
        return "parcial (fines de semana)"
    return ""


def _exp_years(text: str) -> int | None:
    t = norm(text)
    pats = [r"(\d+)\s*(?:o mas\s*)?anos? de experiencia", r"experiencia (?:minima |previa |demostrable )?(?:de )?(\d+)\s*anos?",
            r"al menos (\d+)\s*anos?", r"minimo (\d+)\s*anos?", r"(\d+)\s*years? (?:of )?experience"]
    vals = [int(x) for p in pats for x in re.findall(p, t) if x.isdigit() and int(x) < 20]
    return max(vals) if vals else None


def score_offer(o: Offer, settings) -> Offer:
    cand = settings.candidata
    pref = settings.preferencias
    busq = settings.busqueda
    full_text = " ".join([o.title, o.description, o.requirements, o.education, o.experience, o.contract, o.workday,
                          o.salary_text])
    tn = norm(o.title)
    ft = norm(full_text)
    req_text = norm(" ".join([o.requirements, o.education, o.experience, o.description]))

    # ---------------------------------------------------- categoría / descarte
    cat, why = classify(o.title, o.description, pref.get("aceptar_hosteleria_operativa", False))
    if has_any(tn, OUTSIDE_TITLE):
        cat, why = "", "puesto fuera de Gran Canaria (según el título)"
    o.category = cat
    if not cat:
        o.score, o.verdict = 0, why
        return o

    # ---------------------------------------------------- completar datos si faltan (sin inventar)
    if not o.contract:
        o.contract = _detect_contract(" ".join([o.title, o.description[:1500]]))
    if not o.workday:
        o.workday = _detect_workday(" ".join([o.title, o.description[:1500]]))
    if o.salary_min is None and o.salary_text:
        o.salary_min, o.salary_max, note = parse_salary(o.salary_text)
        if note:
            o.warnings.append(f"Salario anual {note}")

    reasons, warns = [], o.warnings
    pen = 0

    # ---------------------------------------------------- 1. Estudios (25)
    st = {"C": 22, "B": 21, "A": 12, "D": 14, "E": 16}[cat]
    if cat == "C" and has_any(ft, ["comercio internacional", "comercio exterior", "exportacion", "importacion", "aduanas"]):
        st = 25
        reasons.append("Encaja directamente con su ciclo de Comercio Internacional")
    elif cat == "B":
        if has_any(ft, ["grado en turismo", "titulacion en turismo", "estudios de turismo", "diplomatura en turismo",
                        "formacion en turismo", "grado turismo"]):
            st = 25
            reasons.append("Piden formación en Turismo: su Grado es justo lo que buscan")
        else:
            reasons.append("Puesto turístico donde su Grado en Turismo es un plus claro")
    elif cat == "A":
        if has_any(tn, LEADER_TITLES):
            st = 17
            reasons.append("Puesto de responsabilidad en comercio, acorde a su formación superior")
    elif cat == "E" and has_any(tn, ["eventos", "event", "organizacion de eventos"]):
        st = 19
    reqish = norm(" ".join([o.requirements, o.education] + [seg for seg in re.split(r"[\n.;]", o.description)
                                                          if re.search(r"titulaci|grado|licenciad|formaci|estudios|requisit",
                                                                       seg, re.I)]))
    unmet_deg = has_any(reqish, UNMET_DEGREES)
    if unmet_deg and not has_any(reqish, VALUED):
        st -= 10
        pen += 5
        warns.append(f"Piden titulación que no tiene ({unmet_deg[0]})")
    elif has_any(req_text, HER_DEGREES) and st < 25:
        st = min(25, st + 2)
    st = _clamp(st, 0, 25)

    # ---------------------------------------------------- 2. Experiencia (20)
    ex = {"A": 19, "B": 14, "C": 11, "D": 13, "E": 12}[cat]
    if has_any(ft, ["atencion al cliente", "trato con el publico", "orientacion al cliente", "venta", "ventas",
                    "customer service", "trato al cliente", "experiencia comercial", "retail", "tienda"]):
        ex += 3
        if cat != "A":
            reasons.append("Valoran atención al cliente y ventas, que ya domina")
    elif cat == "A":
        reasons.append("Experiencia directa: ya trabaja de cara al público en tienda")
    if has_any(ft, ["sin experiencia", "no se requiere experiencia", "no es necesaria experiencia", "no necesaria experiencia"]):
        ex += 3
    yrs = _exp_years(" ".join([o.experience, o.requirements, o.description]))
    if yrs is not None:
        if cat == "A" and not has_any(tn, LEADER_TITLES):
            pass  # ya tiene experiencia en tienda
        elif has_any(tn, LEADER_TITLES) and has_any(ft, ["coordinando equipos", "gestion de equipos", "liderando equipos",
                                                         "liderazgo de equipos", "a cargo de equipos", "equipo a cargo"]):
            ex -= 8
            warns.append(f"Piden {yrs} años coordinando equipos (ella aún no ha sido encargada)")
        elif yrs >= 4:
            ex -= 9
            warns.append(f"Piden {yrs} años de experiencia en el puesto")
        elif yrs >= 2:
            ex -= 5
            warns.append(f"Piden {yrs} años de experiencia (comprobar si cuenta la suya)")
    ex = _clamp(ex, 0, 20)

    # ---------------------------------------------------- 3. Ubicación (20)
    if o.remote and not o.municipality:
        loc = 17
        reasons.append("Teletrabajo: sin desplazamientos")
    elif o.municipality:
        m = o.travel_min if o.travel_min is not None else 60
        loc = 20 if m <= 20 else 18 if m <= 30 else 15 if m <= 40 else 11 if m <= 50 else 7 if m <= 60 else 3
        if o.geo_tier == "alta":
            loc = max(loc, 15)
        ideal = busq.get("tiempo_desplazamiento_ideal_min", 30)
        if m <= ideal:
            reasons.append(f"Muy cerca: ~{m} min en coche desde San Mateo")
        elif m > busq.get("tiempo_desplazamiento_max_min", 60):
            warns.append(f"Desplazamiento largo (~{m} min)")
    else:
        loc = 10
        warns.append("Localidad exacta no indicada (Gran Canaria)")
    loc = _clamp(loc, 0, 20)

    # ---------------------------------------------------- 4. Condiciones (20)
    co = 8
    c = norm(o.contract)
    if "indefinido" in c:
        co += 6
        reasons.append("Contrato indefinido")
    elif "fijo discontinuo" in c:
        co += 2
    elif "practicas" in c:
        co -= 3
    elif "autonomo" in c:
        co -= 8
        warns.append("Contrato como autónomo (sin nómina fija)")
    elif c:
        co -= 2
    if (has_any(norm(o.title + " " + o.contract + " " + o.workday), SHORT_CONTRACT_TITLE)
            or has_any(norm(o.description), SHORT_CONTRACT_DESC) or "interinidad" in c or "sustitucion" in c):
        co -= 3
        warns.append("Contrato corto / campaña o sustitución")
    w = norm(o.workday)
    want = pref.get("jornada", "completa")
    if w.startswith("completa"):
        co += 4 if want != "parcial" else 0
        if want == "completa":
            reasons.append("Jornada completa")
    elif w.startswith("parcial"):
        if want == "completa":
            co -= 5
            warns.append(f"Jornada {o.workday}")
    sal_min = pref.get("salario_minimo_anual_bruto")
    if o.salary_min:
        co += 1  # transparencia
        ref = o.salary_max or o.salary_min
        if sal_min:
            if ref >= sal_min:
                co += 4
                reasons.append("Salario por encima de su mínimo deseado")
            else:
                co -= 6
                warns.append("Salario por debajo de su mínimo deseado")
        else:
            if ref >= 22000:
                co += 4
                reasons.append("Salario competitivo publicado")
            elif ref >= 19000:
                co += 2
            elif ref < 16500:
                co -= 3
                warns.append("Salario bajo (probablemente parcial)")
    co += min(3, len(has_any(ft, BENEFIT_WORDS)))
    co = _clamp(co, 0, 20)

    # ---------------------------------------------------- 5. Crecimiento (10)
    gr = 3
    if has_any(tn, LEADER_TITLES):
        gr = 8
        reasons.append("Puesto con responsabilidad y proyección")
    elif cat in ("C", "B"):
        gr = 6
    elif cat in ("D", "E"):
        gr = 5
    if has_any(ft, GROWTH_WORDS):
        gr += 2
    gr = _clamp(gr, 0, 10)

    # ---------------------------------------------------- 6. Intereses (5)
    it = {"D": 5, "C": 4, "B": 4, "A": 3, "E": 2}[cat]
    if cat == "A" and has_any(ft, ["decoracion", "artesania", "regalo", "mobiliario", "hogar", "interiorismo", "moda",
                                   "joyeria", "diseno"]):
        it = 5
    if cat == "D":
        reasons.append("Conecta con su interés por el diseño y la decoración")

    # ---------------------------------------------------- Penalizaciones
    langs_conf = [norm(x) for x in cand.get("idiomas_confirmados") or []]
    required, valued = _languages(" \n".join([o.title, o.requirements, o.description]))
    lang_pen = 0
    for lang in required:
        if any(norm(lang) in x for x in langs_conf):
            continue
        if lang == "inglés":
            lang_pen += 3
            warns.append("Piden inglés (nivel de la candidata sin confirmar)")
        else:
            lang_pen += 7
            warns.append(f"Piden {lang} (no consta en su perfil)")
    pen += min(lang_pen, 12)
    extra = [l for l in valued if l not in required and not any(norm(l) in x for x in langs_conf)]
    if extra:
        warns.append("Valoran " + ", ".join(extra) + " (no imprescindible)")
    if has_any(ft, ["carnet de conducir", "permiso de conducir", "carne de conducir", "carnet b", "vehiculo propio",
                    "driving licence", "driving license"]):
        lic = cand.get("carnet_conducir")
        if lic is False:
            pen += 10
            warns.append("Requiere carnet/vehículo (no tiene)")
        elif lic is None:
            pen += 1
            warns.append("Piden carnet de conducir o vehículo (a confirmar)")
    for seg in re.split(r"[\n.;]", " \n".join([o.requirements, o.description])):
        sn = norm(seg)
        sw = has_any(sn, SOFTWARE)
        if sw and "imprescindible" in sn:
            pen += 4
            warns.append(f"Exigen manejo de {sw[0]} (formación específica a confirmar)")
            break
    if "seguros" in tn and has_any(tn, ["comercial", "agente", "asesor", "asesora", "mando"]):
        pen += 6
        warns.append("Venta de seguros: suele ir ligada a comisiones")
    if has_any(ft, SUSPICIOUS):
        pen += 20
        warns.append("⚠️ Anuncio sospechoso (solo comisiones / multinivel)")
    if not o.company.strip() and len(o.description) < 200:
        pen += 6
        warns.append("Oferta poco transparente (sin empresa ni detalle)")
    if has_any(tn, ["practicas", "becario", "becaria", "internship", "alumno", "alumna", "stage", "trainee"]):
        if has_any(ft, ["no remunerada", "no remuneradas", "sin remuneracion"]) and not pref.get(
                "aceptar_practicas_no_remuneradas", False):
            o.score, o.verdict, o.category = 0, "prácticas no remuneradas", ""
            return o
        if has_any(ft, ["estudiantes", "students", "studenti", "matriculado", "matriculada", "convenio de practicas",
                        "convenio con universidad", "enrolled"]):
            pen += 20
            warns.append("Prácticas solo para estudiantes matriculados")
        else:
            pen += 10
            warns.append("Son prácticas: suelen exigir estar matriculada")

    total = _clamp(st + ex + loc + co + gr + it - pen, 0, 100)
    o.score = int(round(total))
    o.score_breakdown = {"estudios": st, "experiencia": ex, "ubicacion": loc, "condiciones": co, "crecimiento": gr,
                         "intereses": it, "penalizaciones": -pen}
    # Mantener únicas, en orden
    o.reasons = list(dict.fromkeys(reasons))
    o.warnings = list(dict.fromkeys(warns))
    o.verdict = build_verdict(o)
    return o


def label(score: int) -> str:
    return ("Excelente" if score >= 90 else "Muy interesante" if score >= 80 else "Buena" if score >= 70
            else "Secundaria" if score >= 60 else "Descartada")


def build_verdict(o: Offer) -> str:
    if not o.reasons:
        base = "encaja con su perfil comercial y de atención al cliente"
    else:
        r = [x[0].lower() + x[1:] for x in o.reasons[:3]]
        base = ", ".join(r[:-1]) + (" y " if len(r) > 1 else "") + r[-1]
    txt = f"Esta oferta merece la pena porque {base}."
    if o.warnings:
        txt += f" Ojo: {o.warnings[0][0].lower() + o.warnings[0][1:]}."
    return txt


def enrich_location(o: Offer, settings) -> str:
    """Rellena municipio/tiempo/tier. Devuelve estado geográfico (ok, generico, otra_isla, fuera, desconocido, remoto)."""
    mun, state = geo.detect_municipality(o.location_text, o.title, o.postal_code)
    if state == "ok":
        o.municipality = mun
        o.travel_min = geo.travel_minutes(mun)
        o.geo_tier = geo.tier_of(mun, settings.geografia)
        return state
    if state in ("fuera", "desconocido") and settings.busqueda.get("admitir_remoto", True) and (
            o.remote or geo.is_remote(o.title + " " + o.description)):
        o.remote = True
        return "remoto"
    if state == "generico":
        mun2 = geo.municipality_from_text(o.description[:1500])
        if mun2:
            o.municipality = mun2
            o.travel_min = geo.travel_minutes(mun2)
            o.geo_tier = geo.tier_of(mun2, settings.geografia)
            return "ok"
        o.geo_tier = "media"
    return state
