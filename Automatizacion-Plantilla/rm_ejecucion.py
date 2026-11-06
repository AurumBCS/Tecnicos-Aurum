"""
PROTOTIPO: lo que el tecnico hizo mal en un mantenimiento cerrado y que puede acabar en RM (mantenimiento repetido).

Usa las fichas que cod_revision.py ya leyo en Oracle (COD_REVISION_DIR/fichas_<fecha>_todos.json): no lee nada mas.
Las reglas salen de lo que fue ensenando Gustavo revisando RMs ("Correo Recuentos/rm-aprendizaje.md"), de los
manuales y comunicados de Verisure y de rm_reglas.py / rm_sugerencias.py. Solo marca lo que se ve en la ficha sin
criterio humano: lo que pedia el aviso o el texto y no consta hecho (ni en observaciones ni en codificaciones).
Los errores de codificacion van en el otro correo (cod_reglas.py), no aqui.

revisar(ficha) -> lista de {"tipo", "texto"} (vacia si no se ve nada)
"""

import re
from datetime import date

from cod_reglas import PACK_4PRO, PILAS, SIMS, _cod_texto, _lineas, _observaciones, no_revisable
from rm_reglas import _n, _panel
from rm_sugerencias import FOTOS, MAGNETICOS, PERIMETRALES, _cuenta, _fecha, _meses, _visitas

# Tipos en los que no se mira la ejecucion (instalaciones nuevas, bajas, remotos, documentacion)
TIPOS_FUERA = re.compile(r"desmontaje|anp remoto|anp/amp|documentacion|nueva instalacion|(?<!des)montaje de alarma|upgrade")
ZONA = re.compile(r"\b([A-Z]{2}\d{2}|B3\d{2})\b")
# pila que tiene que aparecer, cuando no hay duda (panel, prefijo de zona)
PILA_ZONA = {("Fast", "YP"): "7006", ("Fast", "MG"): "7002", ("Fast", "SR"): "7002", ("Fast", "B3"): "7002",
             ("Moonshot", "MG"): "205036", ("Moonshot", "SR"): "205036", ("Moonshot", "MR"): "205036"}
# baterias / cable de la central
BATERIA_CENTRAL = {"F013", "205086", "205106", "153202", "153203", "153181", "F055"}
# lo que el tecnico escribe cuando deja algo sin hacer
PENDIENTE = re.compile(r"queda(n)? pendiente|pendiente de|se deja(n)? (para|pendiente|sin)|para otro (dia|momento)|otro dia"
                       r"|volver a pasar|se volvera|hay que volver|no da tiempo|sin material|falta(n)? (de )?material"
                       r"|no (se )?(puede|pudo|pude|he podido|ha podido) (revisar|terminar|acabar|realizar|cambiar|sustituir|montar|instalar)"
                       r"|cerrajero|no llevo|no tengo (el|la|los|las)? ?(material|repuesto|sim|pila|bateri)")


def _equipo(z):
    return z[:2]


def _zonas_aviso(pet_original):
    """Zonas citadas en el aviso con su motivo: pila (bateria baja) o supervision. Devuelve {zona: motivo}."""
    out = {}
    for m in re.finditer(r"(bater\w* baja|pilas? baja|fallo de supervisi\w*)[^.#]{0,40}?\b(?:zona |zonas )?([A-Z]{2}\d{2}|B3\d{2})\b",
                         pet_original, re.I):
        out.setdefault(m.group(2).upper(), "pila" if re.match(r"bat|pil", m.group(1), re.I) else "supervision")
    return out


def _pilas_en(lin, zona, ficha_cod):
    """Hay linea de pila en esa zona (las SR/MG del mismo numero son el mismo aparato)."""
    mismas = {zona, "MG" + zona[2:], "SR" + zona[2:]} if zona[:2] in ("MG", "SR") else {zona}
    return any((c.get("ZONA RESOLUCION") or "").strip().upper() in mismas and (c.get("ID ITEM") or "").strip() in PILAS
               for c in ficha_cod)


