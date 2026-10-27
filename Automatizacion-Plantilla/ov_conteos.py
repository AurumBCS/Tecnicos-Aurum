"""
Correo al jefe de equipo con los fallos de codificacion de cada conteo PERIODICO
aprobado (app OV, Counts). Reglas en conteos_codificacion.py y en
"Correo Recuentos/conteos-reglas.md".

  1. Entra a la app OV y descarga Counts -> Ver Conteos (lista).
  2. Elige los conteos Periodicos aprobados del dia (o los codigos que se pidan).
  3. Descarga las lineas de cada uno (Ver/Meter Conteos) y las analiza.
  4. Un correo por conteo al jefe de equipo del tecnico, por el Apps Script
     (type=recuentos-borradores, con el detalle en Excel adjunto): mismos destinatarios
     y copias que recuentos y devoluciones.
  5. Resumen a Gustavo.

Uso:
  python3 ov_conteos.py                         -> periodicos aprobados hoy, modo CONTEOS_MODO (enviar)
  python3 ov_conteos.py --fecha 2026-10-22
  python3 ov_conteos.py --codigos C26103643 C26103488 --modo prueba
  python3 ov_conteos.py --excluir C26102603
Variables: RECUENTOS_SCRIPT_URL, RECUENTOS_APP_TOKEN, RECUENTOS_KEY, CONTEOS_MODO y las del login.
"""

import argparse
import csv
import io
import json
import os
import re
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import conteos_codificacion as cc
from comun_ofs import CARPETA_BASE, enviar_aviso, registrar_error

CARPETA = Path(os.environ.get("CONTEOS_DIR", CARPETA_BASE / "conteos"))
REGISTRO = CARPETA / "enviados.json"   # codigos ya enviados (o descartados): no se repiten
DESDE = date(2026, 10, 12)             # no se miran conteos anteriores


