"""
PROTOTIPO: errores de codificacion en el parte de un mantenimiento cerrado.

Cruza lo que escribe el tecnico (observaciones) con las lineas codificadas
(CAUSA / RESOLUCION / ID ITEM / NUMERO ITEMS) usando las reglas de los
comunicados de Verisure ("Correo Recuentos/comunicados-verisure.md") y las que
fue ensenando Gustavo. Cada hallazgo es una frase corta para el jefe de equipo.

revisar(ficha) -> lista de {"tipo", "texto"} (vacia si no se ve nada raro)
"""

import re

from rm_reglas import _n, _panel

PLACAS = re.compile(r"^(ZES\d+|Z3124)$")          # cambio de placas disuasorias (7061/MONT): no cuenta
SIMS = {"9066", "9085", "9088", "9107", "9114", "9115", "203101", "203102", "203118"}
BATERIA_CENTRAL = {"F013", "205086"}
CENTRALES_FAST2 = re.compile(r"^(F039A?|F035\w*|F017|FPN02R?)$")
PACK_4PRO = re.compile(r"^(OXVSF4|RXVSF4)\w+$")
ZV = {"135058", "135059", "135059F", "135104", "FOG001", "FOG003SP", "FOG100"}
MANDOS = {"280785", "280786", "2409SP", "2410SP", "2411SP", "2412SP"}
LLAVES = re.compile(r"^(F44\d|1313(47|48)|13137\d)$")
MAGNETICOS = {"121272", "121295", "2250SP", "F250SP", "F252SP"}   # MG Moonshot (MC2/MC3) y Fast (MGLS/MGLS+)
PILAS = {"7002", "7006", "7008", "7014", "205036", "205112", "205114"}
VIEJAS = {"121272": "ya no se envía: si pusiste un MC3 va DESM 121272 + MONT 121295",
          "199005": "es un kit: no se codifica en un parte",
          "199013": "es un kit: no se codifica en un parte",
          "9082": "es la batería externa de Alianzas: la de 4PRO es la F013"}
# pilas por dispositivo (referencia, unidades por linea) y prefijos de zona que las llevan
PILAS_POR_ZONA = {
    # la 7014 la llevan muchos dispositivos distintos (y no todos salen en zonas): no se cuenta
    "Moonshot": [("205036", "2", ("MG", "MR"))],
    "Fast": [("7002", "1", ("MG", "FG", "B3"))],   # B3 = pulsador SOS (feedback JE 29/10)
}


def _lineas(ficha):
    out = []
    for c in ficha.get("codificaciones") or []:
        item = (c.get("ID ITEM") or "").strip().upper()
        res = (c.get("RESOLUCION") or "").strip().upper()
        if not item or PLACAS.match(item) or res == "ERRO":
            continue
        out.append({"causa": (c.get("CAUSA") or "").strip(), "res": res, "item": item,
                    "n": (c.get("NUMERO ITEMS") or "1").strip()})
    return out


def _observaciones(ficha):
    """Lo que escribio el tecnico: el campo de observaciones o, si viene vacio, lo que queda en el texto de la
    actividad tras '**** Mant: ... Observaciones: ...'."""
    obs = (ficha.get("observaciones_tecnico") or "").strip()
    if obs:
        return obs
    m = re.search(r"\*{4}\s*Mant:.*?Observaciones:\s*(.*?)\s*(\*{4}|$)", ficha.get("texto_actividad") or "", re.S)
    return m.group(1).strip() if m else ""


def _dice(obs, patron):
    return bool(re.search(patron, obs))


def no_revisable(ficha):
    """Montajes, upgrades y documentaciones (ALTA): no traen codificacion de material que revisar."""
    tipo = _n(ficha.get("tipo"))
    if re.search(r"anp remoto|(?<!des)montaje de alarma|upgrade", tipo):
        return True
    cods = ficha.get("codificaciones") or []
    return bool(cods) and all((c.get("RESOLUCION") or "").upper() == "ALTA" for c in cods)


