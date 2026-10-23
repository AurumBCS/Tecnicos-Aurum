"""
Reglas para analizar por que se repitio un mantenimiento (RM) a partir de la
ficha de Oracle del mantenimiento ORIGINAL (ficha_ofs.extraer_ficha) y del
motivo de la vuelta que trae el Excel ("Motivo Post").

Son las reglas que fue ensenando Gustavo revisando RMs a mano (ver
"Correo Recuentos/rm-aprendizaje.md" y el informe de la matricula 302154) y lo
que dicen los cursos de Workday. No sustituyen a una revision humana: marcan
lo que se puede ver en la ficha sin criterio (pilas sin codificar, fallo que
ya estaba en el historico, lo que pedia el texto y no aparece hecho...).

analizar(ficha, motivo_post) -> dict con:
  causas      lista de codigos: cod, reit, texto, pilas, com, cam, ok
  severidad   alta / media / baja
  panel       Fast / Moonshot / ""
  queHizo     observaciones del tecnico (o "Parte sin observaciones.")
  queFalto    lo que falto, en frases cortas
  codificacion  lo codificado -> lo que tocaba
"""

import re
import unicodedata

# Causas oficiales (curso "Codificacion y causas"): la que corresponde a cada aviso
CAUSA_AVISO = [
    (r"bateria baja|pila baja|pilas bajas", "7050", "Pila baja / batería"),
    (r"fallo de supervision", "7051", "Fallo supervisión"),
    (r"tamper", "7053", "Tamper"),
    (r"falsas? alarmas?", "7055", "Falsas alarmas"),
    (r"no (envia|transmite)|gsm|comunicacion|missing test|bloqueo", "7052", "Fallo comunicación central"),
    (r"camara|arlo|cloudcam|imagen|video", "7057", "Fallos de imagen / vídeo"),
    (r"tag reader|teclado|lector", "7054", "Avería teclado/tag reader"),
    (r"no detecta|zona abierta|no actualiza su estado", "7056", "Dispositivo no detecta"),
]

MOTIVOS_PILAS = ("pilas bajas", "diy pilas", "bateria equipo")
MOTIVOS_COM = ("bloqueos gsm",)
MOTIVOS_CAMARA = ("camara arlo", "otros - cliente con camara")


