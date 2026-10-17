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

En la misma entrada a la app hace tambien el correo de RECEPCIONES (material enviado por
el almacen y sin recibir en la app: Inventario Transacciones -> Recibir TOs), ver
recepciones_por_jefe.py. Se manda ANTES que devoluciones y sin apuntar el dia como hecho,
para que si algo falla el respaldo repita los dos. Modo: RECEPCIONES_MODO (por defecto prueba).

Antes de nada comprueba que el Apps Script ya separa el estado de recuentos y de
devoluciones (si no, para: se pisarian el "dia hecho" de los dos controles).
Respaldo ({"tarea": "devoluciones_diario", "respaldo": true}): si hoy ya se hizo, no hace nada.

Variables de entorno: las de recuentos (RECUENTOS_SCRIPT_URL, RECUENTOS_APP_TOKEN,
RECUENTOS_KEY), DEVOLUCIONES_MODO y RECEPCIONES_MODO (opcionales).

Uso local (sin entrar a OV, con las 3 listas ya descargadas):
  python ov_devoluciones.py --borrador B.xlsx --completado C.xlsx --pendiente P.xlsx --tos T.xlsx [--modo prueba] [--respaldo]
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from comun_ofs import CARPETA_BASE, enviar_aviso, registrar_error


def _entrada():
    import ov_comun
    return ov_comun.resumen_entrada()
from ov_recuentos import MODOS, _arg, descargar_cuadrante, mandar_correos, ya_hecho

TIPO = "devoluciones"
LISTAS = {"D": ("Borrador", "--borrador"), "C": ("Completado", "--completado"), "P": ("Recibo Pendiente", "--pendiente")}
TOS = "view-tos?p297_qf_process_status=P&clear=CR,297"  # Recibir TOs (ordenes en Recibo Pendiente)


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
            rutas["TOS"] = carpeta / "Recibir TOs.xlsx"
            filas["Recibir TOs"] = descargar_ig(page, TOS, rutas["TOS"])
        finally:
            browser.close()
    return rutas, filas


def main(respaldo=False):
    import devoluciones_por_jefe
    import recepciones_por_jefe

    respaldo = respaldo or "--respaldo" in sys.argv
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    hoy = ahora.date().isoformat()
    modo = (_arg("--modo") or os.environ.get("DEVOLUCIONES_MODO") or "borradores").strip()
    if modo not in MODOS:
        raise RuntimeError(f"DEVOLUCIONES_MODO no valido: {modo} (usa {'/'.join(MODOS)})")
    modo_recep = (_arg("--modo") or os.environ.get("RECEPCIONES_MODO") or "prueba").strip()
    if modo_recep not in MODOS:
        raise RuntimeError(f"RECEPCIONES_MODO no valido: {modo_recep} (usa {'/'.join(MODOS)})")
    carpeta = CARPETA_BASE / "devoluciones" / hoy
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        # Siempre (no solo en el respaldo): confirma que el Apps Script separa el estado por tipo
        if ya_hecho(hoy, TIPO) and respaldo:
            print("[devoluciones] respaldo: hoy ya se hizo -- no se hace nada")
            return
        if _arg("--borrador"):
            rutas = {k: Path(_arg(flag)) for k, (_, flag) in LISTAS.items()}
            rutas["TOS"] = Path(_arg("--tos"))
            filas = {"origen": "Excel local"}
        else:
            rutas, filas = descargar_devoluciones(carpeta)
        cuadrante = carpeta / "cuadrante.csv"
        descargar_cuadrante(cuadrante)

        # Recepciones primero (sin apuntar el dia: lo apunta devoluciones al final)
        g_rec, d_rec, r_rec = recepciones_por_jefe.generar(rutas["TOS"], cuadrante, carpeta, ahora.date())
        print(r_rec)
        res_rec, lin_rec = mandar_correos(Path(d_rec), modo_recep, hoy, TIPO, marcar=False)
        err_rec = sum(1 for x in res_rec["resultado"] if not x["ok"])
        que_rec = {"borradores": "Borradores creados en Gmail", "enviar": "Correos ENVIADOS a los jefes",
                   "prueba": "Modo prueba: no se creo ni envio nada"}[modo_recep]
        enviar_aviso(f"Recepciones {hoy}: {que_rec.lower()}" + (f" -- {err_rec} con error" if err_rec else ""),
                     _entrada() + f"{que_rec}.\n\n" + ("\n".join(lin_rec) or "Ningún jefe con material pendiente de recibir.")
                     + f"\n\nResumen:\n{r_rec[:3000]}\n\nAdjunto el Excel general.", adjunto=Path(g_rec))

        general, dir_correos, resumen = devoluciones_por_jefe.generar(rutas, cuadrante, carpeta, ahora.date())
        print(resumen)

        res, lineas = mandar_correos(Path(dir_correos), modo, hoy, TIPO)
        errores = sum(1 for x in res["resultado"] if not x["ok"])
        que = {"borradores": "Borradores creados en Gmail (revisalos y envialos)",
               "enviar": "Correos ENVIADOS a los jefes", "prueba": "Modo prueba: no se creo ni envio nada"}[modo]
        enviar_aviso(
            f"Devoluciones {hoy}: {que.split(' (')[0].lower()}" + (f" -- {errores} con error" if errores else ""),
            _entrada() + f"{que}.\n\nListas descargadas: " + ", ".join(f"{k}: {v}" for k, v in filas.items()) + "\n\n"
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
