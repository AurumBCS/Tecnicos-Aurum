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


# ── Avisos push (17/11/2026) ─────────────────────────────────────────────────
# Con los estados de cada pasada se deciden los avisos y se mandan a Render (confirmaciones-sms/push.js),
# que los entrega a quien los tenga activados en la app y no repite ninguno en el día:
#  - técnico: mantenimiento Iniciado que tiene sugerencias de RM (las de la ruta, ?type=ruta-sugerencias);
#  - JE: mantenimiento Pendiente de su equipo en riesgo (Oracle prevé empezar después del fin de la franja)
#    o fuera de franja (ya pasó el fin y sigue sin empezar). Mismo criterio que "Cumplimiento de hoy".
# Sin datos de clientes. Si algo falla aquí, el Cumplimiento en vivo sigue igual.
PUSH_URL = os.environ.get("PUSH_URL", "https://tecnicos-aurum.onrender.com/push/avisos")
# Prueba con Gustavo (17/11/2026): los avisos del equipo de 302154 (que lleva él) le llegan también a GD5381
PUSH_COPIAS = {"302154": "GD5381"}


def sugerencias_rm(dia_iso):
    """{numero: (alertas, hacer)} de los mantenimientos de ese día con alertas de RM."""
    url = _url() + "?type=ruta-sugerencias&token=" + os.environ["RECUENTOS_APP_TOKEN"].strip()
    with urllib.request.urlopen(url, timeout=120) as r:
        filas = csv.DictReader(io.StringIO(r.read().decode()))
        return {f["numero"].strip(): (f.get("alertas") or "", f.get("hacer") or "")
                for f in filas if f.get("fecha") == dia_iso and (f.get("alertas") or "").strip()}