def revisar(ficha):
    if (ficha.get("estado") or "").upper() != "FINL" or no_revisable(ficha):
        return []
    tipo = _n(ficha.get("tipo"))
    if TIPOS_FUERA.search(tipo):
        return []
    cods = ficha.get("codificaciones") or []
    if any((c.get("RESOLUCION") or "").upper() == "ERRO" for c in cods):
        return []
    obs_original = _observaciones(ficha)
    if not obs_original and cods and not any((c.get("ID ITEM") or "").strip() for c in cods):
        return []      # cerrado con soporte
    obs = _n(obs_original)
    pet_original = (ficha.get("texto_actividad") or "").split("****")[0]
    pet = _n(pet_original)
    panel = _panel(ficha)
    lin = _lineas(ficha)
    items = {l["item"] for l in lin}
    disp = [l for l in lin if l["item"] not in PILAS and l["item"] not in SIMS]
    cambia_disp = [l for l in disp if l["res"] in ("SUST", "MONT", "AMPL", "MONU") and l["item"] not in BATERIA_CENTRAL]
    actua_disp = cambia_disp + [l for l in disp if l["res"] in ("DESM", "DESU", "REUB")]
    a4 = [l for l in lin if (l["res"] == "AMPL" and PACK_4PRO.match(l["item"])) or l["item"] == "F049"]
    hay_reub = any(l["res"].startswith("REUB") for l in lin) or "reubic" in obs
    sustituye_obs = bool(re.search(r"sustitu\w* (?!(las |de )?(pila|bateri))|se cambia (el |la )?(detector|magnetico|sirena|foto|teclado|tag|dispositivo|perimetral|humo|central)", obs))
    n_pilas = sum(1 for l in lin if l["item"] in PILAS and l["res"] == "SUST")   # las AMPL de pilas son de lo ampliado
    hoy = _fecha(ficha.get("cita")) or date.today()
    hist = ficha.get("historico") or []
    visitas = [h for h in _visitas(hist) if (_fecha(h.get("apertura")) or date.min) < hoy]
    if lin and all(l["res"] in ("DESM", "DESU") for l in lin):
        return []      # desmontaje (p. ej. por traslado) aunque el tipo diga otra cosa
    h = []

    def mal(t, texto):
        h.append({"tipo": t, "texto": texto})

    # ── 1. pila baja o supervision de una zona del aviso ──
    for z, motivo in _zonas_aviso(pet_original).items():
        ref = PILA_ZONA.get((panel, _equipo(z)))
        en_zona = _pilas_en(lin, z, cods)
        tocado = en_zona or hay_reub or any((c.get("ZONA RESOLUCION") or "").strip().upper() == z for c in cods) \
            or re.search(rf"\b{z.lower()}\b", obs)
        if motivo == "pila":
            if ref and ref not in items and not cambia_disp and not sustituye_obs:
                mal("aviso", f"El aviso era pila baja de {z} y no hay ninguna pila {ref} codificada: "
                             "no consta que se cambiaran las pilas de ese dispositivo.")
            elif not n_pilas and not cambia_disp and not tocado and not sustituye_obs:
                mal("aviso", f"El aviso era pila baja de {z} y no consta ni cambio de pilas ni sustitución del dispositivo.")
        # el mismo dispositivo ya fallo antes por pilas o supervision: tocaba sustituirlo o reubicarlo
        mismas = {z, "MG" + z[2:], "SR" + z[2:]} if z[:2] in ("MG", "SR") else {z}
        previas = [v for v in visitas if any(re.search(rf"\b{a}\b", v.get("texto") or "", re.I) for a in mismas)
                   and re.search(r"pila|bateri|supervis", _n(v.get("razon")) + " " + _n(v.get("texto")))
                   and (hoy - (_fecha(v.get("apertura")) or hoy)).days <= 365]
        if previas and not cambia_disp and not hay_reub and not sustituye_obs:
            f_prev = previas[0].get("apertura")
            mal("reincidente", f"{z} ya tuvo un aviso de pilas o supervisión el {f_prev}: volver a cambiar pilas o revisar "
                               "no lo arregla, había que sustituir o reubicar el dispositivo.")
        if motivo == "supervision" and re.search(r"por (lejania|cercania)", pet) and not hay_reub and not cambia_disp and not sustituye_obs:
            mal("aviso", f"Fallo de supervisión de {z} por distancia (cercanía/lejanía) y no consta ni la reubicación ni la sustitución del dispositivo (lo mejor es cambiar el equipo).")

    if re.search(r"supervis", tipo + " " + pet) and not lin and not hay_reub and not sustituye_obs:
        mal("aviso", "Fallo de supervisión cerrado sin cambiar nada: si el fallo es claro hay que sustituir o reubicar el dispositivo.")

    # ── 2. lo que pedia el texto y no consta ──
    pet_sin_condicion = re.sub(r"de estar correcto,? sustituir \w+", "", pet)
    # "valorar sustitucion" deja la decision al tecnico: solo cuenta "sustituir el ..." sin condicion
    if re.search(r"(?<!valorar )\bsustituir (el |la )?(magnetico|detector|dispositivo|mg|sr|qr|yr|yp|sirena|teclado)", pet_sin_condicion) \
            and not actua_disp and not sustituye_obs:
        mal("texto", "El texto pedía sustituir el dispositivo y no consta sustituido.")
    # "valorar reubicar, sustituir o cambiar pilas" es una opcion, no una orden: solo cuenta si se manda reubicar
    manda_reub = re.search(r"obligatorio reubicar|(?<!valorar )(?<!o )\breubicar\b(?! o )", pet) and not re.search(r"valorar reubicar", pet) \
        or "reubicacion" in tipo
    if manda_reub and not hay_reub and not cambia_disp and not sustituye_obs \
            and not re.search(r"cliente no (quiere|desea|acepta)|no se puede reubicar|se coloca|se instala|se monta", obs):
        mal("texto", "El texto pedía reubicar y no consta (si el cliente no quiere, hay que ponerlo en el parte).")
    if re.search(r"cambiar (la )?sim", pet) and not items & SIMS and not a4 and not re.search(r"\bsim\b|4 ?pro|fast ?4", obs):
        mal("texto", "El texto pedía cambiar la SIM de operador y no consta: la SIM vieja y la nueva son referencias distintas, van codificadas las dos: DESM de la SIM vieja y MONT de la nueva.")

    # ── 3. pilas de toda la instalacion ──
    ult_pilas = None
    for v in visitas:
        t = _n(v.get("texto"))
        if re.search(r"\bpilas?\b|bateri", t + " " + _n(v.get("razon"))) and re.search(r"camb|sustitu|sust\b", t):
            fv = _fecha(v.get("cierre")) or _fecha(v.get("apertura"))
            if fv and (not ult_pilas or fv > ult_pilas):
                ult_pilas = fv
    # sin cambio de pilas en el historico solo vale la fecha de instalacion si el historico llega hasta ella
    # (Oracle no da todo: en instalaciones antiguas solo trae los ultimos 1-3 anos)
    f_inst = _fecha(ficha.get("fecha_instalacion"))
    f_hist = [x for x in (_fecha(v.get("apertura")) for v in hist) if x]
    cubre = f_inst and len(hist) < 15 and (not f_hist or (min(f_hist) - f_inst).days <= 120)
    base = ult_pilas or (f_inst if cubre else None)
    if base and "campana" not in tipo:
        m = _meses(base, hoy) if (hoy - base).days > 365 or _meses(base, hoy) < 12 else 11
        zonas = ficha.get("zonas") or []
        con_pilas = [z.get("ID") for z in zonas if (z.get("ID") or "")[:2] in set(FOTOS + MAGNETICOS + PERIMETRALES + ("ZR", "TI", "FR", "FG", "B3", "VV"))]
        n_disp = len(con_pilas)
        cuando = f"último cambio de pilas el {base.strftime('%d/%m/%Y')}" if ult_pilas else f"no consta cambio de pilas desde la instalación ({base.strftime('%m/%Y')})"
        pequena = _cuenta(zonas, FOTOS) <= 4 and _cuenta(zonas, MAGNETICOS) <= 6 and _cuenta(zonas, PERIMETRALES) <= 2
        # aunque el parte diga que las cambio, si no estan codificadas puede que no lo hiciera (Gustavo, 06/11)
        dice0 = " El parte dice que las cambió, pero no hay ninguna codificada." if re.search(r"pilas", obs) else ""
        if m >= 12 and n_pilas == 0:
            mal("pilas", f"Más de 1 año sin cambiar pilas ({cuando}) y no hay ningún cambio de pilas codificado.{dice0} Tocaba cambiarlas"
                         + (" todas." if pequena else " (como mínimo teclado de entrada, sirena, foto de entrada y MG de la entrada)."))
        elif m >= 12 and pequena and n_disp >= 4 and n_pilas < n_disp / 2:
            dice = (" El parte dice que a todos, pero no están codificadas." if re.search(r"pilas? (a|en) tod|todas las pilas", obs)
                    else " Las que constan son las de la cerradura, que no está entre ellos." if re.search(r"cerradura|smart ?lock", obs)
                    and not re.search(r"pilas? (a|en) tod", obs) else "")
            mal("pilas", f"Más de 1 año sin cambiar pilas ({cuando}): en una instalación pequeña se cambian todas. Tiene {n_disp} "
                         f"dispositivos con pilas ({', '.join(con_pilas)}) y solo cambió baterías a {n_pilas} de {n_disp}.{dice}")
        elif 6 <= m < 12 and n_pilas == 0 and re.search(r"pila|bateri|supervis", tipo + " " + pet):
            mal("pilas", f"Aviso de pilas o supervisión con {cuando} ({m} meses) y no cambió ninguna pila: como mínimo "
                         "teclado o tag reader, sirena y MG1.")

    # ── 4. comunicaciones ──
    gsm = "bloqueos gsm" in tipo or "cobertura" in tipo
    pide_com = gsm or (re.search(r"missing test|no transmite|no envia|fallo de comunicacion", pet) and not re.search(r"\bddi\b|sentinel|imagen|video", pet))
    revisa_com = re.search(r"cobertura|\bsim\b|router|wi-?fi|internet|operador|antena|ethernet|cable de red|transmi|senal|3g|4g|modulo", obs)
    if pide_com and not revisa_com and not items & SIMS and not a4 and not gsm:
        # (el bloqueo GSM sin internet ya lo avisa el correo de codificacion)
        mal("comunicaciones", "Aviso de comunicaciones (missing test / no transmite) y no consta revisión de SIM, cobertura ni conexión a internet.")
    if panel == "Fast" and "vf2" in _n(ficha.get("version_panel")) and ("bloqueos gsm" in tipo or re.search(r"fallo (de )?(la )?central", pet)) \
            and not a4 and not items & SIMS and not re.search(r"\bsim\b|4 ?pro|fast ?4", obs):
        mal("comunicaciones", "Fast 2 con bloqueo GSM o fallo de central: no cambió la SIM ni la pasó a 4PRO.")

    # ── 5. cambio a 4PRO: batería nueva del panel (comunicado 05/11) ──
    if a4 and "F013" not in items and not re.search(r"bateri", obs):
        mal("4PRO", "Pasa a 4PRO y no consta la batería nueva del panel: hay que pedir la F013 nueva y codificarla como SUST. Es uno de los 3 motivos de RM de 4PRO.")

    # ── 6. batería de la central ──
    if re.search(r"bateria (de la |del )?(central|panel|equipo)|bateria se desconecta|desconexion de (la )?bateria", pet + " " + tipo) \
            and not items & BATERIA_CENTRAL and not re.search(r"bateria (de la |del )?(central|panel)|central", obs):
        mal("aviso", "El aviso era la batería de la central y no consta que se cambiara (205086 Moonshot, F013 Fast-4PRO).")

    # ── 7. cámaras ──
    if re.search(r"camara|\barlo\b|\bhub\b|cloudcam", pet) and not re.search(r"\barlo\b|camara", tipo) \
            and not re.search(r"camara|\barlo\b|\bhub\b|cloud|video|imagen", obs) and not any(re.match(r"32\d{4}V?$", i) for i in items):
        mal("aviso", "El aviso hablaba de las cámaras y el parte no dice nada de ellas: revisar todo el sistema, cámaras incluidas.")

    # ── 8. deja algo pendiente o anula ──
    if PENDIENTE.search(obs):
        frase = PENDIENTE.search(obs).group(0)
        mal("pendiente", f"Deja algo sin resolver (\"{frase}\"): el cliente volverá a llamar y cuenta como RM.")
    if re.search(r"\banul", obs) and not cambia_disp and not re.search(r"desanul|se quita (la )?anulacion", obs):
        mal("aviso", "Anula una zona en vez de sustituir el dispositivo que falla.")

    # ── 9. heavy repeater ──
    if "heavy repeater" in pet and not re.search(r"soporte|66043", obs):
        mal("aviso", "Heavy Repeater: no consta la llamada a Soporte Técnico (66043) antes de validar.")

    vistos, out = set(), []
    for x in h:
        if x["texto"] not in vistos:
            vistos.add(x["texto"])
            out.append(x)
    return out


