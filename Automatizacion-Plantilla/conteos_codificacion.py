"""
Fallos de codificacion a partir de un conteo periodico de material (app OV,
Counts -> Ver/Meter Conteos). Reglas de Gustavo: "Correo Recuentos/conteos-reglas.md".

Cada linea del conteo: subinventario (<matricula> o <matricula>DF), item, descripcion,
contado, stock, transito, Dif. C. (= contado - stock), ajuste en euros.
  dif < 0 -> falta: lo gasto y no lo codifico
  dif > 0 -> sobra: codifico algo que no puso, o con otra referencia

analizar(lineas, matricula) -> lista de hallazgos {tipo, texto, unidades, euros}
en este orden: confusiones de familia, kits abiertos, defectuoso sin parcial,
material tipico sin codificar, resto que falta, resto que sobra.
"""

import re
from collections import defaultdict

# Familias que se confunden al codificar. La primera de cada grupo que ya no se envia va en VIEJAS.
FAMILIAS = [
    ("magnéticos Moonshot", ["121272", "121295"]),
    ("perimetrales Moonshot", ["120221", "120264"]),
    ("cánulas Zerovision", ["130958", "FOG001", "135104"]),
    ("sirenas Moonshot", ["131179", "131179IN"]),
    ("Orion", ["120213", "120213T"]),
    ("centrales Moonshot", ["182083", "182084"]),
    ("magnéticos Fast", ["F250SP", "F252SP"]),
    ("sirenas Fast", ["F500SP", "F505SP"]),
    ("cámaras Arlo", ["322050V", "322070V"]),
    ("paneles solares Arlo", ["325603", "326600", "327600"]),
    ("kits Moonshot", ["199005", "199013"]),
    ("llaves Moonshot", ["131347", "131348"] + [str(n) for n in range(131370, 131380)]),
    ("llaves Fast", ["F443", "F444", "F445", "F446", "F447", "F448", "F449"]),
]
VIEJAS = {"121272", "120221", "130958", "FOG001", "199005", "322030V", "322040V"}
# El almacen cambia la referencia al recibir el defectuoso: no es fallo del tecnico
RENOMBRA_ALMACEN = [("322050V", "322050"), ("340001V", "340004")]
KITS = {"199005", "199013"}
CONTENIDO_KIT = {"120213": 2, "131179": 1, "182084": 1, "121295": 1}

LLAVES = {r for _, g in FAMILIAS if _.startswith("llaves") for r in g}
MANDOS = {"280785": "Moonshot", "2409SP": "Fast2", "2410SP": "Fast2", "2411SP": "Fast4"}
CILINDROS = {"131560", "131561", "131562", "131563", "131564"}
SIN_CODIFICAR_TIPICO = {"120236": "porta pilas AA de los Aquila"}


def _num(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v)).replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _es_sim(item, desc):
    return bool(re.search(r"\bsim\b", desc or "", re.I))


def _es_pila(desc):
    return bool(re.search(r"batter|pila", desc or "", re.I)) and not re.search(r"holder|control panel|no battery", desc or "", re.I)


