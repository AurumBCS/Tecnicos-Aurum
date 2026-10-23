"""
Analisis automatico de los mantenimientos repetidos (RM) de un mes, para el
dashboard de RM de la app.

Mes vencido: el RM de un mes son los mantenimientos del mes anterior (el
Excel "Repeated Maintenance Aurum" que llega en octubre trae septiembre y es
el RM de octubre). El Apps Script guarda cada Excel en su pestana "RM <Mes>"
(ver apps-script/RM_mensual.gs).

Que hace:
  1. Pide al Apps Script las RM del mes (type=rm&mes=) y el analisis que ya
     hay (type=rm-analisis&mes=). Solo trabaja las RM que faltan.
  2. Entra en la consola de Oracle (una aprobacion en Authenticator) y lee la
     ficha del mantenimiento ORIGINAL de cada RM (ofs_rm_prueba).
  3. Aplica las reglas de rm_reglas.py y manda el resultado al Apps Script
     (POST type=rm-analisis) cada pocas RM, para no perder nada si se corta.
  4. Si se acaba el tiempo de la Lambda y quedan RM, se vuelve a lanzar a si
     misma (ronda+1). La sesion de Oracle se guarda en /tmp entre rondas: si
     la siguiente ronda cae en el mismo contenedor, no pide otra aprobacion.

No se guardan datos del cliente: solo observaciones del tecnico (ya limpias
de nombres/telefonos/emails por ficha_ofs), codificaciones y el veredicto.

Evento:
  {"tarea": "rm_analizar"}                         -> RM del mes en curso
  {"tarea": "rm_analizar", "mes": "Septiembre"}
  {"tarea": "rm_analizar", "mes": "Septiembre", "tecnicos": ["302154"]}
  {"tarea": "rm_analizar", "max": 20}               -> como mucho 20 RM (prueba)
Variables de entorno: RECUENTOS_SCRIPT_URL, RECUENTOS_APP_TOKEN, RECUENTOS_KEY
(las mismas del control de recuentos) y las de la consola (ETADIRECT_PASS...).
"""

import csv
import io
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

import rm_reglas
from comun_ofs import CARPETA_BASE, LAUNCH_ARGS, enviar_aviso, registrar_error

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]
SESION = Path(CARPETA_BASE) / "ofs_sesion_rm.json"
LOTE = 10                 # RM por cada envio al Apps Script
MARGEN_MS = 150_000       # tiempo que se deja libre al final de la Lambda
MAX_RONDAS = 60


def _entorno(nombre):
    v = os.environ.get(nombre, "").strip()
    if not v:
        raise RuntimeError(f"Falta la variable {nombre} en la Lambda")
    return v


def _get_csv(tipo, mes):
    url = _entorno("RECUENTOS_SCRIPT_URL") + "?" + urllib.parse.urlencode(
        {"type": tipo, "mes": mes, "token": _entorno("RECUENTOS_APP_TOKEN")})
    with urllib.request.urlopen(url, timeout=120) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))