# ───────────────────────── correos ─────────────────────────

CORTO = [
    (r"pila baja de (\S+) y no hay ninguna pila (\S+)", r"Pila baja \1: no cambió la \2"),
    (r"pila baja de (\S+) y no consta", r"Pila baja \1: no consta cambio"),
    (r"^(\S+) ya tuvo un aviso", r"\1 reincidente: tocaba sustituir o reubicar"),
    (r"supervisión de (\S+) por distancia", r"Supervisión \1 por distancia: ni sustituido ni reubicado"),
    (r"Fallo de supervisión cerrado sin cambiar", "Supervisión cerrada sin cambiar nada"),
    (r"pedía sustituir", "Texto pedía sustituir: no consta"),
    (r"pedía reubicar", "Texto pedía reubicar: no consta"),
    (r"cambiar la SIM", "Texto pedía cambiar SIM: no consta"),
    (r"no hay ningún cambio de pilas codificado", "Más de 1 año sin pilas: no cambió ninguna"),
    (r"Tiene (\d+) dispositivos con pilas .* solo cambió baterías a (\d+) de", r"Más de 1 año sin pilas: solo cambió baterías a \2 de \1 dispositivos"),
    (r"Aviso de pilas o supervisión con", "Pilas de 6-12 meses: ni el mínimo"),
    (r"Aviso de comunicaciones", "Comunicaciones: no consta revisión"),
    (r"Fast 2 con bloqueo", "Fast 2 con bloqueo: ni SIM ni 4PRO"),
    (r"batería nueva del panel", "4PRO sin batería nueva (SUST F013)"),
    (r"batería de la central y no consta", "Batería de central: no consta cambio"),
    (r"cámaras", "Cámaras del aviso sin revisar"),
    (r"Deja algo sin resolver", "Deja algo pendiente"),
    (r"Anula una zona", "Anula zona en vez de sustituir"),
    (r"Heavy Repeater", "Heavy Repeater: sin llamar a Soporte"),
]