def analizar(lineas, matricula):
    """lineas: dicts con subinv, item, desc, contado, stock, dif, euros, coste."""
    mat = str(matricula).upper()
    bueno, df, desc, coste = defaultdict(float), defaultdict(float), {}, {}
    for l in lineas:
        it = str(l["item"]).strip().upper()
        desc[it] = l.get("desc") or ""
        d = _num(l.get("dif"))
        u = abs(_num(l.get("euros"))) / abs(d) if d else _num(l.get("coste"))
        if u:
            coste[it] = u
        sub = str(l.get("subinv") or "").upper()
        (df if sub.endswith("DF") and sub != mat else bueno)[it] += d

    hall = []

    def add(tipo, texto, unidades, refs, **extra):
        euros = round(sum(coste.get(r, 0) for r in refs) / max(len(refs), 1) * unidades, 2)
        hall.append(dict({"tipo": tipo, "texto": texto, "unidades": int(round(unidades)), "euros": euros,
                          "ref": refs[0], "desc": desc.get(refs[0], "")}, **extra))

    # 0. Renombrados del almacen al devolver defectuosos: se compensan y no cuentan
    for a, b in RENOMBRA_ALMACEN:
        for caja in (bueno, df):
            if caja[a] * caja[b] < 0:
                m = min(abs(caja[a]), abs(caja[b]))
                caja[a] += m if caja[a] < 0 else -m
                caja[b] += m if caja[b] < 0 else -m

    # 1. Defectuoso sin parcial: falta en bueno y sobra lo mismo en DF
    for it in list(df):
        if df[it] > 0 and bueno[it] < 0:
            m = min(df[it], -bueno[it])
            add("parcial", f"{it} ({desc.get(it, '')}): {int(m)} pasado(s) a defectuoso sin hacer el parcial", m, [it])
            df[it] -= m
            bueno[it] += m

    # 2. Kits abiertos: faltan kits y sobran sus piezas
    for kit in KITS:
        if bueno[kit] < 0:
            abiertos = min(-bueno[kit], min((bueno[p] // n for p, n in CONTENIDO_KIT.items() if bueno[p] > 0), default=0))
            if abiertos > 0:
                add("kit", f"Abrió {int(abiertos)} kit(s) {kit}: faltan los kits y sobran sus piezas sueltas "
                           "(2×120213, 131179, 182084, 121295)", abiertos, [kit])
                bueno[kit] += abiertos
                for p, n in CONTENIDO_KIT.items():
                    bueno[p] -= abiertos * n

    # 3. Confusiones de familia: una ref sobra y otra de la misma familia falta
    for nombre, grupo in FAMILIAS:
        sobran = sorted([r for r in grupo if bueno[r] > 0], key=lambda r: -bueno[r])
        faltan = sorted([r for r in grupo if bueno[r] < 0], key=lambda r: bueno[r])
        for s in sobran:
            for f in faltan:
                if bueno[s] <= 0 or bueno[f] >= 0:
                    continue
                m = min(bueno[s], -bueno[f])
                vieja = f" ({s} ya no se envía)" if s in VIEJAS else ""
                add("confusion", f"{nombre}: colocó {f} y codificó {s}{vieja} — {int(m)} ud.", m, [f],
                    fam=nombre, puso=f, codifico=s)
                bueno[s] -= m
                bueno[f] += m

    # 4. Referencias que ya no se envian con stock negativo (codificadas de mas)
    for r in sorted(VIEJAS):
        if bueno[r] > 0:
            add("vieja", f"{r} ({desc.get(r, '')}): codificada {int(bueno[r])} vez/veces y ya no se envía; "
                         "revisa qué referencia colocó", bueno[r], [r])
            bueno[r] = 0

    # 5. Lo que falta: material tipico sin codificar y resto
    f049 = bueno["F049"] < 0
    for it in sorted([i for i in bueno if bueno[i] < 0], key=lambda i: bueno[i] * coste.get(i, 0)):
        n = -bueno[it]
        d = desc.get(it, "")
        if it in LLAVES:
            cat = "llaves"
        elif it in MANDOS:
            cat, d = "mandos", f"Mando {MANDOS[it]}"
        elif it in CILINDROS:
            cat = "cilindros"
        elif _es_sim(it, d):
            cat = "sims"
        elif it in SIN_CODIFICAR_TIPICO:
            cat, d = "portapilas", SIN_CODIFICAR_TIPICO[it]
        elif it in ("F055", "F057") and f049:
            cat = "f049"
        elif _es_pila(d):
            cat = "pilas"
        else:
            cat = "resto"
        add("falta", f"{it} ({d}): faltan {int(n)}", n, [it], cat=cat)
        hall[-1]["desc"] = d

    # 6. Lo que sobra
    for it in sorted([i for i in bueno if bueno[i] > 0], key=lambda i: -bueno[i] * coste.get(i, 0)):
        add("sobra", f"{it} ({desc.get(it, '')}): sobran {int(bueno[it])} — codificado sin colocar o con otra referencia",
            bueno[it], [it])
    return hall


def leer_excel(ruta):
    """Lineas de un Excel descargado de Ver/Meter Conteos."""
    import openpyxl
    filas = list(openpyxl.load_workbook(ruta, read_only=True).active.iter_rows(values_only=True))
    cab = [str(c or "").strip() for c in filas[0]]
    i = {n: cab.index(n) for n in cab}
    out = []
    for r in filas[1:]:
        if not r or not r[i["Item"]]:
            continue
        out.append({"subinv": r[i["Subinv."]], "item": r[i["Item"]], "desc": r[i["Descripción Item"]],
                    "contado": r[i["Contado"]], "stock": r[i["Stock"]], "dif": r[i["Dif. C."]],
                    "euros": r[i["Ajuste"]], "coste": r[i.get("Coste Unidad", i["Ajuste"])]})
    return out


# ── Correo para el jefe de equipo: corto, lo importante; el detalle va en el Excel adjunto ──
def _e(t):
    import html
    return html.escape(str(t or ""))


def _eur(v):
    return f"{v:,.0f} €".replace(",", ".")


def _corto(h):
    d = re.sub(r"\s*\(.*?\)|no battery|\bEFM\b", "", h.get("desc") or "").strip()
    return f"{d or h['ref']} ×{h['unidades']}"


def _lista(hs, n=4):
    hs = sorted(hs, key=lambda h: -h["euros"])
    txt = ", ".join(_e(_corto(h)) for h in hs[:n])
    return txt + (f" y {len(hs) - n} más" if len(hs) > n else "")


def puntos(hallazgos):
    """Lo importante en frases cortas: [(titulo, detalle, euros)], de mas a menos euros."""
    por = lambda f: [h for h in hallazgos if f(h)]
    out = []
    conf = por(lambda h: h["tipo"] in ("confusion", "vieja"))
    if conf:
        grupos = {}
        for h in conf:
            if h["tipo"] == "vieja":
                grupos.setdefault((h["ref"], "?"), []).append(h)
            else:
                grupos.setdefault((h["codifico"], h["fam"]), []).append(h)
        frases = []
        for (cod, fam), hs in sorted(grupos.items(), key=lambda kv: -sum(h["euros"] for h in kv[1])):
            n = sum(h["unidades"] for h in hs)
            if fam == "?":
                frases.append(f"{cod} (ya no se envía) ×{n}")
            else:
                puso = "/".join(sorted({h["puso"] for h in hs}))
                frases.append(f"{cod} en vez de {puso} ×{n}")
        out.append(("Codifica una referencia por otra", ", ".join(frases[:5]) + (f" y {len(frases) - 5} más" if len(frases) > 5 else ""),
                    sum(h["euros"] for h in conf)))
    entrega = por(lambda h: h["tipo"] == "falta" and h.get("cat") in ("llaves", "mandos", "sims", "cilindros", "portapilas", "f049"))
    if entrega:
        tot = lambda c: sum(h["unidades"] for h in entrega if h.get("cat") == c)
        partes = [f"{tot(c)} {t}" for c, t in (("llaves", "llaves"), ("mandos", "mandos"), ("sims", "SIMs"),
                                               ("cilindros", "cilindros"), ("portapilas", "porta pilas"), ("f049", "F055/F057")) if tot(c)]
        out.append(("No codifica lo que entrega en montajes y ANP", ", ".join(partes), sum(h["euros"] for h in entrega)))
    pilas = por(lambda h: h["tipo"] == "falta" and h.get("cat") == "pilas")
    if pilas:
        refs = ", ".join(f"{h['ref']} ×{h['unidades']}" for h in sorted(pilas, key=lambda h: -h["unidades"]))
        out.append(("Cambia pilas sin codificarlas (SUST en su zona)", _e(refs), sum(h["euros"] for h in pilas)))
    resto = por(lambda h: h["tipo"] == "falta" and h.get("cat") == "resto")
    if resto:
        out.append(("Le faltan equipos que no ha codificado", _lista(resto), sum(h["euros"] for h in resto)))
    kits = por(lambda h: h["tipo"] == "kit")
    if kits:
        out.append(("Abre kits y no lo codifica bien", _lista(kits), sum(h["euros"] for h in kits)))
    parcial = por(lambda h: h["tipo"] == "parcial")
    if parcial:
        out.append(("Pasa equipos a defectuoso sin hacer el parcial", _lista(parcial), sum(h["euros"] for h in parcial)))
    sobra = por(lambda h: h["tipo"] == "sobra")
    if sobra:
        out.append(("Le sobra material (codificado sin colocarlo)", _lista(sobra, 3), sum(h["euros"] for h in sobra)))
    return out


MEJORAS = {
    "Codifica una referencia por otra": "Codificar siempre la referencia que coloca, mirando la etiqueta del equipo, "
                                        "y no usar las que ya no se envían (121272, 120221, 199005, FOG001…).",
    "No codifica lo que entrega en montajes y ANP": "En montajes y ANP, codificar todas las llaves, mandos, SIMs y cilindros que entrega.",
    "Cambia pilas sin codificarlas (SUST en su zona)": "Cada cambio de pilas va como SUST en su zona y con su referencia.",
    "Le faltan equipos que no ha codificado": "Codificar todo lo que coloca o sustituye (SUST, AMPL, MONT) antes de cerrar el mantenimiento.",
    "Abre kits y no lo codifica bien": "Si abre un kit, codificar las piezas sueltas que usa; si lo instala entero, el kit.",
    "Pasa equipos a defectuoso sin hacer el parcial": "Si un equipo nuevo no funciona, hacer el parcial a defectuoso en Oracle antes de dejarlo en DF.",
    "Le sobra material (codificado sin colocarlo)": "Revisar antes de cerrar que lo codificado es lo que de verdad ha colocado.",
}


LIMITE_AJUSTE = 400   # euros: un conteo con ajuste neto por encima de +400 o por debajo de -400 esta mal


def fuera_de_limite(ajuste_neto):
    return abs(_num(ajuste_neto)) > LIMITE_AJUSTE


def correo_html(tecnico, cab, hallazgos):
    """cab: dict con codigo, fecha, ajuste_neto, lineas, lineas_dif."""
    pts = puntos(hallazgos)
    aviso = ""
    if fuera_de_limite(cab.get("ajuste_neto")):
        aviso = (f'<p style="background:#fdecea;border-left:4px solid #c62828;padding:10px 12px;color:#8e1c1c">'
                 f'<b>El conteo está mal:</b> el ajuste neto es de {_e(cab.get("ajuste_neto"))} y no puede pasar de '
                 f'±{LIMITE_AJUSTE} €. Hay que revisarlo con el técnico y corregirlo.</p>')
    mejoras = "".join(f'<li style="margin:4px 0">{_e(MEJORAS[t])}</li>' for t, _, _ in pts if t in MEJORAS)
    filas = "".join(
        f'<tr><td style="padding:8px 12px 8px 0;border-bottom:1px solid #eee;vertical-align:top;width:34%"><b>{_e(t)}</b></td>'
        f'<td style="padding:8px 12px 8px 0;border-bottom:1px solid #eee;vertical-align:top">{d}</td>'
        f'<td style="padding:8px 0;border-bottom:1px solid #eee;vertical-align:top;text-align:right;white-space:nowrap;color:#666">{_eur(e)}</td></tr>'
        for t, d, e in pts)
    return f"""<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;max-width:680px;line-height:1.45">
<p>Hola,</p>
{aviso}<p>En el conteo periódico de <b>{_e(tecnico)}</b> del {_e(cab.get('fecha'))} salen <b>{_e(cab.get('lineas_dif'))} de
{_e(cab.get('lineas'))} referencias con diferencia</b> (ajuste {_e(cab.get('ajuste_neto'))}). Esto es lo que tiene que corregir al codificar:</p>
<table style="border-collapse:collapse;width:100%;font-size:14px">{filas}</table>
<p style="margin-top:10px;color:#555">El detalle referencia por referencia va en el Excel adjunto.</p>
<p style="margin:18px 0 4px"><b>En qué mejorar</b></p>
<ul style="margin:0;padding-left:20px">{mejoras}</ul>
<p>Gustavo Perez<br>Aurum BC Security SL</p></div>"""


TIPOS_EXCEL = {"confusion": "Codifica una por otra", "vieja": "Referencia que ya no se envía", "kit": "Kit abierto",
               "parcial": "Defectuoso sin parcial", "falta": "Falta (sin codificar)", "sobra": "Sobra"}


def excel_detalle(hallazgos, destino):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Detalle"
    ws.append(["Qué pasa", "Referencia", "Descripción", "Unidades", "€", "Explicación"])
    for h in sorted(hallazgos, key=lambda h: (list(TIPOS_EXCEL).index(h["tipo"]), -h["euros"])):
        ws.append([TIPOS_EXCEL[h["tipo"]], h["ref"], h.get("desc", ""), h["unidades"], h["euros"], h["texto"]])
    for col, ancho in zip("ABCDEF", (26, 12, 40, 10, 10, 70)):
        ws.column_dimensions[col].width = ancho
    wb.save(destino)
    return destino