def _franja(ts):
    import re
    m = re.search(r"(\d{1,2})\D+(\d{1,2})", str(ts or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _min(h):
    import re
    m = re.match(r"^(\d{1,2}):(\d{2})", str(h or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _corta(texto, n):
    partes = [p.strip() for p in str(texto or "").split("||") if p.strip()]
    t = "; ".join(partes[:2]) + (f" (+{len(partes) - 2})" if len(partes) > 2 else "")
    return t if len(t) <= n else t[:n - 1] + "…"


def avisos(csvs, gente, sugerencias, ahora):
    """Lista de avisos [{mat, id, titulo, cuerpo}] para esta pasada."""
    out = []
    ahora_min = ahora.hour * 60 + ahora.minute
    for n, r in _filas(csvs):
        e = ESTADOS.get(str(r.get("Estado TOA") or "").strip(), "?")
        mat = str(r.get("Técnico") or "").strip().upper()
        tipo = str(r.get("Tipo de Actividad") or "").strip()
        ts = str(r.get("Timeslot") or r.get("Ventana de Servicio") or "").strip()
        if not mat:
            continue
        g = gente.get(mat) or {}
        je = str(g.get("JDE") or "").strip().upper()
        nombre = f"{g.get('Nombre(S)', '')} {g.get('Apellidos(S)', '')}".strip() or mat
        copia = PUSH_COPIAS.get(je)
        if e == "I" and n in sugerencias:
            alertas, hacer = sugerencias[n]
            out.append({"mat": mat, "id": "rm:" + n, "titulo": f"⚠️ Riesgo de RM · {tipo or 'Mto'} {n}",
                        "cuerpo": _corta(alertas, 140).rstrip(".") + (f". Revisa: {_corta(hacer, 140)}" if hacer.strip() else "")})
            if copia:
                out.append(dict(out[-1], mat=copia, id="copia-rm:" + n, titulo=f"⚠️ RM · {nombre} · {tipo or 'Mto'} {n}"))
        f = _franja(ts)
        if e != "P" or not f or not je:
            continue
        ini = _min(str(r.get("Hora de Inicio") or "")[:5])
        antes = len(out)
        if ahora_min >= f[1] * 60:
            out.append({"mat": je, "id": "fuera:" + n, "titulo": f"🔴 Fuera de franja · {nombre}",
                        "cuerpo": f"{tipo or 'Mto'} {n}, franja {f[0]}-{f[1]}h, sin empezar a las {ahora:%H:%M}."})
        elif ini is not None and ini >= f[1] * 60:
            out.append({"mat": je, "id": "riesgo:" + n, "titulo": f"🟠 En riesgo · {nombre}",
                        "cuerpo": f"{tipo or 'Mto'} {n}, franja {f[0]}-{f[1]}h: Oracle prevé empezar a las {str(r.get('Hora de Inicio'))[:5]}."})
        if copia and len(out) > antes:
            out.append(dict(out[-1], mat=copia, id="copia-" + out[-1]["id"]))
    return out


def _vapid():
    """Clave privada de los avisos, derivada de RECUENTOS_KEY (ver confirmaciones-sms/push.js)."""
    import base64
    import hashlib
    d = hashlib.sha256(("aurum-vapid|" + _clave()).encode()).digest()
    return base64.urlsafe_b64encode(d).decode().rstrip("=")


def enviar_avisos(lista):
    # Se llama aunque no haya avisos: así Render recupera la clave tras un redespliegue y no se duerme
    req = urllib.request.Request(PUSH_URL, data=json.dumps({"key": _clave(), "vapid": _vapid(), "avisos": lista}).encode(),
                                 headers={"Content-Type": "application/json"})
    # Render gratis se duerme: la primera petición puede tardar ~1 min en despertarlo
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


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


# ── Hoja de Anna (PETICIONADOR ANNA), 18/11/2026 ─────────────────────────────
# En cada pasada, con los estados ya descargados, se pone el ESTADO de las filas de hoy: Iniciado -> INICIADO,
# Completado -> FINALIZADO, Suspendido/Cancelado/No completado -> SUSPENDIDO. INICIADO se cambia en una pasada
# posterior; lo que haya escrito Anna no se pisa (lo decide el script de la hoja). Las de días anteriores las sigue
# cerrando el barrido de las 8:00 del Mac (huecos/barrido_huecos.py). URL y clave en variables de la Lambda.
ESTADO_HOJA = {"I": "INICIADO", "C": "FINALIZADO", "S": "SUSPENDIDO", "X": "SUSPENDIDO", "N": "SUSPENDIDO"}


def _hoja_anna(datos):
    url, clave = os.environ.get("HUECOS_HOJA_URL", "").strip(), os.environ.get("HUECOS_HOJA_CLAVE", "").strip()
    if not url or not clave:
        return None
    req = urllib.request.Request(url, data=json.dumps(dict(datos, clave=clave)).encode(),
                                 headers={"Content-Type": "text/plain"})
    with urllib.request.urlopen(req, timeout=90) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        raise RuntimeError(f"hoja de Anna: {res.get('error')}")
    return res


def cambios_hoja(filas, est, hoy):
    """Filas de hoy de la hoja (sin ESTADO o con INICIADO) -> cambios a escribir según el estado en Oracle.
    Solo las de hoy: los estados son los de hoy (y un script de la hoja anterior a esta versión devuelve otras)."""
    cambios = []
    for f in filas:
        if f.get("fecha") != hoy:
            continue
        nuevo = ESTADO_HOJA.get((est.get(str(f.get("mto", "")).strip()) or ["?"])[0])
        if nuevo:
            cambios.append({"hoja": f["hoja"], "fila": f["fila"], "mto": f["mto"], "estado": nuevo})
    return cambios


def estados_a_hoja(est, hoy):
    j = _hoja_anna({"accion": "pendientes", "hoy": True})
    if j is None:
        return "sin configurar (HUECOS_HOJA_URL / HUECOS_HOJA_CLAVE)"
    filas = [f for f in j.get("filas", []) if f.get("fecha") == hoy]
    cambios = cambios_hoja(filas, est, hoy)
    if not cambios:
        return f"{len(filas)} filas de hoy abiertas, ningún cambio"
    r = _hoja_anna({"accion": "estados", "cambios": cambios})
    return (f"{len(filas)} filas de hoy abiertas, {r.get('escritas', 0)} escritas"
            + (f", errores: {'; '.join(r.get('errores', [])[:5])}" if r.get("errores") else ""))


def main():
    from playwright.sync_api import sync_playwright

    import consola_sso
    from comun_ofs import CARPETA_BASE, LAUNCH_ARGS

    ahora = datetime.now(TZ)
    if ahora.weekday() > 4 or not (8 <= ahora.hour < 19):
        print(f"[vivo] fuera de horario ({ahora:%a %H:%M}): no se hace nada")
        return
    hoy = ahora.date().isoformat()
    # Entrada nueva en cada pasada y "Cerrar sesión" al acabar (16/11/2026). La sesion guardada en S3 nunca
    # llego a funcionar (sin permiso en el bucket) y Oracle tampoco acepta una sesion copiada a otro navegador:
    # cada pasada abria una sesion nueva y la dejaba abierta, 33 al dia, y Oracle (3 por usuario) echaba a las
    # tareas del Mac a mitad de lectura.
    correo, clave = consola_sso.leer_credenciales_sso()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        page = None
        try:
            page = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
            consola_sso.entrar_a_consola(page, correo, clave)
            csvs = consola_sso.descargar_csv_grupos(page, hoy)
        finally:
            if page is not None:
                consola_sso.cerrar_sesion(page)
            browser.close()
    est = estados(csvs)
    if len(csvs) < 10 or len(est) < 100:
        raise RuntimeError(f"descarga incompleta de la consola: {len(csvs)} grupos, {len(est)} mantenimientos")
    hora = datetime.now(TZ).strftime("%H:%M")
    res = _post("agenda-vivo", {"key": _clave(), "dia": hoy, "hora": hora, "estados": est})
    print(f"[vivo] {hoy} {hora}: {res.get('guardados')} estados subidos")
    try:
        lista = avisos(csvs, cuadrante(), sugerencias_rm(hoy), ahora)
        r = enviar_avisos(lista)
        print(f"[vivo] avisos: {len(lista)} posibles; {r.get('entregados', 0)} entregados, "
              f"{r.get('repetidos', 0)} ya avisados, {r.get('sinAparato', 0)} sin avisos activados"
              + (f" ({r.get('error')})" if r.get("error") else ""))
    except Exception as e:
        print(f"[vivo] avisos no enviados: {type(e).__name__}: {e}")
    try:
        print(f"[vivo] hoja de Anna: {estados_a_hoja(est, hoy)}")
    except Exception as e:
        print(f"[vivo] hoja de Anna no actualizada: {type(e).__name__}: {e}")
    # Si a las 8:00 el Mac no pudo subir la lista, la sube la primera pasada de la mañana
    if not res.get("lista_hoy") and ahora.hour < 9:
        lista = lista_8(csvs, cuadrante())
        subir_lista(hoy, lista)
        print(f"[vivo] la lista de hoy no estaba: subida desde Oracle ({len(lista)} mantenimientos)")
