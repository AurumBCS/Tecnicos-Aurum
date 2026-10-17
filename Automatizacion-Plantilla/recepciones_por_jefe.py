"""Material enviado por el almacen y sin recibir en la app, por jefe de equipo.

Entrada: Excel de la app OV -> Inventario Transacciones -> Recibir TOs (ordenes de
transferencia en "Recibo Pendiente") y el cuadrante. Lo usa ov_devoluciones.py (misma
entrada a la app, a las 11:00). Uso local:
  python recepciones_por_jefe.py <tos.xlsx|csv> <cuadrante.csv> <carpeta> [AAAA-MM-DD]

Reglas (acordadas con Gustavo, 2026-10-17):
  - Entran las ordenes con 3 dias o mas desde "Enviado" (antes el transporte puede no
    haber llegado). Mas de 7 dias = urgente.
  - Un correo por jefe con la lista de su equipo (solo jefes con algo pendiente).
  - El tecnico es "Entregar a" (matricula); si no esta en el cuadrante se busca por
    "Nombre Trabajador". Lo que no se encuentra va a "Fuera del control".
"""
import base64
import html as _html
import json
import os
import sys
import unicodedata
from datetime import date

import pandas as pd
from openpyxl import Workbook

from devoluciones_por_jefe import COLORES, _fecha, _fmt, _tabla, escribir, leer_cuadrante

MIN_DIAS, URGENTE_DIAS = 3, 7
URGENTE = f"Más de {URGENTE_DIAS} días sin recibir"
PENDIENTE = f"Entre {MIN_DIAS} y {URGENTE_DIAS} días sin recibir"
COLORES.update({URGENTE: "F8CBAD", PENDIENTE: "FFE699"})
NOTA = (f"Material enviado por el almacén y sin recibir en la app (Recibir TOs). Entran las órdenes con "
        f"{MIN_DIAS} días o más desde el envío; más de {URGENTE_DIAS} = urgente.")


def _norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return [t for t in s.replace(",", " ").split() if t]


