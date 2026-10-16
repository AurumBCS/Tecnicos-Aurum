"""
Control semanal de recuentos por jefe de equipo (lunes 10:00, tarea
"recuentos_semanal" de la Lambda). Sustituye el proceso manual de la carpeta
"Correo Recuentos" del Mac (semanal.py + enviar_borradores.py):

  1. Entra a la app OV (ov_comun.py, con Authenticator si hace falta) y
     descarga Counts -> Ver Conteos en Excel, con la vista por defecto (año
     en curso, todos los estados) -- lo mismo que la "Tabla Ver Conteos" que
     se bajaba a mano.
  2. Descarga el cuadrante del script de la app (?type=recuentos).
  3. Genera el informe con recuentos_por_jefe.py (Excel general + correo y
     Excel por jefe).
  4. Manda los correos al Apps Script (?type=recuentos-borradores), que busca
     el correo de cada jefe en el cuadrante y, segun RECUENTOS_MODO:
       borradores -> deja un borrador por jefe en Gmail (por defecto)
       enviar     -> los envia directamente (con copia fija definida en el Apps Script)
       prueba     -> solo comprueba a quien iria cada correo
  5. Manda a Gustavo un correo con el resultado y el Excel general.

Variables de entorno: RECUENTOS_SCRIPT_URL, RECUENTOS_APP_TOKEN, RECUENTOS_KEY,
RECUENTOS_MODO (opcional), y las del login (ETADIRECT_PASS, GMAIL_*).

Uso local (sin entrar a OV, con un Excel ya descargado):
  python ov_recuentos.py --conteos "Tabla Ver Conteos.xlsx" [--modo prueba]
"""

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from comun_ofs import CARPETA_BASE, enviar_aviso, registrar_error

AQUI = Path(__file__).parent
MODOS = ("borradores", "enviar", "prueba")


def _arg(nombre):
    if nombre in sys.argv:
        return sys.argv[sys.argv.index(nombre) + 1]
    return None


def _entorno(nombre):
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre} en la Lambda")
    return valor


def descargar_conteos(destino):
    """Counts -> Ver Conteos -> Acciones -> Descargar -> Excel. Devuelve el numero de filas que dice la tabla."""
    from playwright.sync_api import sync_playwright
    from ov_comun import URL_OV, abrir_ov

    with sync_playwright() as p:
        browser, context, page = abrir_ov(p, ver="--ver" in sys.argv)
        try:
            # Directo a la pagina con la sesion actual (el enlace del menu no se carga si Counts esta plegado)
            sesion = page.evaluate("apex.env.APP_SESSION")
            page.goto(f"{URL_OV}view-counts?session={sesion}", wait_until="domcontentloaded")
            page.wait_for_selector("#Counts_ig .a-GV-table", timeout=60000)
            page.wait_for_load_state("networkidle")
            rango = page.locator("#Counts_ig .a-GV-pageRange")
            filas = rango.first.inner_text() if rango.count() else "?"
            print(f"[recuentos] Ver Conteos: {filas.strip()}")

            page.evaluate("apex.region('Counts').call('getActions').invoke('show-download-dialog')")
            dialogo = page.locator(".ui-dialog:visible").last
            dialogo.locator("[data-value='XLSX']").first.click()
            with page.expect_download(timeout=120000) as descarga:
                dialogo.get_by_role("button", name="Descargar").click()
            descarga.value.save_as(str(destino))
            print(f"[recuentos] Excel descargado: {destino.stat().st_size} bytes")
            return filas.strip()
        finally:
            browser.close()


def descargar_cuadrante(destino):
    url = _entorno("RECUENTOS_SCRIPT_URL") + "?" + urllib.parse.urlencode(
        {"type": "recuentos", "token": _entorno("RECUENTOS_APP_TOKEN")})
    with urllib.request.urlopen(url, timeout=120) as r:
        csv = r.read().decode("utf-8")
    if not csv.startswith('"Fila"'):
        raise RuntimeError("El script no devolvio el cuadrante esperado: " + csv[:200])
    destino.write_text(csv, encoding="utf-8")
    print(f"[recuentos] cuadrante: {csv.count(chr(10))} filas")


def mandar_correos(carpeta_correos, modo):
    jefes = json.loads((carpeta_correos / "correos.json").read_text(encoding="utf-8"))
    datos = {"key": _entorno("RECUENTOS_KEY"), "modo": modo, "jefes": jefes}
    req = urllib.request.Request(_entorno("RECUENTOS_SCRIPT_URL") + "?type=recuentos-borradores",
                                 data=json.dumps(datos).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        texto = r.read().decode()
    try:
        res = json.loads(texto)
    except ValueError:
        raise RuntimeError("El Apps Script no devolvio JSON: " + texto[:300])
    if not res.get("ok"):
        raise RuntimeError("Error del Apps Script: " + str(res.get("error")))
    nombres = {j["jde"]: j["nombre"] for j in jefes}
    lineas = [f"[{'OK ' if r['ok'] else 'ERR'}] {nombres.get(r['jde'], r['jde'])} -> {r.get('para', '')} {r.get('error', '')}"
              for r in res["resultado"]]
    print("\n".join(lineas))
    return res, lineas


def main():
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    modo = (_arg("--modo") or os.environ.get("RECUENTOS_MODO") or "borradores").strip()
    if modo not in MODOS:
        raise RuntimeError(f"RECUENTOS_MODO no valido: {modo} (usa {'/'.join(MODOS)})")
    carpeta = CARPETA_BASE / "recuentos" / hoy
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        conteos = Path(_arg("--conteos")) if _arg("--conteos") else carpeta / "Tabla Ver Conteos.xlsx"
        filas = "Excel local" if _arg("--conteos") else descargar_conteos(conteos)
        cuadrante = carpeta / "cuadrante.csv"
        descargar_cuadrante(cuadrante)

        general = carpeta / f"Recuentos_por_Jefe_{hoy}.xlsx"
        r = subprocess.run([sys.executable, "-W", "ignore", str(AQUI / "recuentos_por_jefe.py"),
                            str(conteos), str(cuadrante), str(general), hoy],
                           capture_output=True, text=True)
        print(r.stdout)
        if r.returncode:
            raise RuntimeError("recuentos_por_jefe.py fallo:\n" + r.stderr[-1500:])

        res, lineas = mandar_correos(carpeta / f"correos_{hoy}", modo)
        errores = sum(1 for x in res["resultado"] if not x["ok"])
        que = {"borradores": "Borradores creados en Gmail (revisalos y envialos)",
               "enviar": "Correos ENVIADOS a los jefes", "prueba": "Modo prueba: no se creo ni envio nada"}[modo]
        enviar_aviso(
            f"Recuentos {hoy}: {que.split(' (')[0].lower()}" + (f" -- {errores} con error" if errores else ""),
            f"{que}.\n\nVer Conteos: {filas}\n\n" + "\n".join(lineas)
            + f"\n\nResumen:\n{r.stdout.strip()[:3000]}\n\nAdjunto el Excel general.",
            adjunto=general)
        if errores:
            sys.exit(1)
    except Exception as e:
        registrar_error("ov_recuentos", str(e))
        enviar_aviso(f"Recuentos {hoy}: fallo", f"El control semanal de recuentos fallo:\n\n{e}")
        raise


if __name__ == "__main__":
    main()
