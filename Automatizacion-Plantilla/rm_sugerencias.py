"""
PROTOTIPO: que hacer en cada mantenimiento de la ruta para que no se repita.

Son las reglas de rm_reglas.py (lo que fue ensenando Gustavo revisando RMs)
pero mirando ANTES de la visita: el aviso, el panel, las zonas y el historico
de la instalacion.

sugerir(ficha) -> {"alertas": [...], "hacer": [...]} (frases cortas)
"""

import re
from datetime import date, datetime

from rm_reglas import _n, _panel, _peticion, _zonas_citadas

DISPOSITIVO = {"MG": "magnético", "SR": "sirena", "QR": "detector con foto", "YR": "teclado/tag reader",
               "YP": "teclado", "VV": "detector de vibración", "TI": "tag reader", "PS": "pulsador",
               "SH": "detector de humo", "AG": "detector de agua"}


def _fecha(txt):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", txt or "")
    if not m:
        return None
    d, mes, a = (int(x) for x in m.groups())
    a += 2000 if a < 100 else 0
    try:
        return date(a, mes, d)
    except ValueError:
        return None


def _meses(desde, hoy):
    return (hoy.year - desde.year) * 12 + hoy.month - desde.month


def _visitas(hist):
    """Visitas reales: sin revisiones remotas ni las lineas sueltas de CUSTVE (envios al cliente)."""
    return [h for h in hist if "revisiones remotas" not in _n(h.get("razon")) and h.get("tecnico") != "CUSTVE"]


# Visitas en las que no toca sugerir nada (instalacion nueva, baja, remoto)
TIPOS_SIN_SUGERENCIAS = ("desmontaje", "anp remoto", "campana")
TIPOS_COM = ("cobertura",)


def es_mantenimiento(ficha):
    tipo = _n(ficha.get("tipo"))
    if any(t in tipo for t in TIPOS_SIN_SUGERENCIAS):
        return False
    if "montaje" in tipo and not any(z.get("ID", "").strip("*") not in ("", "NOIM") for z in ficha.get("zonas") or []):
        return False   # montaje/traslado sin zonas todavia
    return True