def leer_tos(ruta):
    """Excel descargado de Ver ordenes Transferencia (o CSV ';' de prueba)."""
    if str(ruta).lower().endswith(".csv"):
        df = pd.read_csv(ruta, sep=";", dtype=str)
    else:
        crudo = pd.read_excel(ruta, header=None, dtype=object)
        fila = next(i for i in range(min(6, len(crudo))) if "TO/SO" in [str(x).strip() for x in crudo.iloc[i]])
        df = crudo.iloc[fila + 1:].copy()
        df.columns = [str(x).strip() for x in crudo.iloc[fila]]
    df = df.dropna(subset=["TO/SO"])
    return pd.DataFrame({
        "TO": df["TO/SO"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip(),
        "Entregar a": df["Entregar a"].astype(str).str.strip().str.upper(),
        "Trabajador": df["Nombre Trabajador"].astype(str).str.strip(),
        "Almacén": df["Nombre Almacén"].astype(str).str.replace("Global Warehouse ", "", regex=False).str.strip(),
        "Transporte": df["Shipping Method"].astype(str).str.strip(),
        "Enviado": df["Enviado"].map(_fecha),
        "Líneas": pd.to_numeric(df["Líneas"], errors="coerce"),
    })


def asignar(tos, activos):
    """Matricula del cuadrante para cada orden: por 'Entregar a' o, si no, por nombre."""
    mats = set(activos.Matricula)
    tokens = {m: set(_norm(n)) for m, n in zip(activos.Matricula, activos.Nombre)}

    def buscar(r):
        if r["Entregar a"] in mats:
            return r["Entregar a"]
        t = _norm(r["Trabajador"])[:2]  # nombre + primer apellido
        candidatos = [m for m, tk in tokens.items() if len(t) == 2 and set(t) <= tk]
        return candidatos[0] if len(candidatos) == 1 else None

    tos = tos.copy()
    tos["Matrícula"] = tos.apply(buscar, axis=1)
    return tos


def generar(ruta_tos, cuadrante, carpeta, hoy):
    """Devuelve (Excel general, carpeta correos, resumen). Solo crea correo para jefes con pendientes."""
    activos, nombres = leer_cuadrante(cuadrante, exigir_toa=False)
    tos = asignar(leer_tos(ruta_tos), activos)
    tos["Días"] = tos["Enviado"].map(lambda f: (hoy - f).days if f else None)
    tos = tos[tos["Días"] >= MIN_DIAS].copy()
    tos["Estado"] = tos["Días"].map(lambda d: URGENTE if d > URGENTE_DIAS else PENDIENTE)
    jde = activos.set_index("Matricula")["JDE"].to_dict()
    nombre = activos.set_index("Matricula")["Nombre"].to_dict()
    fuera = tos[tos["Matrícula"].isna()].drop(columns=["Matrícula"])
    tos = tos[tos["Matrícula"].notna()].copy()
    tos.insert(0, "JDE", tos["Matrícula"].map(jde))
    tos.insert(2, "Técnico", tos["Matrícula"].map(nombre))
    tos = tos.drop(columns=["Entregar a", "Trabajador"]).sort_values(["JDE", "Días", "Técnico"], ascending=[True, False, True])

    os.makedirs(carpeta, exist_ok=True)
    general = os.path.join(carpeta, f"Recepciones_por_Jefe_{hoy:%Y-%m-%d}.xlsx")
    res = tos.groupby("JDE").agg(Órdenes=("TO", "count"), Técnicos=("Matrícula", "nunique")).reset_index()
    res[URGENTE] = res.JDE.map(tos[tos.Estado == URGENTE].groupby("JDE").size()).fillna(0).astype(int)
    res.insert(1, "Jefe de equipo", res.JDE.map(lambda j: nombres.get(j, j)))
    wb = Workbook()
    wb.active.title = "Resumen"
    escribir(wb.active, res, "Material sin recibir en la app por jefe de equipo", hoy, NOTA)
    escribir(wb.create_sheet("Órdenes"), tos, "Órdenes de transferencia sin recibir", hoy, NOTA)
    escribir(wb.create_sheet("Fuera del control"), fuera, "Órdenes de personas que no están como técnico activo en el cuadrante", hoy, NOTA)
    wb.save(general)

    dir_correos = os.path.join(carpeta, f"correos_recepciones_{hoy:%Y-%m-%d}")
    os.makedirs(dir_correos, exist_ok=True)
    cols = [("Orden", lambda t: t["TO"]), ("Enviado", lambda t: _fmt(t["Enviado"])),
            ("Días", lambda t: str(int(t["Días"]))), ("Almacén / transporte", lambda t: f"{t['Almacén']} · {t['Transporte']}"),
            ("Líneas", lambda t: "" if pd.isna(t["Líneas"]) else str(int(t["Líneas"])))]
    manifiesto = []
    for j, g in tos.groupby("JDE"):
        nom = nombres.get(j, j)
        archivo = f"Recepciones_{nom.replace(' ', '_')}_{hoy:%Y-%m-%d}.xlsx"
        wbj = Workbook()
        wbj.active.title = "Mi equipo"
        escribir(wbj.active, g.drop(columns="JDE"), f"Jefe de equipo: {nom} ({j})", hoy, NOTA)
        ruta = os.path.join(dir_correos, archivo)
        wbj.save(ruta)
        secciones = [(f"{URGENTE} – recibir ya", "#FDECEA", "#C0392B", g[g.Estado == URGENTE]),
                     (PENDIENTE, "#FFF8E1", "#E0A800", g[g.Estado == PENDIENTE])]
        cajas = "".join(
            f'<td align="center" style="padding:8px 4px;background:{fondo};border-top:3px solid {borde}">'
            f'<div style="font-size:22px;font-weight:bold;color:{borde}">{len(sub)}</div>'
            f'<div style="font-size:11px;color:#555">{_html.escape(t.split(" –")[0])}</div></td>'
            for t, fondo, borde, sub in secciones)
        bloques = "".join(_tabla(sub, t, fondo, borde, cols) for t, fondo, borde, sub in secciones if len(sub))
        cuerpo = f"""<div style="font-family:Arial,Helvetica,sans-serif;color:#222;max-width:680px">
<p style="font-size:14px">Hola {_html.escape(nom.split()[0])},</p>
<p style="font-size:14px">Te paso el material que el almacén ya ha enviado a tu equipo y que <b>todavía no está recibido en la app</b>
(Recibir TOs), a fecha <b>{hoy:%d/%m/%Y}</b>. Solo aparecen las órdenes enviadas hace {MIN_DIAS} días o más.
En cuanto el técnico tenga el material tiene que recibirlo en digital; si no le ha llegado, que lo avise para reclamarlo.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="4" style="margin:10px 0"><tr>{cajas}</tr></table>
{bloques}
<p style="font-size:14px;margin-top:20px">Te adjunto el Excel con el detalle. Avísame si algún dato no cuadra.</p>
<p style="font-size:14px">Un saludo,</p>
<p style="font-size:14px;margin-top:4px">Gustavo Perez<br>Aurum BC Security SL</p></div>"""
        urg = int((g.Estado == URGENTE).sum())
        manifiesto.append({
            "jde": j, "nombre": nom, "asunto": f"Material pendiente de recibir en la app - {hoy:%d/%m/%Y}",
            "html": cuerpo, "archivo": archivo,
            "texto": f"Material de tu equipo enviado por el almacén y sin recibir en la app a {hoy:%d/%m/%Y}: "
                     f"{len(g)} órdenes ({urg} con más de {URGENTE_DIAS} días). Detalle en el Excel adjunto.",
            "xlsx_b64": base64.b64encode(open(ruta, "rb").read()).decode(),
        })
        with open(ruta.replace(".xlsx", ".html"), "w", encoding="utf-8") as fh:
            fh.write('<!doctype html><html lang="es"><head><meta charset="utf-8">'
                     '<meta name="viewport" content="width=device-width,initial-scale=1">'
                     f'<title>Correo {_html.escape(nom)}</title></head>'
                     f'<body style="margin:0;padding:16px;background:#fff">{cuerpo}</body></html>')
    with open(os.path.join(dir_correos, "correos.json"), "w", encoding="utf-8") as fh:
        json.dump(manifiesto, fh, ensure_ascii=False)
    resumen = (f"Órdenes con {MIN_DIAS}+ días sin recibir: {len(tos)} (urgentes: {int((tos.Estado == URGENTE).sum())})"
               f"\nFuera del control: {len(fuera)}\n\n" + (res.drop(columns="JDE").to_string(index=False) if len(res) else ""))
    return general, dir_correos, resumen


if __name__ == "__main__":
    ruta, cuadrante, carpeta = sys.argv[1:4]
    hoy = date.fromisoformat(sys.argv[4]) if len(sys.argv) > 4 else date.today()
    general, correos, resumen = generar(ruta, cuadrante, carpeta, hoy)
    print(resumen)
    print("correos preparados en:", correos)
