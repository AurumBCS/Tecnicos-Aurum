"""
Pre-conteo: stock del sistema de cada técnico con un conteo PERIÓDICO pendiente (creado y aún vacío,
"Entrada Pendiente" en Counts -> Ver Conteos), para que su jefe de equipo cuente el coche en la app
(Mi equipo -> Pre-conteo), vea el descuadre exacto y qué dejarle o quitarle para quedar en ±100 €.

  1. Entra a la app OV (ov_comun.abrir_ov: reutiliza la sesión de la tarea de traspasos de las 8:00).
  2. Lee los conteos periódicos en "Entrada Pendiente" (sin los técnicos de baja en el cuadrante).
  3. Para cada técnico: Technicians/Installers -> Manage Subinventories (organización PESIAU o PESIAT,
     trabajador = matrícula, Buscar, pulsar el importe de "Valor Stock") -> Acciones -> Descargar -> CSV.
     Bueno y DF, con importe y cantidad (precio = importe / cantidad).
  4. Órdenes por recibir (Recibir TOs) y traspasos por aceptar de esos técnicos (los tiene que dejar hechos
     antes del recuento).
  5. Lo sube al Apps Script (?type=preconteo-stock) con la descripción de cada referencia
     (items_catalogo.json, sacado de los conteos ya hechos) y el jefe de equipo de cada técnico.
  6. Resumen a Gustavo.

Conteos no planificados: cargar_lista(mats) hace lo mismo con una lista de matrículas (Gustavo la pega en la
app, tarjeta Pre-conteo). Con conteo creado usa su código; si no, uno provisional MANUAL-<matrícula>.

Uso local:  python3 ov_preconteo.py [--modo prueba] [--mat 318921 --org PESIAU]   (prueba: no sube nada)
            python3 ov_preconteo.py [--modo prueba] --lista "356444 LQ1546"
Variables: RECUENTOS_SCRIPT_URL, RECUENTOS_APP_TOKEN, RECUENTOS_KEY y las del login.
"""

import csv
import io
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from comun_ofs import CARPETA_BASE, enviar_aviso, registrar_error

AQUI = Path(__file__).parent
CARPETA = CARPETA_BASE / "preconteo"
REASIGNAR_JDE = {"302154": "GD5381"}  # técnicos de Nicola Morsa -> Gustavo Pérez
GRID = """async () => {
    const id = document.querySelector('.a-IG').id.replace(/_ig$/, '');
    const m = apex.region(id).call('getViews', 'grid').model;
    await new Promise(res => { m.fetchAll(s => { if (s.done) res(); }); setTimeout(res, 25000); });
    const v = (r, p) => { let x = m.getValue(r, p); if (x && typeof x === 'object') x = x.d || x.v; return String(x ?? ''); };
    const out = []; m.forEach(r => { const o = {}; COLS.forEach(c => o[c] = v(r, c)); out.push(o); });
    return out;
}"""


def _arg(nombre):
    return sys.argv[sys.argv.index(nombre) + 1] if nombre in sys.argv else None


def _num(s):
    s = str(s or "").strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _tabla(page, ruta, cols):
    from ov_comun import URL_OV
    sesion = page.evaluate("apex.env.APP_SESSION")
    page.goto(f"{URL_OV}{ruta}{'&' if '?' in ruta else '?'}session={sesion}", wait_until="domcontentloaded")
    page.wait_for_selector(".a-IG", timeout=60000)
    page.wait_for_load_state("networkidle")
    return page.evaluate(GRID.replace("COLS", json.dumps(cols)))


def conteos_pendientes(page):
    filas = _tabla(page, "view-counts", ["CODE", "COUNT_TYPE", "ORG_CODE", "TECHNICIAN", "CREATED", "STATUS", "STOCK_VAL_CURR"])
    out = []
    for f in filas:
        if f["STATUS"] == "Entrada Pendiente" and f["COUNT_TYPE"].startswith("Peri"):
            mat, _, nombre = f["TECHNICIAN"].partition(" ")
            if mat.upper() != "GE":
                out.append({"conteo": f["CODE"], "org": f["ORG_CODE"], "mat": mat.upper(), "nombre": nombre.strip(),
                            "creado": f["CREATED"], "stock_conteo": f["STOCK_VAL_CURR"].strip()})
    return out