def revisar(ficha):
    if (ficha.get("estado") or "").upper() != "FINL":
        return []      # CERR (en negro en la consola) = no se realizo: no hay parte que revisar
    if no_revisable(ficha):
        return []      # partes manuales / documentacion: no se revisan aqui
    tipo = _n(ficha.get("tipo"))
    if any((c.get("RESOLUCION") or "").upper() == "ERRO" for c in ficha.get("codificaciones") or []):
        return []
    obs_original = _observaciones(ficha)
    cods = ficha.get("codificaciones") or []
    if not obs_original and cods and not any((c.get("ID ITEM") or "").strip() for c in cods):
        return []      # cerrado con soporte: lineas sin referencia y sin observaciones (feedback JE 29/10)
    obs = _n(obs_original)
    pet = _n((ficha.get("texto_actividad") or "").split("****")[0])
    panel = _panel(ficha)
    lin = _lineas(ficha)
    items = {l["item"] for l in lin}
    res_de = lambda r: [l for l in lin if l["res"].startswith(r)]
    disp = [l for l in lin if l["item"] not in PILAS]
    h = []

    def mal(tipo_h, texto):
        h.append({"tipo": tipo_h, "texto": texto})

    # ── parte vacio ──
    if not obs_original and not re.search(r"\banp\b|upgrade|nueva instalacion|cambio de equipo", tipo):
        mal("observaciones", "Parte sin observaciones: hay que escribir qué se hizo.")
    if not lin and not re.search(r"placas disuasorias|revision", obs + " " + tipo):
        mal("sin codificar", "No hay nada codificado del motivo del aviso.")

    # ── cambio de Fast 2 a 4PRO ──
    a4 = [l for l in lin if (l["res"] == "AMPL" and PACK_4PRO.match(l["item"])) or (l["item"] == "F049" and l["res"] in ("AMPL", "MONT"))]
    if a4:
        if not any(CENTRALES_FAST2.match(l["item"]) and l["res"] in ("DESM", "DESU") for l in lin):
            mal("4PRO", "Pasa a 4PRO y no codifica el DESM de la central Fast 2 retirada.")
        if not items & SIMS:
            mal("4PRO", "Pasa a 4PRO y no codifica la SIM nueva (MONT de la 9114 Vodafone / 9115 Orange): la de la Fast 2 no sirve.")
        if any(l["item"] == "F013" and l["res"] != "SUST" for l in lin):
            mal("4PRO", "La batería F013 va como SUST cuando se cambia (si no se cambia, no se codifica).")
        if any(PACK_4PRO.match(l["item"]) for l in a4) and items & {"F049", "F055", "F057"}:
            mal("4PRO", "Codifica el pack de 4PRO y además F049/F055/F057 sueltas: el pack ya las incluye.")
        if not any(PACK_4PRO.match(l["item"]) for l in a4) and not {"F055", "F057"} <= items:
            mal("4PRO", "Codifica la central F049 suelta sin la fuente F055 y el soporte F057: sin pack van las tres.")
        if any(l["item"] in ("F049", "F055", "F057") and l["res"] == "MONT" for l in lin):
            mal("4PRO", "F049/F055/F057 van como AMPL (desde julio de 2026), no como MONT.")

    # ── referencias que no tocan ──
    for l in lin:
        if l["item"] in VIEJAS and l["res"] not in ("DESM", "DESU", "MONU"):
            mal("referencia", f"{l['res']} de {l['item']}: {VIEJAS[l['item']]}.")

    # ── misma referencia montada y desmontada: es una SUST ──
    # DESM (se lo lleva el tecnico) y DESU (se lo queda el cliente, o perdida) valen los dos al retirar (Gustavo, 29/10):
    # solo MONT + DESM de la misma referencia deberia ser SUST
    misma = {l["item"] for l in res_de("MONT")} & {l["item"] for l in res_de("DESM")}
    for it in misma:
        mal("sustitución", f"MONT + DESM de la misma referencia {it}: si es la misma referencia es una SUST.")
    # ── dice que sustituye y solo hay medio cambio ──
    sustituye = _dice(obs, r"se sustitu\w* (?!(el |la |los |las |un |una |dos |tres |cuatro |\d+ )*(bater|pila|sim\b|fuente|zv|zero|canula|bases?\b|soportes?\b))(el |la |los |las )?\w+|se cambia (el |la )?(magnetico|sirena|foto|teclado|tag)")
    # las bases y soportes (p. ej. base de magnetico) son piezas que no se codifican (Gustavo, 29/10)
    sust_disp = [l for l in res_de("SUST") if l["item"] not in PILAS]
    if sustituye and not sust_disp:
        if res_de("DESM") and not res_de("MONT"):
            mal("sustitución", "Dice que sustituye y solo codifica el DESM: falta el MONT del dispositivo nuevo.")
        elif [l for l in res_de("MONT") if l["item"] not in SIMS] and not (res_de("DESM") or res_de("DESU") or res_de("MONU")) \
                and not _dice(obs, r"instalacion anterior|otra instalacion"):
            # la SIM no se desmonta y lo que viene de otra instalacion (MONU) no tiene DESM (feedback JE 29/10)
            mal("sustitución", "Dice que sustituye y solo codifica el MONT: si es la misma referencia va SUST; "
                               "si es otra, DESM (o DESU si se lo queda el cliente) del viejo + MONT del nuevo.")
        elif not disp:
            mal("sustitución", "Dice que sustituye un dispositivo y no está codificado (SUST con su referencia).")
    if _dice(obs, r"sustitu\w* (la )?(zv|zero ?vision|canula)") and not items & ZV:
        mal("sustitución", "Dice que sustituye el ZeroVision / la cánula y no lo codifica (SUST con su referencia).")
    if _dice(obs, r"fuente de alimen|bateria de (la )?central") and not items & (BATERIA_CENTRAL | {"F055", "153203"}):
        mal("sustitución", "Cambia fuente o batería de la central y no lo codifica (F055/F013 en Fast-4PRO, 205086 en Moonshot).")

    # ── SIM ──
    if _dice(obs, r"\bsim\b") and _dice(obs, r"sustitu|camb|coloca|pone") and not items & SIMS:
        mal("SIM", "Cambia la SIM y no la codifica: Añadir trabajos → referencia de la SIM → MONT.")
    if any(l["causa"] in ("2500", "2501") for l in lin):
        mal("SIM", "Usa la causa 2500/2501 (Upgrade): bloquea la facturación, no se usa en mantenimientos.")

    # ── reubicacion ──
    # la REUB no hace falta codificarla si el comentario dice que se reubica

    # ── desmontajes ──
    if _dice(obs, r"se (desmonta|elimina|retira)n? (\d+ ?)?(mg|magnetico|foto|tag|sirena|teclado|dispositivo|sentinel|centinel)") \
            and not (res_de("DESM") or res_de("DESU")):
        mal("desmontaje", "Dice que desmonta o elimina dispositivos y no codifica el DESM/DESU.")
    m = re.search(r"(?:elimina|desmonta|retira)n? (\d+) ?(?:mg|magneticos?)", obs)
    if m:
        n_desm = sum(int(l["n"] or 1) for l in lin if l["res"] in ("DESM", "DESU") and l["item"] in MAGNETICOS)
        if n_desm and n_desm != int(m.group(1)):
            mal("desmontaje", f"Dice que quita {m.group(1)} magnéticos y codifica {n_desm}.")

    # ── ampliaciones de mandos y llaves ──
    if _dice(obs, r"ampli\w* (\d+ )?mandos?") and not any(l["item"] in MANDOS and l["res"] == "AMPL" for l in lin):
        mal("ampliación", "Amplía mando(s) y no está la AMPL del mando (280785 Moonshot, 2409SP/2410SP Fast2, 2411SP 4PRO).")
    if _dice(obs, r"ampli\w* (\d+ )?llaves?") and not any(LLAVES.match(l["item"]) and l["res"] == "AMPL" for l in lin):
        mal("ampliación", "Amplía llave(s) y no va como AMPL con la referencia de la llave (está como MONT/SUST o no está).")

    # ── pilas ──
    # DESM de un dispositivo sin nada que lo explique
    if res_de("DESM") and not res_de("MONT") and not sust_disp and not a4 \
            and not _dice(obs, r"desmont|elimin|retir|quit|sustitu|baja|anul"):
        mal("desmontaje", "Codifica un DESM que no se explica en el parte: ¿lo retiró? Si lo cambió por otro falta el MONT del nuevo.")
    zonas = [z.get("ID", "")[:2] for z in ficha.get("zonas") or []]
    for ref, uds, prefijos in PILAS_POR_ZONA.get(panel, []):
        n_lin = sum(1 for l in lin if l["item"] == ref and l["n"] == uds and l["res"] == "SUST")
        # los MONT de dispositivos nuevos aun no salen en zonas y traen sus pilas como SUST
        n_disp = sum(1 for z in zonas if z in prefijos) + sum(int(l["n"] or 1) for l in disp if l["res"] == "MONT")
        if n_disp and n_lin > n_disp:
            mal("pilas", f"{n_lin} líneas de pilas {ref}×{uds} para {n_disp} dispositivo(s): hay pilas duplicadas "
                         "(lo sustituido o ampliado ya lleva sus pilas; no se marca en 'Añadir pilas').")
    # pila baja del perimetral YP (Fast): sus pilas son la 7006
    if panel == "Fast" and re.search(r"bateria baja de zona yp\d|pilas?\).{0,40}zona: yp\d", pet) and "7006" not in items:
        mal("pilas", "El aviso era pila baja del perimetral YP y no están codificadas sus pilas (7006).")
    if _dice(obs, r"(camb|sustitu)\w* (de )?(las )?(pilas|bateri)") and not items & PILAS \
            and not _dice(obs, r"bateria de (la )?central|bateria de mandos"):
        mal("pilas", "Dice que cambia pilas y no hay ninguna pila codificada ('Añadir pilas').")

    # ── comunicaciones ──
    # bloqueo GSM: en el comentario si se conecto a internet, o el cambio de SIM codificado
    gsm = "bloqueos gsm" in tipo
    # vale tambien si comprueba que transmite / senales ok o cambia la central: el bloqueo no siempre es
    # de la central o la SIM, a veces lo abre la voz del cliente (feedback JE 29/10)
    if gsm and not a4 and not items & SIMS and not _dice(obs, r"internet|router|wifi|wi-fi|ethernet|cable de red|\bsim\b|tarjeta|chip"
                                                         r"|transmi|senales (ok|correct)|operativ|(camb|sustitu)\w* (de )?(la )?central"):
        mal("comunicaciones", "Bloqueo GSM: falta indicar en observaciones si se conectó a internet (si se cambió la SIM, codificarla con MONT).")
    # (sin aviso generico de comunicaciones: lo disparaba la nota automatica "Missing Test... comprobar
    # cobertura" de Verisure y no es un error de codificacion; Gustavo, 28/10)

    # quitar repetidos manteniendo el orden
    vistos, out = set(), []
    for x in h:
        if x["texto"] not in vistos:
            vistos.add(x["texto"])
            out.append(x)
    return out


