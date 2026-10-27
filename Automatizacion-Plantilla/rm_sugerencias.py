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

# Prefijos de zona (confirmados por Gustavo 27/10). SRnn es el sismico del magnetico MGnn: el mismo aparato.
DISPOSITIVO = {"MG": "magnético", "MR": "magnético", "SR": "magnético (sísmico)", "QR": "detector con foto",
               "YR": "detector con foto", "XR": "detector con foto", "QP": "perimetral", "YP": "perimetral con foto",
               "XP": "perimetral con foto", "KP": "teclado", "VV": "teclado", "TI": "tag reader", "TO": "tag reader",
               "ZR": "sirena", "FR": "detector de humo", "B3": "pulsador", "DR": "cerradura (smartlock)"}
FOTOS, MAGNETICOS, PERIMETRALES = ("QR", "YR", "XR"), ("MG", "MR"), ("QP", "YP", "XP")


def _mismo_aparato(z):
    """SR01 y MG01 son el mismo magnetico: se buscan las dos formas en el historico."""
    return {z, "MG" + z[2:]} if z.startswith("SR") else {z, "SR" + z[2:]} if z.startswith("MG") else {z}


def _cuenta(zonas, prefijos):
    return sum(1 for z in zonas if z.get("ID", "")[:2] in prefijos)


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
    ultimo_mes = [h for h in visitas if (_fecha(h.get("apertura")) or date.min) >= date.fromordinal(hoy.toordinal() - 30)]
    if len(ultimo_mes) >= 4 or "heavy repeater" in pet:
        alertas.append("HEAVY REPEATER (4 o más visitas en el último mes).")
        hacer.append("Heavy Repeater: llama a Soporte Técnico (66043) antes de finalizar la validación; "
                     "cuando se llama, no vuelve a repetirse.")
    if _n(ficha.get("historial_atipico")) in ("si", "sí", "s"):
        alertas.append("Instalación marcada con historial atípico.")

    # ── zona del aviso que ya fallo antes ──
    for z in sorted(_zonas_citadas(pet_original)):
        previas = [h for h in visitas if any(a in (h.get("texto") or "") for a in _mismo_aparato(z))]
        if previas:
            disp = DISPOSITIVO.get(z[:2], "dispositivo")
            alertas.append(f"La zona {z} ({disp}) ya falló antes ({len(previas)} visita/s en el histórico).")
            ya_sustituido = any(re.search(r"sustitu|\bsust\b|cambi\w* (el |la |de )?(dispositivo|detector|magnetico|sirena|teclado|foto)", t)
                                and not re.search(r"pila|bateri", t) for t in (_n(h.get("texto")) for h in previas))
            if ya_sustituido and re.search(r"pila|bateri|supervis", pet):
                hacer.append(f"{z}: el dispositivo ya se sustituyó y sigue fallando: cambiarlo otra vez no lo arregla. "
                             "REUBÍCALO o cambia de tipo de dispositivo, y mide el RSSI con salto (no con tamper).")
            elif any(re.search(r"pila|bateri|supervis", _n(h.get("texto"))) for h in previas):
                hacer.append(f"{z}: ya fue un técnico por batería baja o supervisión. SUSTITUYE el dispositivo ({disp}); "
                             "no se vuelven a cambiar las pilas.")
            else:
                hacer.append(f"{z}: si vuelve a fallar no basta con pilas. Lleva {disp} para SUSTITUIR o REUBÍCALO; "
                             "si cambias pilas otra vez, volverá.")
    if re.search(r"supervis", pet):
        hacer.append("Fallo de supervisión: si no tienes el fallo muy claro, cambia el dispositivo. Mide el RSSI con salto "
                     "(76-98 % o -86 a -29 dBm) y busca muros gruesos, puertas metálicas o inhibición.")

    if re.search(r"reincident", pet):
        hacer.append("El aviso es reincidente: SUSTITUYE el dispositivo (o reubícalo); revisar o cambiar pilas otra vez no basta.")
    if re.search(r"(mg\d*|magnetico)\b.{0,40}(se ha caido|caido|despegad)|(se ha caido|caido|despegad).{0,40}(mg\d*|magnetico)", pet):
        hacer.append("Magnético caído: además de fijarlo bien, otra resolución es SUSTITUIRLO (SUST con su referencia).")
    if re.search(r"tamper|caido|despegad", pet):
        if panel == "Moonshot":
            hacer.append("Tamper o caído en Moonshot: base NUEVA de Shock Sensor (202409) obligatoria, nunca reutilizar. "
                         "Atornilla si puedes; si pegas, limpia con la toallita 201127.")
        elif panel == "Fast":
            hacer.append("Tamper en Fast: si cambias un 2250SP por F250SP/F252SP, cambia también la base (no son compatibles). "
                         "Tag reader y sirena, de la misma tecnología (PIC/EFM) que el resto.")
    if re.search(r"falsa alarma|falsas alarmas|saltos? (sin|en falso)|fallo de armado", pet):
        hacer.append("Falsas alarmas: descarta en orden cliente → mascotas → entorno → equipo; cambia el dispositivo solo al final. "
                     "Si el texto trae diagnóstico de CRA (reubicación), haz lo que indica."
                     + (" Si el imán queda separado, imán potente 202411 (+ espaciador 202407)." if panel == "Moonshot" else ""))
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
    zonas = ficha.get("zonas") or []
    m = _meses(base, hoy) if base else None
    if base:
        cuando = (f"último cambio de pilas hace {m} meses" if ult_pilas
                  else f"no consta cambio de pilas en el histórico (instalación hace {m} meses)")
        pequena = (_cuenta(zonas, FOTOS) <= 4 and _cuenta(zonas, MAGNETICOS) <= 6
                   and _cuenta(zonas, PERIMETRALES) <= 2)
        if m >= 12 and pequena:
            hacer.append(f"Pilas: {cuando}. Más de 1 año: cambia TODAS sin excepción, vayas por lo que vayas ({refs}).")
        elif m >= 12:
            minimo = ("teclado de entrada, sirena y foto de entrada" if panel == "Fast"
                      else "teclado de entrada, foto de entrada y los magnéticos por donde entran y salen")
            hacer.append(f"Pilas: {cuando}. Instalación grande con más de 1 año: arregla el fallo y cambia como "
                         f"mínimo {minimo} ({refs}).")
        elif m >= 6:
            hacer.append(f"Pilas: {cuando}. Como mínimo teclado o tag reader, sirena y MG1 ({refs}).")
        # con mas de 1 año ya va arriba (todas, o el minimo de una instalacion grande)
        if panel == "Moonshot" and 8 <= m < 12 and _cuenta(zonas, MAGNETICOS):
            hacer.append(f"Magnéticos de puertas: {cuando}. En Moonshot se cambian cada 8 meses, aunque vayas por otra cosa.")
        if panel == "Fast" and m >= 5 and not (m >= 12 and pequena) and _cuenta(zonas, ("FR",)):
            hacer.append(f"Detectores de humo: {cuando}. En Fast, con más de 5 meses se cambian sus pilas aunque vayas por otra cosa.")
    elif re.search(r"pila|bateria", pet):
        hacer.append(f"Aviso de pilas sin fecha del último cambio: revisa el estado de todas ({refs}).")

    # best practice ANP/Traslados/RBE: su ratio de RM es peor que el de las altas nuevas
    if re.search(r"\banp\b|montaje de alarma|traslado|\brbe\b", tipo):
        hacer.append("ANP / montaje por traslado / RBE: cambia las pilas de TODOS los elementos vía radio y sustituye "
                     "los dispositivos antiguos (DESM del viejo + MONT del nuevo).")

    # ── fallo de supervision: arbol oficial de Pharus (All4Tech, lista FalloSupervision) ──
    if re.search(r"supervis", pet + " " + tipo):
        if len(_zonas_citadas(pet_original)) >= 3:
            paso = "3 o más zonas a la vez: es el receptor RF de la central, CAMBIA LA CENTRAL"
        elif m is not None and m >= 12:
            paso = f"pilas de hace {m} meses (más de 1 año): CAMBIA LAS PILAS DE TODOS los dispositivos"
        elif ult_pilas and (hoy - ult_pilas).days < 90:
            paso = "pilas cambiadas hace menos de 3 meses: consumo excesivo, CAMBIA EL DISPOSITIVO con sus pilas"
        else:
            paso = "mide el voltaje: si es correcto, cambia el dispositivo con sus pilas; si no, revisa el RSSI"
        hacer.append("Supervisión (árbol oficial): si el fallo es continuo, RSSI correcto → cambia el dispositivo con sus pilas; "
                     f"RSSI incorrecto → reubícalo con pilas nuevas. Si es con reset: {paso}.")

    # ── cerradura electrica (smartlock / DR): no sale en las zonas, se busca en los textos ──
    textos = [ficha.get("texto_actividad") or "", ficha.get("observaciones_tecnico") or ""] + [h.get("texto") or "" for h in hist]
    if "smartlock" in tipo or any(re.search(r"smart ?lock|\bDR\d{2}\b", t, re.I) for t in textos):
        f_cerr = None
        for h in visitas:
            t = _n(h.get("texto"))
            if re.search(r"smart ?lock|\bdr\d{2}\b|cerradura", t) and re.search(r"pila|bateri", t):
                f = _fecha(h.get("cierre")) or _fecha(h.get("apertura"))
                if f and (not f_cerr or f > f_cerr):
                    f_cerr = f
        desde = f_cerr or base
        mc = _meses(desde, hoy) if desde else None
        if mc is None or mc >= 5:
            hacer.append("Cerradura eléctrica (smartlock): " + (f"pilas cambiadas hace {mc} meses. " if mc is not None else "")
                         + "Con más de 5 meses se cambian sus pilas (4 × CR123A, ref. 7002) aunque vayas por otra cosa; "
                         "después de cambiarlas hay que calibrarla con la puerta abierta.")

    # ── FAST 2 ──
    if panel == "Fast" and "vf2" in _n(ficha.get("version_panel")):
        if re.search(r"bloqueo|fallo (de )?(la )?central|central (no|bloque)", tipo + " " + pet):
            if _cuenta(zonas, ("XP",)):
                hacer.append("Pase a FAST 4: los fotoperimetrales OPDD (zona XP) no son compatibles; lleva OPDI F455SP para sustituirlos.")
            hacer.append("FAST 2 con bloqueo GSM o fallo de central: hay que pasarla a FAST 4."
                         + (" Al resetear los dispositivos, cambia también las pilas de todos." if m is not None and m >= 12 else "")
                         + " Batería nueva F013 (nunca la 9082). Sin coste: AMPL de F049 + F055 + F057 (o el pack, no los dos), "
                         "DESM de la Fast 2 y MONT de la SIM.")
        if re.search(r"\b2g\b", pet):
            hacer.append("FAST 2 transmitiendo en 2G: 1) monetiza el cambio a FAST 4 (AMPLIAR); 2) si no, cambia la SIM y "
                         "verifica que queda en 3G; 3) cambio a FAST 4 a coste 0 (AMPL F049) según zonas y riesgo en ruta: "
                         "LLAMA OBLIGATORIAMENTE AL JE antes.")

    # ── caducidad: IMA no deja salir de programacion con humo caducado o a menos de 1 año ──
    f_inst = _fecha(ficha.get("fecha_instalacion"))
    if f_inst and _cuenta(zonas, ("FR",)) and _meses(f_inst, hoy) >= 108:
        hacer.append(f"Detector de humo de hace {_meses(f_inst, hoy) // 12} años: si está caducado o le queda menos de 1 año, "
                     "IMA no te deja salir de programación. Lleva uno nuevo.")

    if f_inst and _cuenta(zonas, ("FG",)) and _meses(f_inst, hoy) >= 48:
        hacer.append("ZeroVision: la cánula caduca a los 5 años y IMA bloquea si le queda menos de 1 año. "
                     "Revisa la fecha y lleva cánula de repuesto.")

    if any(h.startswith(("Pilas:", "Magnéticos de puertas", "Detectores de humo", "Cerradura eléctrica")) for h in hacer):
        hacer.append("Codificación de pilas: 'Añadir pilas' solo en los dispositivos en los que SOLO cambias pilas; "
                     "lo que sustituyas, amplíes o montes ya lleva sus pilas (si no, salen duplicadas).")

    # ── comunicaciones ──
    if any(t in tipo for t in TIPOS_COM) or (not venta and re.search(r"ddi|gsm|cobertura|\bsim\b|no envia|missing|no transmite|comunicacion", pet)):
        # prioridad de operador confirmada por Gustavo 27/10/2026: Vodafone
        sim = "prioridad Vodafone; Movistar fuera salvo que no haya otra" + ("; deja módulo 3G" if panel == "Fast" else "")
        hacer.append(f"Comunicaciones: prueba SIM de todos los operadores y deja la de mejor cobertura ({sim}). "
                     "Revisa DDI, antena y que la central esté conectada a internet; nada de antenas exteriores. Causa 7052. "
                     "La SIM se codifica en Añadir trabajos como MONT (no 'Datos de SIM' ni causa 2500/2501)."
                     + (" Conecta la CU al router del cliente por cable (o wifi): sin internet hay el doble de missing test."
                        if panel == "Moonshot" else
                        " Si es 4PRO, conéctala al wifi del cliente." if "vf4" in _n(ficha.get("version_panel")) else "")
                     + (f" Instalación de hace {_meses(f_inst, hoy) // 12} años: cambia la batería de la central si tiene más de 2 años "
                        f"({'205086' if panel == 'Moonshot' else 'F013, nunca la 9082'})." if f_inst and _meses(f_inst, hoy) >= 24 else ""))

    # ── camaras ──
    if not venta and (re.search(r"camara|arlo|hub|cloudcam", pet) or "arlo" in tipo):
        hacer.append("Cámaras: casi siempre es la señal wifi, no la cámara: mídela con Wifi Analyzer antes de cambiarla "
                     "(subida ≥ 1 Mb). Exterior siempre con HUB (a 1 m del router, en altura, punto intermedio) y panel solar "
                     "al sol directo con el cable tensado; configura 'Mejor duración de la batería', zonas de actividad, "
                     "menos sensibilidad y clips de 30 s. Si cambió el router, desvincular y volver a grabar.")

    return {"alertas": alertas, "hacer": list(dict.fromkeys(hacer)), "panel": panel}