def _registro():
    try:
        return json.loads(REGISTRO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _apuntar(codigos, estado):
    reg = _registro()
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d %H:%M")
    for c in codigos:
        reg[c] = f"{estado} {hoy}"
    REGISTRO.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def _fecha(v):
    if isinstance(v, datetime):
        return v.date()
    try:
        return datetime.strptime(str(v)[:10], "%d-%m-%Y").date()
    except ValueError:
        return None


def _lista(ruta):
    import openpyxl
    filas = list(openpyxl.load_workbook(ruta, read_only=True).active.iter_rows(values_only=True))
    cab = [str(c or "").strip() for c in filas[0]]
    return [dict(zip(cab, f)) for f in filas[1:] if f and f[0]]


def _bajar_lista(page, destino):
    from ov_comun import URL_OV
    sesion = page.evaluate("apex.env.APP_SESSION")
    page.goto(f"{URL_OV}view-counts?session={sesion}", wait_until="domcontentloaded")
    page.wait_for_selector("#Counts_ig .a-GV-table", timeout=60000)
    page.wait_for_load_state("networkidle")
    page.evaluate("apex.region('Counts').call('getActions').invoke('show-download-dialog')")
    dlg = page.locator(".ui-dialog:visible").last
    dlg.locator("[data-value='XLSX']").first.click()
    with page.expect_download(timeout=120000) as d:
        dlg.get_by_role("button", name="Descargar").click()
    d.value.save_as(str(destino))


def _enlaces(page, codigos, max_paginas=30):
    """Enlace (con su checksum de APEX) de cada conteo, pasando paginas de la lista hasta encontrarlos todos.
    (La busqueda de la tabla aplicaba el texto anterior: visto en vivo el 27/10, por eso se pagina.)"""
    from ov_comun import URL_OV
    sesion = page.evaluate("apex.env.APP_SESSION")
    page.goto(f"{URL_OV}view-counts?session={sesion}", wait_until="domcontentloaded")
    page.wait_for_selector("#Counts_ig .a-GV-table", timeout=60000)
    page.wait_for_load_state("networkidle")
    faltan, enlaces = set(codigos), {}
    for _ in range(max_paginas):
        for href in page.evaluate("() => [...document.querySelectorAll('#Counts_ig .a-GV-row a')].map(a => a.href)"):
            m = re.search(r"p272_code=([^&]+)", href)
            if m and m.group(1) in faltan:
                enlaces[m.group(1)] = href
                faltan.discard(m.group(1))
        siguiente = page.locator("#Counts_ig button.a-GV-pageButton--nav[aria-label*='Siguiente'], "
                                 "#Counts_ig button.a-GV-pageButton--nav[title*='Siguiente'], "
                                 "#Counts_ig button.a-GV-pageButton--nav[aria-label*='Next']")
        if not faltan or not siguiente.count() or not siguiente.first.is_enabled():
            break
        rango = page.locator("#Counts_ig .a-GV-pageRange").first.inner_text()
        siguiente.first.click()
        page.wait_for_function("r => document.querySelector('#Counts_ig .a-GV-pageRange').innerText !== r", arg=rango, timeout=30000)
        page.wait_for_load_state("networkidle")
    for c in sorted(faltan):
        print(f"[conteos] {c}: no aparece en la lista")
    return enlaces


def _bajar_lineas(page, enlace, destino):
    page.goto(enlace, wait_until="domcontentloaded")
    page.wait_for_selector(".a-IG .a-GV-table", timeout=60000)
    page.wait_for_load_state("networkidle")
    region = page.evaluate("document.querySelector('.a-IG').id.replace(/_ig$/, '')")
    page.evaluate(f"apex.region('{region}').call('getActions').invoke('show-download-dialog')")
    dlg = page.locator(".ui-dialog:visible").last
    dlg.locator("[data-value='XLSX']").first.click()
    with page.expect_download(timeout=120000) as d:
        dlg.get_by_role("button", name="Descargar").click()
    d.value.save_as(str(destino))


def _jerarquia():
    url = (os.environ["RECUENTOS_SCRIPT_URL"].strip() + "?type=jerarquia&token=" + os.environ["RECUENTOS_APP_TOKEN"].strip())
    with urllib.request.urlopen(url, timeout=120) as r:
        return {x["Matricula"].strip().upper(): x for x in csv.DictReader(io.StringIO(r.read().decode()))}


def _mandar(jefes, modo):
    datos = {"key": os.environ["RECUENTOS_KEY"].strip(), "tipo": "conteos", "modo": modo, "jefes": jefes}
    req = urllib.request.Request(os.environ["RECUENTOS_SCRIPT_URL"].strip() + "?type=recuentos-borradores",
                                 data=json.dumps(datos).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


def main(fecha=None, codigos=None, excluir=(), modo=None):
    from playwright.sync_api import sync_playwright
    from ov_comun import abrir_ov

    modo = modo or os.environ.get("CONTEOS_MODO", "enviar")
    fecha = fecha or datetime.now(ZoneInfo("Europe/Madrid")).date()
    CARPETA.mkdir(parents=True, exist_ok=True)
    jer = _jerarquia()
    resumen, errores, jefes = [], [], []
    with sync_playwright() as p:
        browser, context, page = abrir_ov(p)
        try:
            _bajar_lista(page, CARPETA / "Ver Conteos.xlsx")
            lista = _lista(CARPETA / "Ver Conteos.xlsx")
            if codigos:
                elegidos = [c for c in lista if c.get("Cód.") in codigos]
            else:
                # Todos los periodicos aprobados que aun no se han enviado (asi no se pierde
                # ninguno que se apruebe despues de la hora del envio)
                ya = _registro()
                elegidos = [c for c in lista if str(c.get("Tipo de Conteo", "")).startswith("Peri")
                            and str(c.get("Estado")) == "Aprobado" and c.get("Cód.") not in ya
                            and (_fecha(c.get("Creado")) or date.min) >= DESDE]
            if excluir:
                _apuntar(excluir, "excluido")
            elegidos = [c for c in elegidos if c.get("Cód.") not in excluir]
            print(f"[conteos] {len(elegidos)} conteo(s): {', '.join(c['Cód.'] for c in elegidos) or '-'}")
            enlaces = _enlaces(page, [c["Cód."] for c in elegidos]) if elegidos else {}
            for c in elegidos:
                cod = c["Cód."]
                mat = str(c.get("Técnico", "")).split()[0].upper()
                try:
                    ruta = CARPETA / f"{cod}.xlsx"
                    if cod not in enlaces:
                        raise RuntimeError("no aparece en la lista de conteos")
                    _bajar_lineas(page, enlaces[cod], ruta)
                    hall = cc.analizar(cc.leer_excel(ruta), mat)
                    persona = jer.get(mat) or jer.get(re.sub(r"^[A-Z]{2}(?=\d{6}$)", "", mat)) or {}
                    jde = persona.get("JE", "").strip().upper()
                    nombre = persona.get("Nombre") or str(c.get("Técnico", "")).split(" ", 1)[-1]
                    cab = {"codigo": cod, "fecha": (_fecha(c.get("Creado")) or fecha).strftime("%d/%m/%Y"),
                           "ajuste_neto": str(c.get("Aju. Neto", "")).strip(), "lineas": c.get("Líneas"),
                           "lineas_dif": c.get("Líneas Dif.")}
                    if not jde:
                        errores.append(f"{cod} {mat}: sin jefe de equipo en el cuadrante")
                        continue
                    html = cc.correo_html(nombre, cab, hall)
                    aviso = "⚠️ " if cc.fuera_de_limite(cab["ajuste_neto"]) else ""
                    import base64
                    archivo = f"Conteo {cod} {nombre}.xlsx"
                    cc.excel_detalle(hall, CARPETA / archivo)
                    jefes.append({"codigo": cod, "jde": jde, "asunto": f"{aviso}Conteo de {nombre}: qué corregir al codificar",
                                  "html": html, "texto": f"Conteo periódico {cod} de {nombre}: fallos de codificación.",
                                  "archivo": archivo,
                                  "xlsx_b64": base64.b64encode((CARPETA / archivo).read_bytes()).decode()})
                    resumen.append(f"{cod} {nombre} (JE {jde}) · ajuste {cab['ajuste_neto']} · "
                                   f"{len([h for h in hall if h['tipo'] != 'sobra'])} fallos")
                except Exception as e:
                    errores.append(f"{cod}: {e}")
                    registrar_error("ov_conteos", f"{cod}: {e}")
        finally:
            browser.close()

    if jefes:
        res = _mandar(jefes, modo)
        hechos = []
        for j, r in zip(jefes, res.get("resultado", [])):
            if not r.get("ok"):
                errores.append(f"{j['codigo']} JE {r.get('jde')}: {r.get('error')}")
            elif modo == "enviar":
                hechos.append(j["codigo"])
        if hechos:
            _apuntar(hechos, "enviado")
        resumen.append(f"Modo {res.get('modo')}: {sum(1 for r in res.get('resultado', []) if r.get('ok'))} correo(s) ok")
    if jefes or errores:
        enviar_aviso(("⚠️" if errores else "✅") + f" Conteos periódicos ({len(jefes)} correos)",
                     "\n".join(resumen + ([""] + ["Errores:"] + errores if errores else [])))
    print("\n".join(resumen + errores))
    return {"correos": len(jefes), "errores": errores}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha")
    ap.add_argument("--codigos", nargs="*")
    ap.add_argument("--excluir", nargs="*", default=[])
    ap.add_argument("--modo", choices=["enviar", "borradores", "prueba"])
    a = ap.parse_args()
    main(date.fromisoformat(a.fecha) if a.fecha else None, a.codigos, a.excluir, a.modo)