MEJORAS = {
    "observaciones": "Escribir siempre en el parte qué se ha hecho: sin observaciones no se puede comprobar la codificación.",
    "sin codificar": "Codificar siempre el motivo del aviso y todo lo instalado: lo que no se codifica descuadra el stock.",
    "4PRO": "Pase a 4PRO: con pack (OXVSF4…/RXVSF4…) la fuente F055 y el soporte F057 ya van dentro; con la central F049 suelta "
            "se codifican también F055 y F057. Siempre DESM de la Fast 2 y MONT de la SIM nueva; si se cambia la batería, SUST de la F013.",
    "sustitución": "Misma referencia → SUST. Otra referencia → MONT del nuevo + DESM (te lo llevas) o DESU (se lo queda el cliente).",
    "pilas": "'Añadir pilas' solo en los dispositivos en los que únicamente se cambian pilas: lo sustituido o ampliado ya lleva las suyas.",
    "SIM": "La SIM se codifica en Añadir trabajos con su referencia y resolución MONT (nunca 'Datos de SIM' ni causa 2500/2501).",
    "reubicación": "Todo lo que se reubica va codificado como REUB.",
    "desmontaje": "Todo lo que se retira va como DESM (o DESU si se lo queda el cliente), con las unidades exactas.",
    "ampliación": "Lo que se amplía (mandos, llaves…) va como AMPL con su referencia.",
    "referencia": "Usar la referencia que de verdad se instala (121295 MC3, F013 batería 4PRO; los kits no se codifican).",
    "comunicaciones": "En avisos de comunicaciones dejar constancia de lo revisado (SIM, cobertura, router) y codificarlo.",
}