CONSEJOS = {
    "aviso": "Resolver siempre el motivo del aviso en la zona que dice el texto, y dejarlo escrito en el parte.",
    "reincidente": "Si el mismo dispositivo ya falló por pilas o supervisión, no se vuelven a cambiar pilas: se sustituye o se reubica.",
    "texto": "Hacer todo lo que pide el texto del mantenimiento; si algo no se puede (el cliente no quiere…), ponerlo en el parte.",
    "pilas": "Más de 1 año sin cambiar pilas: todas (instalación pequeña) o como mínimo teclado, sirena, foto y MG de la entrada. "
             "Entre 6 meses y 1 año: teclado o tag reader, sirena y MG1.",
    "comunicaciones": "En avisos de comunicaciones: probar SIM de otros operadores, revisar cobertura y dejar la central conectada a internet.",
    "4PRO": "Al pasar a 4PRO: batería nueva F013 (SUST), panel anclado y atornillado en negocios, y comprobar con el cliente mandos y llaves.",
    "pendiente": "No cerrar con cosas pendientes: lo que queda sin hacer vuelve como mantenimiento repetido.",
}


def corto(texto):
    for patron, frase in CORTO:
        m = re.search(patron, texto)
        if m:
            return m.expand(frase) if "\\" in frase else frase
    return texto