def _n(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _peticion(texto_actividad):
    """Parte del texto que escribio quien abrio el mantenimiento (antes de '**** Mant:')."""
    return texto_actividad.split("****")[0]


def _panel(ficha):
    p = _n(ficha.get("panel")) + " " + _n(ficha.get("grupo_panel"))
    if "sdvecu" in p:
        return "Moonshot"
    if "sdvfast" in p or "verifast" in p or "verisure" in p:
        return "Fast"
    return ""


def _zonas_citadas(texto):
    """Codigos de zona tipo MG02, SR05, QR08, YR01, VV01, TI01 citados en un texto."""
    return set(re.findall(r"\b([A-Z]{2}\d{2})\b", texto or ""))


def _codigos(ficha):
    return [{"causa": c.get("CAUSA", "").strip(), "res": c.get("RESOLUCION", "").strip().upper(),
             "zona": (c.get("ZONA RESOLUCION", "") or "").strip(), "item": (c.get("ID ITEM", "") or "").strip()}
            for c in ficha.get("codificaciones") or []]


def _resumen_codigos(cods):
    if not cods:
        return "sin codificar"
    return "; ".join(f"{c['causa'] or '?'}/{c['res'] or '?'}" + (f"/{c['zona']}" if c["zona"] and c["zona"] != "null" else "")
                     for c in cods)


def analizar(ficha, motivo_post=""):
    texto = ficha.get("texto_actividad") or ""
    pet = _n(_peticion(texto))
    obs_original = (ficha.get("observaciones_tecnico") or "").strip()
    obs = _n(obs_original)
    post = _n(motivo_post)
    cods = _codigos(ficha)
    hist = ficha.get("historico") or []

    menciona_placas = "placas disuasorias" in obs
    # Lineas que NO son el cambio de placas (7061/MONT cuando el tecnico dice que cambio placas)
    utiles = [c for c in cods if not (menciona_placas and c["causa"] == "7061" and c["res"] == "MONT")]
    res = {c["res"] for c in utiles}
    hay_sust = any(r.startswith("SUST") for r in res)
    hay_ampl = any(r.startswith("AMPL") for r in res)
    hay_reub = any(r.startswith("REUB") for r in res)
    solo_revi = bool(utiles) and res <= {"REVI"}

    causas, falto, cod_recomendada = [], [], []

    # ── cod: lo que hizo no esta en el parte ──
    cambia_pilas = bool(re.search(r"(camb|sustitu)\w* (de )?(las )?(pilas|bateri)", obs)) or "pilas" in obs and "cambi" in obs
    amplia = bool(re.search(r"\bse ampli|amplia\b|amplian\b", obs))
    monta = bool(re.search(r"se (coloca|monta|instala)", obs))
    sustituye = bool(re.search(r"se sustituye(?! pila)|sustituye (el|la|mg|qr|foto|tag|teclado|sirena|central)", obs))
    if not obs_original:
        causas.append("cod")
        falto.append("El parte no tiene observaciones: hay que escribir qué se hizo.")
    if cambia_pilas and not hay_sust:
        causas.append("cod")
        falto.append("Cambió pilas pero no las codificó: cada cambio de pilas va como SUST en su zona con su referencia.")
        cod_recomendada.append("SUST de pilas por zona (205036 MG Moonshot, 7014 AA, 7002 MG/SR Fast)")
    if (amplia or monta) and not hay_ampl and not any(r in res for r in ("MONT", "MONU")):
        causas.append("cod")
        falto.append("Lo que amplió o montó no está en el parte: va como AMPL (o MONU si ya era del cliente) con su referencia.")
    if sustituye and not hay_sust:
        causas.append("cod")
        falto.append("Sustituyó un dispositivo y no está codificado como SUST.")

    # Causa que corresponde al aviso
    causa_ok = None
    for patron, codigo, nombre in CAUSA_AVISO:
        if re.search(patron, pet):
            causa_ok = (codigo, nombre)
            break
    if not causa_ok and re.search(r"camara|arlo|cloudcam|hub", obs):
        causa_ok = ("7057", "Fallos de imagen / vídeo")
    if causa_ok and not any(c["causa"] == causa_ok[0] for c in utiles):
        if not utiles:
            falto.append("No hay ninguna línea del aviso en el parte (solo placas o nada).")
        if "cod" not in causas:
            causas.append("cod")
        cod_recomendada.insert(0, f"causa {causa_ok[0]} {causa_ok[1]}")

    # ── reit: el fallo ya estaba y no se cambio/reubico el dispositivo ──
    zonas = _zonas_citadas(_peticion(texto))
    repetido_hist = any(z in (h.get("texto") or "") for z in zonas for h in hist
                        if "revisiones remotas" not in _n(h.get("razon")))
    avisa_reincidente = bool(re.search(r"reincident|reiterad|ya fue tecnico", pet))
    if re.search(r"camara|arlo|hub", pet + " " + obs + " " + post):
        repetido_hist = repetido_hist or any(re.search(r"camara|arlo|hub", _n(h.get("texto"))) for h in hist
                                             if "revisiones remotas" not in _n(h.get("razon")))
    if (repetido_hist or avisa_reincidente) and not (hay_sust and not cambia_pilas) and not hay_reub \
            and not re.search(r"reubic|sustitu(?!.*pila)", obs):
        causas.append("reit")
        falto.append("El fallo ya se había repetido en esta instalación: cambiar pilas o revisar no basta, "
                     "había que reubicar o sustituir el dispositivo.")

    if re.search(r"\banula", obs) and not hay_sust and "reit" not in causas:
        causas.append("reit")
        falto.append("Anuló la zona en vez de sustituir el dispositivo que fallaba.")

    # ── texto: lo que pedia el texto y no aparece hecho ──
    if re.search(r"por (lejania|cercania)", pet) and not hay_reub and "reubic" not in obs and "reit" not in causas:
        causas.append("texto")
        falto.append("El aviso era por distancia (lejanía/cercanía): tocaba verificar la distancia y reubicar.")
    if re.search(r"sustituir pilas", pet) and not cambia_pilas:
        causas.append("texto")
        falto.append("El texto pedía cambiar pilas de otra zona y no consta.")
    pet_sin_condicion = re.sub(r"de estar correcto,? sustituir \w+", "", pet)
    if re.search(r"sustituir (el |la )?(magnetico|detector|dispositivo|mg|sr|qr)|valorar sustitucion", pet_sin_condicion) \
            and not hay_sust and "sustitu" not in obs:
        causas.append("texto")
        falto.append("El texto pedía sustituir el dispositivo y no se sustituyó.")
    pendiente_sim = any(re.search(r"cambiar (la )?sim", _n(h.get("texto"))) for h in hist[:2])
    if (re.search(r"cambiar (la )?sim", pet) or pendiente_sim) and "sim" not in obs:
        if pendiente_sim:
            causas.append("com")
        causas.append("texto")
        falto.append("El texto pedía cambiar la SIM de operador y no se hizo.")
    if re.search(r"reubicar", pet) and not hay_reub and "reubic" not in obs:
        causas.append("texto")
        falto.append("El texto pedía reubicar y no consta.")

    # ── pilas: la vuelta fue por pilas ──
    if any(m in post for m in MOTIVOS_PILAS) and not re.search(r"todas las pilas|pilas a todos|todos los (elementos|dispositivos)", obs):
        n_sust = sum(1 for c in utiles if c["res"].startswith("SUST"))
        if n_sust < 3:
            causas.append("pilas")
            falto.append("Volvieron por pilas: revisar el historial y, si hace más de un año, cambiar todas; "
                         "entre 6 meses y un año, como mínimo teclado o tag reader, sirena y MG1.")

    # ── com: comunicaciones ──
    pide_com = bool(re.search(r"ddi|gsm|cobertura|\bsim\b|no envia|missing", pet))
    revisa_com = bool(re.search(r"cobertura|\bsim\b|router|wifi|internet|operador|antena", obs))
    if (pide_com or any(m in post for m in MOTIVOS_COM)) and not revisa_com and "7052" not in {c["causa"] for c in utiles}:
        causas.append("com")
        falto.append("No consta revisión de comunicaciones: cobertura, DDI, SIM de otro operador y central conectada a internet.")

    # ── cam: volvieron por camara y no se revisaron ──
    if any(m in post for m in MOTIVOS_CAMARA) and not re.search(r"camara|arlo|cloud|hub|video", obs):
        causas.append("cam")
        falto.append("Volvieron por las cámaras y no se revisaron: revisar el sistema entero, cámaras incluidas.")

    causas = list(dict.fromkeys(causas)) or ["ok"]
    if causas == ["ok"]:
        severidad = "baja"
        falto.append("No se ve en la ficha un fallo claro del técnico: revisar a mano.")
    elif any(c in causas for c in ("reit", "texto", "pilas")) or len(causas) >= 3:
        severidad = "alta"
    else:
        severidad = "media"

    codificacion = _resumen_codigos(cods)
    if cod_recomendada:
        codificacion += " → " + " + ".join(dict.fromkeys(cod_recomendada))

    return {
        "causas": causas,
        "severidad": severidad,
        "panel": _panel(ficha),
        "queHizo": obs_original or "Parte sin observaciones.",
        "queFalto": " ".join(falto),
        "codificacion": codificacion,
    }