def _e(s):
    import html
    return html.escape(str(s or ""))


def _cod_texto(ficha):
    ls = _lineas(ficha)
    return "; ".join(f"{l['res']} {l['item']}" + (f" ×{l['n']}" if l["n"] not in ("", "1") else "") for l in ls) or "nada"


def correo_html(jefe, fecha, tecnicos):
    """tecnicos: lista de (nombre, matricula, [(numero, tipo, obs, codificado, [hallazgos])])."""
    from collections import Counter
    tipos = Counter(h["tipo"] for _, _, ms in tecnicos for m in ms for h in m[4])
    n_mant = sum(len(ms) for _, _, ms in tecnicos)
    bloques = ""
    for nombre, mat, ms in tecnicos:
        filas = ""
        for numero, tipo, obs, cod, hall in ms:
            fallos = "".join(f'<li style="margin:2px 0">{_e(h["texto"])}</li>' for h in hall)
            filas += (f'<tr><td style="padding:8px 10px 8px 0;border-bottom:1px solid #eee;vertical-align:top;white-space:nowrap">'
                      f'<b>{_e(numero)}</b><br><span style="color:#777;font-size:12px">{_e(tipo)}</span></td>'
                      f'<td style="padding:8px 0;border-bottom:1px solid #eee;vertical-align:top">'
                      f'<ul style="margin:0;padding-left:18px">{fallos}</ul>'
                      f'<div style="color:#777;font-size:12px;margin-top:4px">Codificó: {_e(cod)}</div></td></tr>')
        bloques += (f'<p style="margin:18px 0 6px"><b>{_e(nombre)}</b> <span style="color:#777">({_e(mat)})</span></p>'
                    f'<table style="border-collapse:collapse;width:100%;font-size:14px">{filas}</table>')
    mejoras = "".join(f'<li style="margin:4px 0">{_e(MEJORAS[t])}</li>' for t, _ in tipos.most_common() if t in MEJORAS)
    return f"""<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:720px;line-height:1.45">
<p>Hola,</p>
<p>Revisando los partes del <b>{_e(fecha)}</b>, en <b>{n_mant} mantenimiento(s)</b> de tu equipo la codificación no cuadra con
lo que se hizo. Por técnico:</p>
{bloques}
<p style="margin:18px 0 4px"><b>En qué mejorar</b></p>
<ul style="margin:0;padding-left:20px">{mejoras}</ul>
<p>Gustavo Perez<br>Aurum BC Security SL</p></div>"""