def pendientes_por_tecnico(page):
    """{matricula: ["TO 4875099 enviada 08-10-2026", "Traspaso T2385001 (recibir)", ...]}"""
    p = {}
    for f in _tabla(page, "view-tos?p297_qf_process_status=P&clear=CR,297", ["CODE", "DELIVERY_WORKER", "SHIPPED_DATE", "LINES"]):
        p.setdefault(f["DELIVERY_WORKER"].upper(), []).append(f"Orden {f['CODE']} enviada el {f['SHIPPED_DATE']} sin recibir ({f['LINES']} líneas)")
    for f in _tabla(page, "view-interworker-transfers?p248_qf_process_status=P&clear=248", ["TRANSFER_NUM", "FROM_SUBINV", "TO_SUBINV", "CREATED"]):
        o, d = f["FROM_SUBINV"].split(" ")[0].upper(), f["TO_SUBINV"].split(" ")[0].upper()
        p.setdefault(d, []).append(f"Traspaso {f['TRANSFER_NUM']} de {o} sin aceptar (creado {f['CREATED'][:10]})")
        p.setdefault(o, []).append(f"Traspaso {f['TRANSFER_NUM']} a {d} sin aceptar por el otro técnico")
    return p


def stock_tecnico(page, org, mat):
    """Lineas del informe Valor Stock: [{sub, item, cant, importe}]."""
    from ov_comun import URL_OV
    page.goto(URL_OV + "home", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    enlace = page.evaluate("""() => { const ad = $('#t_TreeNav').treeView('getNodeAdapter'); let l = null;
        const w = n => { for (let i = 0; i < ad.childCount(n); i++) { const c = ad.child(n, i);
            if (c.link && /manage-subinventories/.test(c.link)) l = c.link; w(c); } }; w(ad.root()); return l; }""")
    page.goto(urllib.parse.urljoin(URL_OV, enlace), wait_until="domcontentloaded")
    page.wait_for_selector("#P103_WORKER", state="attached", timeout=60000)
    page.wait_for_load_state("networkidle")
    nombre_org = "PESIAT Partner Technicians AURUM TENERIFE" if org == "PESIAT" else "PESIAU Partner Technicians AURUM"
    page.evaluate(f"apex.item('P103_ORG_CODE').setValue('{org}', '{nombre_org}')")
    page.wait_for_timeout(1200)
    page.evaluate(f"apex.item('P103_WORKER').setValue('{mat}', '{mat}')")
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Buscar").click()
    # Hay dos enlaces "stock_value" y solo uno trae el importe: esperar a ese y pulsarlo
    page.wait_for_function("() => [...document.querySelectorAll('a.stock_value')].some(a => a.innerText.trim() !== '')", timeout=60000)
    valor = page.evaluate("""() => { const a = [...document.querySelectorAll('a.stock_value')].find(a => a.innerText.trim() !== '');
                                      a.click(); return a.innerText.trim(); }""")
    page.wait_for_selector(".a-IRR-container tbody tr td", timeout=60000)
    page.wait_for_load_state("networkidle")
    page.locator(".a-IRR-container .a-IRR-button--actions").first.click()
    page.locator(".icon-irr-download").first.click()
    dlg = page.locator(".ui-dialog:visible").filter(has_text="Descargar").last
    dlg.locator("[data-value='CSV']").first.click()
    with page.expect_download(timeout=120000) as d:
        dlg.get_by_role("button", name="Descargar").click()
    destino = CARPETA / f"stock_{mat}.csv"
    d.value.save_as(str(destino))
    texto = destino.read_text(encoding="utf-8-sig")
    lineas = [{"sub": r["Subinventario"].strip(), "item": r["Item"].strip(), "importe": _num(r["Importe"]), "cant": _num(r["Cantidad"])}
              for r in csv.DictReader(io.StringIO(texto), delimiter=";") if r.get("Item")]
    print(f"[preconteo] {mat}: {len(lineas)} líneas, valor {valor} (importe suma {sum(l['importe'] for l in lineas):.2f})")
    return lineas, valor


def _cuadrante():
    """(jefe de equipo de cada matrícula, matrículas de baja) desde el cuadrante completo (?type=recuentos)."""
    url = os.environ["RECUENTOS_SCRIPT_URL"].strip() + "?type=recuentos&token=" + os.environ["RECUENTOS_APP_TOKEN"].strip()
    with urllib.request.urlopen(url, timeout=120) as r:
        filas = list(csv.DictReader(io.StringIO(r.read().decode())))
    jefes = {f["Matricula"].strip().upper(): REASIGNAR_JDE.get(f["JDE"].strip().upper(), f["JDE"].strip().upper())
             for f in filas if f.get("Matricula")}
    # De baja: con fecha en "F Baja" o jerarquía "99 BAJA" (01/11: de momento no entran en el pre-conteo)
    bajas = {f["Matricula"].strip().upper() for f in filas if f.get("Matricula")
             and ((f.get("F Baja") or "").strip() or "BAJA" in (f.get("Jerarquia") or "").upper())}
    return jefes, bajas


def _subir(fecha, tecnicos, catalogo):
    datos = {"key": os.environ["RECUENTOS_KEY"].strip(), "fecha": fecha, "tecnicos": tecnicos, "catalogo": catalogo}
    req = urllib.request.Request(os.environ["RECUENTOS_SCRIPT_URL"].strip() + "?type=preconteo-stock",
                                 data=json.dumps(datos).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        res = json.loads(r.read().decode())
    if not res.get("ok"):
        raise RuntimeError("Apps Script: " + str(res.get("error")))
    return res


def _nombre_tecnico(mat):
    url = os.environ["RECUENTOS_SCRIPT_URL"].strip() + "?type=recuentos&token=" + os.environ["RECUENTOS_APP_TOKEN"].strip()
    with urllib.request.urlopen(url, timeout=120) as r:
        for f in csv.DictReader(io.StringIO(r.read().decode())):
            if f.get("Matricula", "").strip().upper() == mat:
                return f"{f.get('Nombre(S)', '').strip()} {f.get('Apellidos(S)', '').strip()}".strip()
    return ""


def cargar_lista(mats, modo="subir"):
    """Pre-conteo de las matrículas pedidas. Una que falle no para las demás; cada una se sube al terminarla."""
    from playwright.sync_api import sync_playwright
    from ov_comun import abrir_ov

    hoy = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d")
    mats = list(dict.fromkeys(str(m).strip().upper() for m in mats if str(m).strip()))
    CARPETA.mkdir(parents=True, exist_ok=True)
    catalogo = json.loads((AQUI / "items_catalogo.json").read_text(encoding="utf-8"))
    cat = {k: {"d": v.get("d", ""), "p": v.get("p", 0)} for k, v in catalogo.items()}
    bien, mal = [], []
    try:
        jefes, bajas = _cuadrante()
        with sync_playwright() as p:
            browser, context, page = abrir_ov(p, ver="--ver" in sys.argv)
            try:
                reales = {c["mat"]: c for c in conteos_pendientes(page)}
                pend = pendientes_por_tecnico(page)
                for mat in mats:
                    try:
                        if not jefes.get(mat):
                            raise RuntimeError("no tiene jefe de equipo en el cuadrante")
                        if mat in bajas:
                            raise RuntimeError("está de baja en el cuadrante")
                        c = reales.get(mat) or {"conteo": f"MANUAL-{mat}", "org": "PESIAU", "mat": mat,
                                                "nombre": _nombre_tecnico(mat), "creado": hoy}
                        try:
                            c["lineas"], c["valor"] = stock_tecnico(page, c["org"], mat)
                        except Exception:
                            if mat in reales:
                                raise
                            c["org"] = "PESIAT"  # sin conteo no se sabe la organización: Tenerife si no sale en la península
                            c["lineas"], c["valor"] = stock_tecnico(page, c["org"], mat)
                        c["je"], c["pendientes"] = jefes[mat], pend.get(mat, [])
                        for l in c["lineas"]:
                            l["desc"] = catalogo.get(l["item"], {}).get("d", "")
                            if l["cant"]:
                                cat.setdefault(l["item"], {"d": l["desc"], "p": 0})["p"] = round(l["importe"] / l["cant"], 4)
                        if modo != "prueba":
                            _subir(hoy, [c], cat)
                        bien.append(f"- {c['conteo']} {mat} {c['nombre']} (JE {c['je']}): {len(c['lineas'])} líneas, "
                                    f"valor {c['valor']}; pendientes: {len(c['pendientes'])}")
                    except Exception as e:
                        print(f"[preconteo] {mat}: {e}")
                        mal.append(f"- {mat}: {str(e).splitlines()[0][:150]}")
            finally:
                browser.close()
        texto = (("Stock subido a la app (Mi equipo -> Pre-conteo), visible solo hoy:\n\n" + "\n".join(bien)) if bien else "No se cargó ninguna.") \
            + (("\n\nNo se pudieron cargar:\n" + "\n".join(mal)) if mal else "")
        if modo == "prueba":
            print(texto)
            return
        enviar_aviso(("⚠️ " if mal else "") + f"Pre-conteo no planificado: {len(bien)} de {len(mats)} cargados", texto)
    except Exception as e:
        registrar_error("ov_preconteo", str(e))
        enviar_aviso("Pre-conteo no planificado: fallo", f"No se pudo cargar la lista {', '.join(mats)}:\n\n{e}")
        raise
    finally:
        shutil.rmtree(CARPETA, ignore_errors=True)


def main(modo=None):
    from playwright.sync_api import sync_playwright
    from ov_comun import abrir_ov

    modo = modo or _arg("--modo") or os.environ.get("PRECONTEO_MODO", "subir")
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d")
    CARPETA.mkdir(parents=True, exist_ok=True)
    catalogo = json.loads((AQUI / "items_catalogo.json").read_text(encoding="utf-8"))
    try:
        jefes, bajas = _cuadrante()
        with sync_playwright() as p:
            browser, context, page = abrir_ov(p, ver="--ver" in sys.argv)
            try:
                if _arg("--mat"):
                    conteos = [{"conteo": "PRUEBA", "org": _arg("--org") or "PESIAU", "mat": _arg("--mat").upper(),
                                "nombre": "", "creado": "", "stock_conteo": ""}]
                else:
                    conteos = conteos_pendientes(page)
                    for c in [c for c in conteos if c["mat"] in bajas]:
                        print(f"[preconteo] {c['conteo']} {c['mat']} {c['nombre']}: de baja en el cuadrante, no se sube")
                    conteos = [c for c in conteos if c["mat"] not in bajas]
                print(f"[preconteo] conteos periódicos pendientes: {len(conteos)}")
                pend = pendientes_por_tecnico(page) if conteos else {}
                for c in conteos:
                    c["lineas"], c["valor"] = stock_tecnico(page, c["org"], c["mat"])
                    for l in c["lineas"]:
                        info = catalogo.get(l["item"], {})
                        l["desc"] = info.get("d", "")
                    c["je"] = jefes.get(c["mat"], "")
                    c["pendientes"] = pend.get(c["mat"], [])
            finally:
                browser.close()
        # catálogo para referencias que el JE añada y no estén en el sistema del técnico
        cat = {k: {"d": v.get("d", ""), "p": v.get("p", 0)} for k, v in catalogo.items()}
        for c in conteos:
            for l in c["lineas"]:
                if l["cant"]:
                    cat.setdefault(l["item"], {"d": l.get("desc", ""), "p": 0})["p"] = round(l["importe"] / l["cant"], 4)
        lineas_txt = [f"- {c['conteo']} {c['mat']} {c['nombre']} (JE {c['je'] or '?'}): {len(c['lineas'])} líneas, "
                      f"valor {c['valor']}; pendientes: {len(c['pendientes'])}" for c in conteos]
        if modo == "prueba":
            print("\n".join(lineas_txt) or "Sin conteos pendientes")
            (CARPETA / "preconteo.json").write_text(json.dumps({"tecnicos": conteos, "catalogo": cat}, ensure_ascii=False, indent=1), encoding="utf-8")
            return
        if conteos:
            _subir(hoy, conteos, cat)
        enviar_aviso(f"Pre-conteo {hoy}: {len(conteos)} técnico(s)",
                     ("Stock subido a la app (Mi equipo -> Pre-conteo):\n\n" + "\n".join(lineas_txt)) if conteos
                     else "Hoy no hay conteos periódicos pendientes.")
    except Exception as e:
        registrar_error("ov_preconteo", str(e))
        enviar_aviso(f"Pre-conteo {hoy}: fallo", f"No se pudo preparar el pre-conteo:\n\n{e}")
        raise


if __name__ == "__main__":
    if _arg("--lista"):
        cargar_lista(re.split(r"[\s,;]+", _arg("--lista")), _arg("--modo") or "subir")
    else:
        main()
