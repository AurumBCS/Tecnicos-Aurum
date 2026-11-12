"""
"Cumplimiento de hoy" (vista del JE en la app) desde la consola de Oracle.

1. Lista de las 8:00 (lista_8): los mantenimientos con los que sale cada técnico. La sube
   mac_tarde.py --manana con los CSV que ya descarga para la ruta (type=agenda-hoy), sin
   depender del correo de Verisure (el 12/11 no llegó). agenda_cruce.py la compara después
   con el Excel de Verisure de las 8:00 y, si el Mac no pudo subirla, sube la de Verisure.
2. Estados en vivo (main): la Lambda, cada 20 minutos de 8:10 a 18:50 (L-V), descarga la
   consola y sube el estado de cada mantenimiento de hoy (type=agenda-vivo). La app avisa al JE
   de los que van a quedar fuera de su franja ("en riesgo": Oracle prevé empezarlos después de
   que acabe) o ya lo están ("fuera de franja").

Solo viajan números de mantenimiento, estados, horas y matrículas: ningún dato de clientes.
"""

import csv
import io
import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
EXEC = ("https://script.google.com/macros/s/AKfycbxotyAfeX08YR-Sx4QuYCt41SOwmfVX5ltxq4n0L2-"
        "XVJoahUkdlo4_EY8-SCDfVgR7/exec")
CLAVE_FICHERO = Path("/Users/gustavoperez/Correo Recuentos/recuentos_clave.txt")
# Copia de la lista de las 8:00 en el Mac, para compararla con el Excel de Verisure (agenda_cruce.py)
FOTO_DIR = Path(os.environ.get("AGENDA_FOTO_DIR")
                or "/Users/gustavoperez/Control Fichajes Tecnicos/agenda-apertura-cierre/oracle_8")
CLAVE_S3_SESION = "sesion_consola.json"
ESTADOS = {"Pendiente": "P", "Iniciado": "I", "Completado": "C", "Suspendido": "S",
           "Cancelado": "X", "No completado": "N"}


def _url():
    return os.environ.get("RECUENTOS_SCRIPT_URL", EXEC).strip()


def _clave():
    return os.environ.get("RECUENTOS_KEY", "").strip() or CLAVE_FICHERO.read_text().strip()


def _post(tipo, datos):
    req = urllib.request.Request(_url() + "?type=" + tipo, data=json.dumps(datos).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        raise RuntimeError(f"el Apps Script no guardó {tipo}: {res.get('error')}")
    return res


def _filas(csvs):
    for _, texto in csvs:
        for r in csv.DictReader(io.StringIO(texto)):
            n = str(r.get("Número de Mantenimiento") or "").strip()
            if n:
                yield n, r


def cuadrante():
    """{matrícula: fila del cuadrante} (JDE, nombre) desde ?type=recuentos."""
    url = _url() + "?type=recuentos&token=" + os.environ["RECUENTOS_APP_TOKEN"].strip()
    with urllib.request.urlopen(url, timeout=180) as r:
        return {f["Matricula"].strip().upper(): f for f in csv.DictReader(io.StringIO(r.read().decode()))
                if f.get("Matricula")}


def lista_8(csvs, gente):
    """Mantenimientos con técnico y no cancelados: [{mat, tecnico, jde, n, tipo, ts, orden}]."""
    out = []
    for n, r in _filas(csvs):
        mat = str(r.get("Técnico") or "").strip().upper()
        if not mat or r.get("Estado TOA") == "Cancelado":
            continue
        g = gente.get(mat, {})
        out.append({"mat": mat, "n": n, "jde": (g.get("JDE") or "?").strip().upper(),
                    "tecnico": f"{g.get('Nombre(S)', '')} {g.get('Apellidos(S)', '')}".strip(),
                    "tipo": r.get("Tipo de Actividad") or "",
                    "ts": r.get("Timeslot") or r.get("Ventana de Servicio") or "",
                    "orden": r.get("Orden en la Agenda") or ""})
    return out


def subir_lista(dia_iso, lista):
    return _post("agenda-hoy", {"key": _clave(), "dia": dia_iso, "filas": lista})


def guardar_foto(dia_iso, lista):
    """Copia local (sin datos de clientes) para compararla con el Excel de Verisure."""
    if FOTO_DIR.parent.exists():
        FOTO_DIR.mkdir(exist_ok=True)
        (FOTO_DIR / f"{dia_iso}.json").write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")


def estados(csvs):
    """{numero: [estado, hora de inicio (prevista si está pendiente), matrícula]}"""
    out = {}
    for n, r in _filas(csvs):
        e = str(r.get("Estado TOA") or "").strip()
        out[n] = [ESTADOS.get(e, "?"), str(r.get("Hora de Inicio") or "").strip()[:5],
                  str(r.get("Técnico") or "").strip().upper()]
    return out


def _sesion(ruta, subir=False):
    """Sesión de la consola guardada en S3 (como la de la app OV), para no entrar con Microsoft cada 20 min."""
    from ov_comun import _s3

    cliente, bucket = _s3()
    if not cliente:
        return
    try:
        if subir:
            cliente.upload_file(str(ruta), bucket, CLAVE_S3_SESION, ExtraArgs={"ServerSideEncryption": "AES256"})
        else:
            cliente.download_file(bucket, CLAVE_S3_SESION, str(ruta))
            os.chmod(ruta, 0o600)
    except Exception as e:  # primera vez o sin permiso: se entra con Microsoft
        print(f"[vivo] sesión en S3 ({'subir' if subir else 'bajar'}): {type(e).__name__}")


def main():
    from playwright.sync_api import sync_playwright

    import consola_sso
    from comun_ofs import CARPETA_BASE, LAUNCH_ARGS

    ahora = datetime.now(TZ)
    if ahora.weekday() > 4 or not (8 <= ahora.hour < 19):
        print(f"[vivo] fuera de horario ({ahora:%a %H:%M}): no se hace nada")
        return
    hoy = ahora.date().isoformat()
    ruta = CARPETA_BASE / "sesion_consola.json"
    _sesion(ruta)
    correo, clave = consola_sso.leer_credenciales_sso()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        try:
            context = browser.new_context(viewport={"width": 1600, "height": 1000},
                                          storage_state=str(ruta) if ruta.exists() else None)
            page = context.new_page()
            consola_sso.entrar_a_consola(page, correo, clave)
            csvs = consola_sso.descargar_csv_grupos(page, hoy)
            context.storage_state(path=str(ruta))
            os.chmod(ruta, 0o600)
        finally:
            browser.close()
    _sesion(ruta, subir=True)
    est = estados(csvs)
    if len(csvs) < 10 or len(est) < 100:
        raise RuntimeError(f"descarga incompleta de la consola: {len(csvs)} grupos, {len(est)} mantenimientos")
    hora = datetime.now(TZ).strftime("%H:%M")
    res = _post("agenda-vivo", {"key": _clave(), "dia": hoy, "hora": hora, "estados": est})
    print(f"[vivo] {hoy} {hora}: {res.get('guardados')} estados subidos")
    # Si a las 8:00 el Mac no pudo subir la lista, la sube la primera pasada de la mañana
    if not res.get("lista_hoy") and ahora.hour < 9:
        lista = lista_8(csvs, cuadrante())
        subir_lista(hoy, lista)
        print(f"[vivo] la lista de hoy no estaba: subida desde Oracle ({len(lista)} mantenimientos)")
