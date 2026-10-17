"""
Control diario de devoluciones al almacen por jefe de equipo (lunes a viernes
11:00, tarea "devoluciones_diario" de la Lambda; respaldo a las 13:00).

  1. Entra a la app OV (ov_comun.py, con Authenticator si hace falta) y en
     Inventario Transacciones -> Devoluciones al almacen descarga en Excel las
     3 listas: Borrador, Completado y Recibo Pendiente (pagina Ver Devoluciones).
  2. Descarga el cuadrante del script de la app (?type=recuentos).
  3. Genera el informe con devoluciones_por_jefe.py (Excel general + correo y
     Excel por jefe).
  4. Manda los correos al Apps Script (tipo "devoluciones"), segun DEVOLUCIONES_MODO:
     borradores (por defecto) / enviar (con la copia fija del Apps Script) / prueba.
  5. Manda a Gustavo un correo con el resultado y el Excel general.

Antes de nada comprueba que el Apps Script ya separa el estado de recuentos y de
devoluciones (si no, para: se pisarian el "dia hecho" de los dos controles).
Respaldo ({"tarea": "devoluciones_diario", "respaldo": true}): si hoy ya se hizo, no hace nada.

Variables de entorno: las de recuentos (RECUENTOS_SCRIPT_URL, RECUENTOS_APP_TOKEN,
RECUENTOS_KEY) y DEVOLUCIONES_MODO (opcional).

Uso local (sin entrar a OV, con las 3 listas ya descargadas):
  python ov_devoluciones.py --borrador B.xlsx --completado C.xlsx --pendiente P.xlsx [--modo prueba] [--respaldo]
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from comun_ofs import CARPETA_BASE, enviar_aviso, registrar_error
from ov_recuentos import MODOS, _arg, descargar_cuadrante, mandar_correos, ya_hecho

TIPO = "devoluciones"
LISTAS = {"D": ("Borrador", "--borrador"), "C": ("Completado", "--completado"), "P": ("Recibo Pendiente", "--pendiente")}


def descargar_devoluciones(carpeta):
    """Las 3 listas de Ver Devoluciones en Excel. Devuelve ({estado: ruta}, {estado: filas})."""
    from playwright.sync_api import sync_playwright
    from ov_comun import abrir_ov, descargar_ig

    rutas, filas = {}, {}
    with sync_playwright() as p:
        browser, context, page = abrir_ov(p, ver="--ver" in sys.argv)
        try:
            for estado, (nombre, _) in LISTAS.items():
                rutas[estado] = carpeta / f"Devoluciones {nombre}.xlsx"
                filas[nombre] = descargar_ig(
                    page, f"view-returns?p291_qf_process_status={estado}&request=IG_505517&clear=CR,291", rutas[estado])
        finally:
            browser.close()
    return rutas, filas


def main(respaldo=False):
    import devoluciones_por_jefe

    respaldo = respaldo or "--respaldo" in sys.argv
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    hoy = ahora.date().isoformat()
    modo = (_arg("--modo") or os.environ.get("DEVOLUCIONES_MODO") or "borradores").strip()
    if modo not in MODOS:
        raise RuntimeError(f"DEVOLUCIONES_MODO no valido: {modo} (usa {'/'.join(MODOS)})")
    carpeta = CARPETA_BASE / "devoluciones" / hoy
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        # Siempre (no solo en el respaldo): confirma que el Apps Script separa el estado por tipo
        if ya_hecho(hoy, TIPO) and respaldo:
            print("[devoluciones] respaldo: hoy ya se hizo -- no se hace nada")
            return
        if _arg("--borrador"):
            rutas = {k: Path(_arg(flag)) for k, (_, flag) in LISTAS.items()}
            filas = {"origen": "Excel local"}
        else:
            rutas, filas = descargar_devoluciones(carpeta)
        cuadrante = carpeta / "cuadrante.csv"
        descargar_cuadrante(cuadrante)

        general, dir_correos, resumen = devoluciones_por_jefe.generar(rutas, cuadrante, carpeta, ahora.date())
        print(resumen)

        res, lineas = mandar_correos(Path(dir_correos), modo, hoy, TIPO)
        errores = sum(1 for x in res["resultado"] if not x["ok"])
        que = {"borradores": "Borradores creados en Gmail (revisalos y envialos)",
               "enviar": "Correos ENVIADOS a los jefes", "prueba": "Modo prueba: no se creo ni envio nada"}[modo]
        enviar_aviso(
            f"Devoluciones {hoy}: {que.split(' (')[0].lower()}" + (f" -- {errores} con error" if errores else ""),
            f"{que}.\n\nListas descargadas: " + ", ".join(f"{k}: {v}" for k, v in filas.items()) + "\n\n"
            + "\n".join(lineas) + f"\n\nResumen:\n{resumen[:3000]}\n\nAdjunto el Excel general.",
            adjunto=Path(general))
        if errores:
            sys.exit(1)
    except Exception as e:
        registrar_error("ov_devoluciones", str(e))
        siguiente = ("Lanzalo a mano desde Lambda -> Test con {\"tarea\": \"devoluciones_diario\"}." if respaldo
                     else "A las 13:00 el respaldo lo intenta otra vez solo.")
        enviar_aviso(f"Devoluciones {hoy}: fallo" + (" (respaldo)" if respaldo else ""),
                     f"El control diario de devoluciones fallo:\n\n{e}\n\n{siguiente}")
        raise


if __name__ == "__main__":
    main()