def _e(s):
    import html
    return html.escape(str(s or ""))


def _pct(a, b):
    return f"{round(100 * a / b)} %" if b else "-"


def _consejos(hallazgos):
    from collections import Counter
    tipos = Counter(x["tipo"] for x in hallazgos)
    li = "".join(f'<li style="margin:3px 0">{_e(CONSEJOS[t])}</li>' for t, _ in tipos.most_common() if t in CONSEJOS)
    return f'<p style="margin:18px 0 4px"><b>Para que no se repitan</b></p><ul style="margin:0;padding-left:20px">{li}</ul>' if li else ""


def correo_html_corto(fecha, tecnicos, finalizados=None):
    """Correo al JE. tecnicos: [(nombre, matricula, [(numero, tipo, [hallazgos])])]; finalizados: {matricula: FINL}."""
    n_mant = sum(len(ms) for _, _, ms in tecnicos)
    fin = finalizados or {}
    n_fin = sum(fin.values())
    resumen = (f'<p>Tu equipo finalizó <b>{n_fin}</b> mantenimientos y en <b>{n_mant}</b> ({_pct(n_mant, n_fin)}) '
               f'quedó algo sin hacer que puede hacer que se repitan.</p>' if n_fin else "")
    bloques = ""
    for nombre, mat, ms in sorted(tecnicos, key=lambda t: -len(t[2])):
        lineas = "".join(f'<li style="margin:2px 0"><b>{_e(num)}</b> · {_e(" · ".join(dict.fromkeys(corto(x["texto"]) for x in hall)))}</li>'
                         for num, _, hall in ms)
        cuenta = f"{len(ms)} de {fin[mat]}" if fin.get(mat) else str(len(ms))
        bloques += (f'<p style="margin:14px 0 4px"><b>{_e(nombre)}</b> ({_e(mat)}) — {cuenta}</p>'
                    f'<ul style="margin:0;padding-left:18px">{lineas}</ul>')
    todos = [x for _, _, ms in tecnicos for _, _, hall in ms for x in hall]
    return f"""<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:680px;line-height:1.45">
<p>Hola,</p>
<p>Mantenimientos del <b>{_e(fecha)}</b> con riesgo de repetirse (RM) por algo que el técnico no hizo (<b>{n_mant}</b>).
Repásalos con cada técnico; el detalle de cada uno va en el Excel:</p>
{resumen}{bloques}{_consejos(todos)}
<p>Gustavo Perez<br>Aurum BC Security SL</p></div>"""