def _enviar(filas):
    if not filas:
        return
    datos = {"key": _entorno("RECUENTOS_KEY"), "filas": filas}
    req = urllib.request.Request(_entorno("RECUENTOS_SCRIPT_URL") + "?type=rm-analisis",
                                 data=json.dumps(datos).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        raise RuntimeError("El Apps Script no guardo el analisis: " + str(res.get("error")))
    print(f"[rm] guardadas {res.get('nuevas')} nuevas / {res.get('actualizadas')} actualizadas")


def pendientes(mes, tecnicos=None):
    """RM del mes (repetidas) que todavia no tienen analisis."""
    rm = _get_csv("rm", mes)
    hechas = {f.get("nMant", "").strip() for f in _get_csv("rm-analisis", mes)}
    tecs = {t.strip().upper() for t in (tecnicos or []) if t}
    out = []
    for f in rm:
        if f.get("repetido", "").strip().upper() not in ("SI", "SÍ", "1", "TRUE"):
            continue
        n = f.get("nMant", "").strip()
        if not n or n in hechas or (tecs and f.get("tecnico", "").strip().upper() not in tecs):
            continue
        out.append({"nMant": n, "tecnico": f.get("tecnico", "").strip().upper(), "nMantPost": f.get("nMantPost", "").strip(),
                    "motivo": f.get("motivo", "").strip(), "motivoPost": f.get("motivo_post", "").strip()})
    return out


def _fila(mes, rm, ficha):
    if not isinstance(ficha, dict):
        return dict(rm, mes=mes, panel="", severidad="", causas="",
                    queHizo="No se pudo leer la ficha en Oracle.", queFalto="", codificacion="")
    a = rm_reglas.analizar(ficha, rm["motivoPost"])
    return dict(rm, mes=mes, panel=a["panel"], severidad=a["severidad"], causas=";".join(a["causas"]),
                queHizo=a["queHizo"], queFalto=a["queFalto"], codificacion=a["codificacion"])


def main(event=None, context=None):
    import consola_sso
    import ofs_rm_prueba

    event = dict(event or {})
    mes = event.get("mes") or MESES[datetime.now(ZoneInfo("Europe/Madrid")).month - 1]
    ronda = int(event.get("ronda") or 1)
    lista = pendientes(mes, event.get("tecnicos"))
    if event.get("max"):
        lista = lista[: int(event["max"])]
    print(f"[rm] {mes}: {len(lista)} RM pendientes de analizar (ronda {ronda})")
    if not lista:
        return {"mes": mes, "analizadas": 0, "pendientes": 0}

    def queda_tiempo():
        return context is None or context.get_remaining_time_in_millis() > MARGEN_MS

    correo, clave = consola_sso.leer_credenciales_sso()
    hechas, lote, errores, capturas = 0, [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        opciones = {"viewport": {"width": 1600, "height": 1000}}
        if SESION.exists():
            opciones["storage_state"] = str(SESION)
        ctx = browser.new_context(**opciones)
        page = ctx.new_page()
        try:
            consola_sso.entrar_a_consola(page, correo, clave)
            ctx.storage_state(path=str(SESION))
            for rm in lista:
                if not queda_tiempo():
                    break
                ficha = ofs_rm_prueba._leer(page, rm["nMant"], capturas, errores)
                lote.append(_fila(mes, rm, ficha))
                hechas += 1
                if len(lote) >= LOTE:
                    _enviar(lote)
                    lote = []
        except Exception as e:
            errores.append(f"ronda {ronda}: {e}")
            registrar_error("rm_analizar", str(e))
        finally:
            try:
                _enviar(lote)
            except Exception as e:
                errores.append(f"envio final: {e}")
            try:
                ctx.storage_state(path=str(SESION))
            except Exception:
                pass
            browser.close()

    quedan = len(lista) - hechas
    print(f"[rm] ronda {ronda}: {hechas} analizadas, quedan {quedan}")
    seguir = quedan > 0 and not event.get("max") and ronda < MAX_RONDAS and context is not None and hechas > 0
    if seguir:
        import boto3
        boto3.client("lambda").invoke(FunctionName=context.function_name, InvocationType="Event",
                                      Payload=json.dumps(dict(event, tarea="rm_analizar", mes=mes, ronda=ronda + 1)).encode())
        print("[rm] lanzada la ronda", ronda + 1)
    elif errores or not quedan:
        asunto = ("⚠️" if errores else "✅") + f" Análisis de RM {mes}: {hechas} en la última ronda"
        cuerpo = [f"RM de {mes}: ronda {ronda}, {hechas} analizadas, quedan {quedan}."]
        if errores:
            cuerpo += ["", "Errores:"] + errores
        enviar_aviso(asunto, "\n".join(cuerpo), capturas=capturas)
    return {"mes": mes, "analizadas": hechas, "pendientes": quedan, "ronda": ronda}


if __name__ == "__main__":
    import sys
    # python rm_analizar.py Septiembre [302154 ...]   (prueba local, sin encadenar rondas)
    main({"mes": sys.argv[1] if len(sys.argv) > 1 else None, "tecnicos": sys.argv[2:], "max": 5})
