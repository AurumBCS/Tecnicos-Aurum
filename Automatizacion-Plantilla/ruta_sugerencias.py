"""
Sugerencias por mantenimiento de la ruta del dia siguiente, para evitar RM.

Se corre desde el Mac (una aprobacion en Authenticator para toda la empresa):
entra en la consola, descarga la ruta de los grupos Aurum (misma regla de
fechas que la descarga de la ruta: de lunes a jueves el dia siguiente, el
viernes sabado y lunes), abre la ficha de cada mantenimiento, aplica
rm_sugerencias.py y manda el resultado al Apps Script (type=ruta-sugerencias),
que lo guarda para que cada tecnico lo vea en la app.

No se guarda nada del cliente: solo matricula del tecnico, numero de
mantenimiento, hora, tipo, panel y las sugerencias.

Uso en el Mac:
  python3 ruta_sugerencias.py                      -> ruta del siguiente dia de trabajo, todos los grupos
  python3 ruta_sugerencias.py --fecha 2026-10-26 --grupo Tenerife
  python3 ruta_sugerencias.py --desde-json <ruta_*.json>   -> recalcula y sube sin entrar en Oracle
Variables: ETADIRECT_PASS, RECUENTOS_SCRIPT_URL, RECUENTOS_KEY.
Copia de las fichas leidas: <RUTA_SUGERENCIAS_DIR>/ruta_<fechas>_<grupo>.json
"""

import argparse
import csv
import io
import json
import os
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from comun_ofs import LAUNCH_ARGS

CARPETA_SALIDA = Path(os.environ.get("RUTA_SUGERENCIAS_DIR", Path(__file__).parent / "ruta_sugerencias"))


def fechas_objetivo(hoy=None):
    """Como descargar_ruta_y_subir.calcular_fechas_objetivo (sin importar requests)."""
    hoy = hoy or datetime.now(ZoneInfo("Europe/Madrid")).date()
    dia = hoy.weekday()
    if dia == 4:
        return [hoy + timedelta(days=1), hoy + timedelta(days=3)]
    if dia == 5:
        return [hoy + timedelta(days=2)]
    return [hoy + timedelta(days=1)]


def _filas_ruta(csvs, fecha_iso):
    out = []
    for nombre, texto in csvs:
        for r in csv.DictReader(io.StringIO(texto)):
            n = str(r.get("Número de Mantenimiento") or "").strip()
            if n:
                out.append({"fecha": fecha_iso, "grupo": nombre, "numero": n,
                            "tecnico": str(r.get("Técnico") or "").strip().upper()})
    return out


def leer_fichas(fechas, filtro_grupo=""):
    import consola_sso
    import ofs_rm_prueba
    from playwright.sync_api import sync_playwright

    correo, clave = consola_sso.leer_credenciales_sso()
    datos, errores, capturas = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        page = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
        try:
            consola_sso.entrar_a_consola(page, correo, clave)
            filas = []
            for f in fechas:
                csvs = [c for c in consola_sso.descargar_csv_grupos(page, f.isoformat())
                        if filtro_grupo.lower() in c[0].lower()]
                filas += _filas_ruta(csvs, f.isoformat())
            print(f"[ruta] {len(filas)} mantenimientos en la ruta de {', '.join(f.isoformat() for f in fechas)}")
            for i, f in enumerate(filas, 1):
                ficha = ofs_rm_prueba._leer(page, f["numero"], capturas, errores)
                datos.append(dict(f, ficha=ficha if isinstance(ficha, dict) else None))
                if i % 25 == 0:
                    print(f"[ruta] {i}/{len(filas)} fichas")
        finally:
            browser.close()
    print(f"[ruta] fichas leidas: {sum(1 for d in datos if d['ficha'])}/{len(datos)} ({len(errores)} errores)")
    return datos


def sugerencias(datos):
    import rm_sugerencias
    filas = []
    for d in datos:
        f = d.get("ficha")
        if not f or not rm_sugerencias.es_mantenimiento(f):
            continue
        hoy = date.fromisoformat(d["fecha"])
        s = rm_sugerencias.sugerir(f, hoy)
        filas.append({"fecha": d["fecha"], "tecnico": d["tecnico"], "numero": d["numero"],
                      "hora": f.get("inicio_fin", ""), "tipo": f.get("tipo", ""), "panel": s["panel"],
                      "alertas": s["alertas"], "hacer": s["hacer"]})
    return filas


def enviar(fechas_iso, filas):
    url = os.environ["RECUENTOS_SCRIPT_URL"].strip() + "?type=ruta-sugerencias"
    datos = {"key": os.environ["RECUENTOS_KEY"].strip(), "fechas": fechas_iso, "filas": filas}
    req = urllib.request.Request(url, data=json.dumps(datos).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        raise RuntimeError("El Apps Script no guardo las sugerencias: " + str(res.get("error")))
    print(f"[ruta] subidas {res.get('guardadas')} sugerencias a la app")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha", action="append", help="yyyy-mm-dd (se puede repetir)")
    ap.add_argument("--grupo", default="", help="solo los grupos que contengan este texto")
    ap.add_argument("--desde-json")
    a = ap.parse_args()

    if a.desde_json:
        datos = json.load(open(a.desde_json, encoding="utf-8"))
        for d in datos:
            d.setdefault("fecha", (a.fecha or [None])[0])
            d["tecnico"] = d["tecnico"].upper()
        fechas_iso = sorted({d["fecha"] for d in datos})
    else:
        fechas = [date.fromisoformat(f) for f in a.fecha] if a.fecha else fechas_objetivo()
        fechas_iso = [f.isoformat() for f in fechas]
        datos = leer_fichas(fechas, a.grupo)
        CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
        copia = CARPETA_SALIDA / f"ruta_{'_'.join(fechas_iso)}_{a.grupo.lower() or 'todos'}.json"
        copia.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[ruta] copia de las fichas en {copia}")

    filas = sugerencias(datos)
    print(f"[ruta] {len(filas)} mantenimientos con sugerencias, {sum(1 for f in filas if f['alertas'])} con alerta")
    enviar(fechas_iso, filas)