def sugerir(ficha, hoy=None):
    hoy = hoy or date.today()
    pet_original = _peticion(ficha.get("texto_actividad") or "")
    pet = _n(pet_original)
    tipo = _n(ficha.get("tipo"))
    venta = bool(re.search(r"vap|modelo de pago|cuota fija|cliente acepta", pet))
    panel = _panel(ficha)
    hist = ficha.get("historico") or []
    visitas = _visitas(hist)
    alertas, hacer = [], []

    # ── RM en riesgo: ya hubo una visita hace poco ──
    if "ha tenido un mantenimiento recientemente" in pet:
        alertas.append("Viene de un mantenimiento reciente: si es el mismo fallo ya cuenta como RM. Arréglalo a fondo.")
    ultima = next((h for h in visitas if _fecha(h.get("cierre")) or _fecha(h.get("apertura"))), None)
    if ultima:
        f_ult = _fecha(ultima.get("cierre")) or _fecha(ultima.get("apertura"))
        dias = (hoy - f_ult).days
        if 0 <= dias <= 30:
            alertas.append(f"Última visita hace {dias} días (técnico {ultima.get('tecnico') or '?'}): "
                           "si el fallo es el mismo, es una RM.")

    # ── la instalacion ya da guerra ──
    recientes = [h for h in visitas if (_fecha(h.get("apertura")) or date.min) >= date.fromordinal(hoy.toordinal() - 60)]
    if len(recientes) >= 2:
        alertas.append(f"Instalación reincidente: {len(recientes)} visitas en los últimos 60 días.")
    if _n(ficha.get("historial_atipico")) in ("si", "sí", "s"):
        alertas.append("Instalación marcada con historial atípico.")

    # ── zona del aviso que ya fallo antes ──
    for z in sorted(_zonas_citadas(pet_original)):
        previas = [h for h in visitas if z in (h.get("texto") or "")]
        if previas:
            disp = DISPOSITIVO.get(z[:2], "dispositivo")
            alertas.append(f"La zona {z} ({disp}) ya falló antes ({len(previas)} visita/s en el histórico).")
            hacer.append(f"{z}: si vuelve a fallar no basta con pilas. Lleva {disp} para SUSTITUIR o REUBÍCALO; "
                         "si cambias pilas otra vez, volverá.")

    if re.search(r"reincident", pet):
        hacer.append("El aviso es reincidente: SUSTITUYE el dispositivo (o reubícalo); revisar o cambiar pilas otra vez no basta.")
    if re.search(r"(mg\d*|magnetico)\b.{0,40}(se ha caido|caido|despegad)|(se ha caido|caido|despegad).{0,40}(mg\d*|magnetico)", pet):
        hacer.append("Magnético caído: además de fijarlo bien, otra resolución es SUSTITUIRLO (SUST con su referencia).")
    if re.search(r"anulad", pet):
        hacer.append("Hay zonas anuladas: no las dejes anuladas, sustituye lo que falla.")
    if re.search(r"cambiar placa si es recurrente", pet):
        hacer.append("Si el fallo de la central es recurrente, cambia la placa.")

    # ── lo que pide el aviso ──
    if re.search(r"por (lejania|cercania)", pet):
        hacer.append("Aviso por distancia: mide la cobertura del dispositivo y REUBICA (el dispositivo o la central); "
                     "solo cambiar pilas no lo arregla.")
    for patron, frase in [
        (r"sustituir (el |la )?(magnetico|detector|dispositivo|mg|sr|qr)|valorar sustitucion", "El texto pide sustituir el dispositivo: llévalo y sustitúyelo."),
        (r"cambiar (la )?sim", "El texto pide cambiar la SIM de operador: lleva una SIM de otro operador."),
        (r"reubicar", "El texto pide reubicar: hazlo y codifícalo como REUB."),
        (r"sustituir pilas", "El texto pide cambiar pilas de otra zona: cámbialas también."),
    ]:
        if re.search(patron, re.sub(r"de estar correcto,? sustituir \w+", "", pet)):
            hacer.append(frase)
    pendiente_sim = any(re.search(r"cambiar (la )?sim", _n(h.get("texto"))) for h in hist[:2])
    if pendiente_sim and not re.search(r"cambiar (la )?sim", pet):
        hacer.append("En el histórico quedó pendiente cambiar la SIM: lleva SIM de otro operador.")

    # ── pilas: cuando se cambiaron por ultima vez ──
    ult_pilas = None
    for h in visitas:
        if re.search(r"\bpilas?\b|bateri", _n(h.get("texto"))) and re.search(r"camb|sustitu|sust\b", _n(h.get("texto"))):
            f = _fecha(h.get("cierre")) or _fecha(h.get("apertura"))
            if f and (not ult_pilas or f > ult_pilas):
                ult_pilas = f
    base = ult_pilas or _fecha(ficha.get("fecha_instalacion"))
    refs = ("205036 (AAA) en MG Moonshot, 7014 las AA" if panel == "Moonshot"
            else "7002 (CR123) en MG/SR, 7006 en teclado YP" if panel == "Fast" else "con su referencia")
    if base:
        m = _meses(base, hoy)
        cuando = (f"último cambio de pilas hace {m} meses" if ult_pilas
                  else f"no consta cambio de pilas en el histórico (instalación hace {m} meses)")
        if m >= 12:
            hacer.append(f"Pilas: {cuando}. Cambia TODAS ({refs}).")
        elif m >= 6:
            hacer.append(f"Pilas: {cuando}. Como mínimo teclado o tag reader, sirena y MG1 ({refs}).")
    elif re.search(r"pila|bateria", pet):
        hacer.append(f"Aviso de pilas sin fecha del último cambio: revisa el estado de todas ({refs}).")

    # ── comunicaciones ──
    if any(t in tipo for t in TIPOS_COM) or (not venta and re.search(r"ddi|gsm|cobertura|\bsim\b|no envia|missing|no transmite|comunicacion", pet)):
        hacer.append("Comunicaciones: revisa cobertura, DDI, SIM de otro operador y que la central esté conectada a internet. Causa 7052.")

    # ── camaras ──
    if not venta and (re.search(r"camara|arlo|hub|cloudcam", pet) or "arlo" in tipo):
        hacer.append("Cámaras: comprueba wifi y velocidad de subida (≥ 1 Mb) y el hub; si cambió el router, desvincular y volver a grabar.")

    return {"alertas": alertas, "hacer": list(dict.fromkeys(hacer)), "panel": panel}