def correo_html_tecnico(fecha, nombre, partes, n_fin):
    """Correo a un tecnico (equipo de Nicola). partes: [(numero, tipo, [hallazgos])]."""
    n = len(partes)
    if n_fin == 1:
        frase = f'En el mantenimiento que finalizaste el <b>{_e(fecha)}</b> quedó algo sin hacer que puede hacer que se repita:'
    else:
        frase = (f'De los <b>{n_fin}</b> mantenimientos que finalizaste el <b>{_e(fecha)}</b>, en <b>{n}</b> quedó algo sin hacer '
                 f'que puede hacer que se {"repita" if n == 1 else "repitan"} (RM):')
    bloques = ""
    for num, tipo, hall in partes:
        lineas = "".join(f'<li style="margin:2px 0">{_e(t)}</li>' for t in dict.fromkeys(x["texto"] for x in hall))
        bloques += (f'<p style="margin:14px 0 4px"><b>{_e(num)}</b> · {_e(tipo or "")}</p>'
                    f'<ul style="margin:0;padding-left:18px">{lineas}</ul>')
    todos = [x for _, _, hall in partes for x in hall]
    return f"""<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:680px;line-height:1.45">
<p>Hola {_e(nombre.split()[0])},</p>
<p>{frase}</p>
{bloques}{_consejos(todos)}
<p>Si ya lo resolviste y no está en el parte, escríbelo siempre en las observaciones.</p>
<p>Gustavo Perez<br>Aurum BC Security SL</p></div>"""