# Version corta de cada hallazgo para el correo (el jefe de equipo lo lee de un vistazo)
CORTO = [
    (r"no codifica el DESM de la central Fast 2", "4PRO: falta DESM de la Fast 2"),
    (r"no codifica la SIM nueva", "4PRO: falta MONT de la SIM"),
    (r"pack de 4PRO y además", "4PRO: pack + F049/F055/F057 duplicado"),
    (r"F049 suelta sin la fuente", "4PRO: F049 sin F055/F057"),
    (r"van como AMPL \(desde julio", "4PRO: F049/F055/F057 en MONT → AMPL"),
    (r"F013 va como SUST", "Batería F013 → SUST"),
    (r"^AMPL de 9082|9082", "Batería 9082 → F013"),
    (r"121272", "121272 → si es MC3: DESM 121272 + MONT 121295"),
    (r"es un kit", "Kit en el parte"),
    (r"misma referencia (\S+): si es", "Misma referencia: SUST, no MONT + DESM"),
    (r"solo codifica el DESM", "Sustitución: falta MONT del nuevo"),
    (r"solo codifica el MONT", "Sustitución: falta DESM/SUST"),
    (r"sustituye un dispositivo y no está", "Sustitución sin codificar"),
    (r"ZeroVision / la cánula", "ZV/cánula sin codificar"),
    (r"fuente o batería de la central", "Fuente/batería central sin codificar"),
    (r"Cambia la SIM y no la codifica", "SIM sin codificar (MONT)"),
    (r"2500/2501", "Causa 2500/2501 prohibida"),
    (r"Bloqueo GSM: falta indicar", "Bloqueo GSM: indicar en observaciones si se conectó a internet"),
    (r"no codifica la REUB", "Falta REUB"),
    (r"desmonta o elimina dispositivos", "Desmontaje sin codificar"),
    (r"quita (\d+) magnéticos y codifica (\d+)", r"Quita \1 MG, codifica \2"),
    (r"DESM que no se explica", "DESM sin explicar"),
    (r"Amplía mando", "Mando ampliado sin AMPL"),
    (r"Amplía llave", "Llave ampliada: AMPL"),
    (r"Pilas codificadas como AMPL", "Pilas en AMPL → SUST"),
    (r"pilas (\S+)×\S+ para .* duplicadas", r"Pilas \1 duplicadas"),
    (r"perimetral YP", "Pilas del YP (7006) sin codificar"),
    (r"cambia pilas y no hay ninguna", "Pilas sin codificar"),
    (r"comunicaciones", "Comunicaciones: no consta revisión"),
    (r"sin observaciones", "Parte sin observaciones"),
    (r"nada codificado", "Sin codificar"),
]


