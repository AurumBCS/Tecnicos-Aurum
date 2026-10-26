"""
Tareas de Oracle en el Mac (launchd, lunes a viernes), con un solo numero de
Authenticator que llega por correo como con la Lambda.

  python3 mac_tarde.py            -> 18:05, despues de la Lambda de las 17:50 (ruta + SMS):
                                     1. Proxima ruta: ficha de cada mantenimiento de la ruta del
                                        siguiente dia de trabajo de toda la empresa y sugerencias a la app.
                                     2. RM del mes sin analizar (Excel de martes y jueves).
  python3 mac_tarde.py --manana   -> 8:00: actualizacion rapida de la ruta de HOY. Solo lee los
                                     mantenimientos que no se leyeron por la tarde.

La sesion de Oracle se guarda al terminar (SESION_MAC) y se reutiliza en la
siguiente tarea: si sigue viva no hace falta aprobar nada. Si Oracle la cerro,
se entra de cero y llega el correo con el numero.

Lo lanza "Correo Recuentos/tarde_mac.sh", que saca las claves del Llavero.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

import consola_sso
import ofs_rm_prueba
import rm_analizar
import ruta_sugerencias
from comun_ofs import LAUNCH_ARGS, enviar_aviso, registrar_error

SESION_MAC = Path(os.environ.get("SESION_MAC", Path.home() / ".aurum_ofs_sesion.json"))


def _entrar(browser, correo, clave):
    """Consola abierta reutilizando la sesion guardada si sigue viva. Devuelve (ctx, page, reutilizada)."""
    pidio_login = []
    original = consola_sso.iniciar_sesion_microsoft

    def con_aviso(*a, **k):
        pidio_login.append(True)
        return original(*a, **k)

    consola_sso.iniciar_sesion_microsoft = con_aviso
    try:
        if SESION_MAC.exists():
            ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, storage_state=str(SESION_MAC))
            page = ctx.new_page()
            try:
                consola_sso.entrar_a_consola(page, correo, clave)
                return ctx, page, not pidio_login
            except Exception as e:
                print(f"[mac] la sesion guardada no sirvio ({e.__class__.__name__}); se entra de cero")
                ctx.close()
                pidio_login.clear()
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        consola_sso.entrar_a_consola(page, correo, clave)
        return ctx, page, False
    finally:
        consola_sso.iniciar_sesion_microsoft = original


def _fichas_ya_leidas(fecha_iso):
    """numero -> ficha de las copias guardadas por la tarde para esa fecha."""
    leidas = {}
    for f in sorted(ruta_sugerencias.CARPETA_SALIDA.glob(f"ruta_*{fecha_iso}*.json")):
        try:
            for d in json.load(open(f, encoding="utf-8")):
                if d.get("fecha") == fecha_iso and d.get("ficha"):
                    leidas[d["numero"]] = d["ficha"]
        except Exception:
            pass
    return leidas


def _proxima_ruta(page, fechas_iso, errores, capturas, reutilizar=False):
    filas = []
    for f in fechas_iso:
        filas += ruta_sugerencias._filas_ruta(consola_sso.descargar_csv_grupos(page, f), f)
    ya = {}
    if reutilizar:
        for f in fechas_iso:
            ya.update(_fichas_ya_leidas(f))
    nuevas = [f for f in filas if f["numero"] not in ya]
    print(f"[mac] ruta {', '.join(fechas_iso)}: {len(filas)} mantenimientos, {len(nuevas)} por leer")
    datos = []
    for i, f in enumerate(filas, 1):
        ficha = ya.get(f["numero"])
        if ficha is None:
            ficha = ofs_rm_prueba._leer(page, f["numero"], capturas, errores)
            ficha = ficha if isinstance(ficha, dict) else None
        datos.append(dict(f, ficha=ficha))
        if i % 50 == 0:
            print(f"[mac] {i}/{len(filas)}")
    ruta_sugerencias.CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    sufijo = "manana" if reutilizar else "todos"
    (ruta_sugerencias.CARPETA_SALIDA / f"ruta_{'_'.join(fechas_iso)}_{sufijo}.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    sug = ruta_sugerencias.sugerencias(datos)
    ruta_sugerencias.enviar(fechas_iso, sug)
    return (f"Ruta {', '.join(fechas_iso)}: {len(sug)} mantenimientos con sugerencias, "
            f"{sum(1 for s in sug if s['alertas'])} con riesgo de RM"
            + (f" ({len(nuevas)} nuevos desde la tarde)." if reutilizar else
               f" ({sum(1 for d in datos if d['ficha'])}/{len(datos)} fichas leídas)."))


def main(manana=False):
    inicio = datetime.now()
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
    if manana and hoy.weekday() >= 5:
        print("[mac] fin de semana: nada que hacer por la mañana")
        return 0
    fechas_iso = [hoy.isoformat()] if manana else [f.isoformat() for f in ruta_sugerencias.fechas_objetivo()]
    resumen, errores, capturas = [], [], []
    correo, clave = consola_sso.leer_credenciales_sso()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        ctx = None
        try:
            ctx, page, reutilizada = _entrar(browser, correo, clave)
            resumen.append("Sesión de Oracle: " + ("reutilizada, sin aprobar nada." if reutilizada else "nueva (con aprobación)."))
            try:
                resumen.append(_proxima_ruta(page, fechas_iso, errores, capturas, reutilizar=manana))
            except Exception as e:
                errores.append(f"próxima ruta: {e}")
                registrar_error("mac_tarde", f"proxima ruta: {e}")
            if not manana:
                try:
                    mes = rm_analizar._mes_actual()
                    lista = rm_analizar.pendientes(mes)
                    hechas = 0
                    if lista:
                        hechas = rm_analizar._analizar_lista(page, ctx, correo, clave, mes, lista, lambda: True,
                                                             errores, capturas, local=True)
                    resumen.append(f"RM de {mes}: {hechas} analizadas" + ("" if lista else " (no había pendientes)") + ".")
                except Exception as e:
                    errores.append(f"RM: {e}")
                    registrar_error("mac_tarde", f"rm: {e}")
        except Exception as e:
            errores.append(f"entrada en la consola: {e}")
            registrar_error("mac_tarde", f"entrada: {e}")
        finally:
            if ctx is not None:
                try:
                    ctx.storage_state(path=str(SESION_MAC))
                    os.chmod(SESION_MAC, 0o600)
                except Exception:
                    pass
            browser.close()

    minutos = round((datetime.now() - inicio).total_seconds() / 60)
    asunto = ("⚠️" if errores else "✅") + (" Ruta de hoy actualizada" if manana else " Tarde en el Mac") + f" ({minutos} min)"
    cuerpo = resumen + ([""] + ["Errores:"] + errores[:30] if errores else [])
    print("\n".join([asunto] + cuerpo))
    enviar_aviso(asunto, "\n".join(cuerpo), capturas=capturas[:3])
    return 1 if errores and len(resumen) <= 1 else 0


if __name__ == "__main__":
    sys.exit(main(manana="--manana" in sys.argv))