def _excel(filas, destino):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Mantenimientos"
    ws.append(["Técnico", "Matrícula", "Mantenimiento", "Tipo", "Qué faltó", "Qué pedía el aviso", "Qué escribió el técnico", "Qué codificó"])
    for f in filas:
        ws.append(f)
    for c in ws[1]:
        c.font = Font(bold=True)
    for col, ancho in zip("ABCDEFGH", (26, 11, 13, 22, 60, 60, 60, 45)):
        ws.column_dimensions[col].width = ancho
    for fila in ws.iter_rows(min_row=2):
        for c in fila:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(destino)
    return destino


# ───────────────────────── barrido diario ─────────────────────────

import json
import os
from pathlib import Path

CARPETA = Path(os.environ.get("COD_REVISION_DIR", "/Users/gustavoperez/Correo Recuentos/cod_revision"))
REGISTRO = CARPETA / "rm_enviados.json"
JE_POR_TECNICO = "302154"   # Nicola Morsa: un correo a cada tecnico, sin Excel, con Nicola en copia


def _registro():
    try:
        return json.loads(REGISTRO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def preparar(fecha_iso, datos, jer):
    """Agrupa los hallazgos por JE -> (nombre, matricula) y cuenta los FINL revisables de cada tecnico."""
    from collections import defaultdict
    por_je = defaultdict(lambda: defaultdict(list))
    fin_je = defaultdict(lambda: defaultdict(int))
    total = finl = 0
    for d in {d["numero"]: d for d in datos}.values():   # un parte puede salir en dos grupos de la ruta
        f = d.get("ficha") or {}
        if (f.get("estado") or "").upper() != "FINL" or no_revisable(f) or TIPOS_FUERA.search(_n(f.get("tipo"))):
            continue
        finl += 1
        mat = (d.get("tecnico") or f.get("tecnico") or "").upper()
        p = jer.get(mat) or jer.get(re.sub(r"^[A-Z]{2}(?=\d{6}$)", "", mat)) or {}
        je = (p.get("JE") or "").strip().upper() or "SIN JE"
        m = (p.get("Matricula") or mat).strip().upper()
        fin_je[je][m] += 1
        h = revisar(f)
        if h:
            total += 1
            por_je[je][(p.get("Nombre") or mat, m)].append((d["numero"], f, h))
    return por_je, fin_je, total, finl


def revisar_y_mandar(fecha_iso, datos, modo="enviar", jer=None, salida_html=None):
    """Mismo esquema que cod_revision.revisar_y_mandar, con su propio registro (rm_enviados.json).
    salida_html: carpeta donde dejar los correos en HTML (vista previa) en vez de mandarlos."""
    import base64
    from datetime import datetime
    from cod_revision import _mandar_tecnicos
    from comun_ofs import enviar_aviso
    from ov_conteos import _jerarquia, _mandar

    if modo == "enviar" and fecha_iso in _registro():
        print(f"[rm] el {fecha_iso} ya se envio ({_registro()[fecha_iso]})")
        return
    jer = jer if jer is not None else _jerarquia()
    por_je, fin_je, total, finl = preparar(fecha_iso, datos, jer)
    fecha_txt = "/".join(reversed(fecha_iso.split("-")))
    tecs_tf, fin_tf = por_je.pop(JE_POR_TECNICO, {}), fin_je.pop(JE_POR_TECNICO, {})
    jefes, tecnicos, resumen, errores = [], [], [], []
    for (nombre, mat), ms in tecs_tf.items():
        html = correo_html_tecnico(fecha_txt, nombre, [(num, f.get("tipo"), h) for num, f, h in ms], fin_tf.get(mat, len(ms)))
        tecnicos.append({"mat": mat, "asunto": f"Tus mantenimientos del {fecha_txt} que se pueden repetir ({len(ms)})", "html": html,
                         "texto": f"Tus mantenimientos del {fecha_txt} que se pueden repetir: {len(ms)}."})
    for je, tecs in por_je.items():
        if je == "SIN JE":
            resumen.append(f"Sin jefe de equipo en el cuadrante: {', '.join(m for _, m in tecs)}")
            continue
        html = correo_html_corto(fecha_txt, [(n, m, [(num, f.get("tipo"), h) for num, f, h in ms]) for (n, m), ms in tecs.items()],
                                 fin_je[je])
        filas = [[n, m, num, f.get("tipo"), "\n".join(dict.fromkeys(x["texto"] for x in h)),
                  (f.get("texto_actividad") or "").split("****")[0].strip()[:1500], _observaciones(f), _cod_texto(f)]
                 for (n, m), ms in tecs.items() for num, f, h in ms]
        archivo = f"RM {fecha_iso} JE {je}.xlsx"
        _excel(filas, CARPETA / archivo)
        n_p = sum(len(ms) for ms in tecs.values())
        jefes.append({"codigo": je, "jde": je, "asunto": f"Mantenimientos del {fecha_txt} que se pueden repetir ({n_p})",
                      "html": html, "texto": f"Mantenimientos del {fecha_txt} que se pueden repetir: {n_p}.",
                      "archivo": archivo, "xlsx_b64": base64.b64encode((CARPETA / archivo).read_bytes()).decode()})
        resumen.append(f"JE {je}: {n_p} de {sum(fin_je[je].values())} mantenimientos con riesgo de RM, {len(tecs)} técnicos")
    if salida_html:
        Path(salida_html).mkdir(parents=True, exist_ok=True)
        for j in jefes:
            (Path(salida_html) / f"rm_JE_{j['jde']}.html").write_text(j["html"], encoding="utf-8")
        for t in tecnicos:
            (Path(salida_html) / f"rm_tecnico_{t['mat']}.html").write_text(t["html"], encoding="utf-8")
        print(f"[rm] {fecha_txt}: {total} de {finl} con riesgo ({_pct(total, finl)}); vista previa en {salida_html}")
        print("\n".join(resumen))
        return
    if jefes:
        res = _mandar(jefes, modo)
        ok = sum(1 for r in res.get("resultado", []) if r.get("ok"))
        errores = [f"JE {r.get('jde')}: {r.get('error')}" for r in res.get("resultado", []) if not r.get("ok")]
        resumen.insert(0, f"{fecha_txt}: {finl} finalizados, {total} con riesgo de RM ({_pct(total, finl)}). "
                          f"Modo {res.get('modo')}: {ok}/{len(jefes)} correos ok.")
    if tecnicos:
        ok_t = 0
        try:
            res = _mandar_tecnicos(tecnicos, modo)
            ok_t = sum(1 for r in res.get("resultado", []) if r.get("ok"))
            errores += [f"Técnico {r.get('mat')}: {r.get('error')}" for r in res.get("resultado", []) if not r.get("ok")]
        except Exception as e:
            errores.append(f"Correos a técnicos de JE {JE_POR_TECNICO}: {e}")
        resumen.append(f"JE {JE_POR_TECNICO} (a cada técnico): {sum(len(ms) for ms in tecs_tf.values())} de {sum(fin_tf.values())}, "
                       f"{ok_t}/{len(tecnicos)} correos ok")
    if modo == "enviar" and (jefes or tecnicos):
        reg = _registro()
        reg[fecha_iso] = datetime.now().strftime("%Y-%m-%d %H:%M")
        REGISTRO.write_text(json.dumps(reg, indent=1), encoding="utf-8")
    if modo != "prueba":
        enviar_aviso(("⚠️" if errores else "✅") + f" Riesgo de RM en los mantenimientos del {fecha_txt}",
                     "\n".join(resumen + ([""] + ["Errores:"] + errores if errores else [])))
    print("\n".join(resumen + errores))


if __name__ == "__main__":
    # Solo usa las fichas ya leidas por cod_revision.py: no abre Oracle
    import argparse
    from cod_revision import dia_anterior
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha")
    ap.add_argument("--modo", choices=["enviar", "prueba", "borradores"], default="prueba")
    ap.add_argument("--vista", help="carpeta para dejar los correos en HTML sin mandar nada")
    a = ap.parse_args()
    fecha = a.fecha or dia_anterior().isoformat()
    datos = json.loads((CARPETA / f"fichas_{fecha}_todos.json").read_text(encoding="utf-8"))
    revisar_y_mandar(fecha, datos, a.modo, salida_html=a.vista)