def corto(texto):
    for patron, frase in CORTO:
        m = re.search(patron, texto)
        if m:
            return m.expand(frase) if "\\" in frase else frase
    return texto


def _pct(a, b):
    return f"{round(100 * a / b)} %" if b else "-"


def correo_html_corto(fecha, tecnicos, finalizados=None):
    """tecnicos: lista de (nombre, matricula, [(numero, [hallazgos])]). Una línea por mantenimiento.
    finalizados: {matricula: partes FINL del dia} del equipo, para el porcentaje de partes mal codificados."""
    n_mant = sum(len(ms) for _, _, ms in tecnicos)
    fin = finalizados or {}
    n_fin = sum(fin.values())
    resumen = (f'<p>Tu equipo finalizó <b>{n_fin}</b> mantenimientos y <b>{n_mant}</b> tienen la codificación mal: '
               f'<b>{_pct(n_mant, n_fin)}</b> de mala ejecución ({len(fin)} técnicos, media de '
               f'{n_mant / len(fin):.1f} partes mal por técnico).</p>' if n_fin else "")
    bloques = ""
    for nombre, mat, ms in sorted(tecnicos, key=lambda t: -len(t[2])):
        lineas = "".join(f'<li style="margin:2px 0"><b>{_e(num)}</b> · {_e(" · ".join(dict.fromkeys(corto(h["texto"]) for h in hall)))}</li>'
                         for num, hall in ms)
        cuenta = f"{len(ms)} de {fin[mat]} ({_pct(len(ms), fin[mat])})" if fin.get(mat) else str(len(ms))
        bloques += (f'<p style="margin:14px 0 4px"><b>{_e(nombre)}</b> ({_e(mat)}) — {cuenta}</p>'
                    f'<ul style="margin:0;padding-left:18px">{lineas}</ul>')
    return f"""<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:680px;line-height:1.45">
<p>Hola,</p>
<p>Partes del <b>{_e(fecha)}</b> con la codificación mal (<b>{n_mant}</b>). Avisa a cada técnico para que lo corrija:</p>
{resumen}{bloques}
<p>Gustavo Perez<br>Aurum BC Security SL</p></div>"""
