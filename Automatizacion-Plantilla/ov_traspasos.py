"""
Aviso diario de traspasos InterWorker sin completar (lunes a viernes 8:00,
tarea "traspasos_diario" de la Lambda; respaldo a las 9:30).

  1. Entra a la app OV (ov_comun.py) y abre Inventario Transacciones ->
     Transferencia InterWorker -> "A la espera Aceptacion".
  2. Por cada traspaso creado ANTES de hoy entra en su detalle (con el enlace de la
     lista: la pagina exige su suma de control) y saca una captura de la ficha
     (subinventario origen/destino, fecha y articulos). Solo mira: nunca pulsa
     Aceptar ni Rechazar.
  3. Prepara un correo por traspaso y lo manda al Apps Script (tipo "traspasos"),
     que busca en el cuadrante el correo de los dos tecnicos (Para) y de sus jefes
     de equipo (CC), con copia oculta fija a Jose Luis Osorio y Cesar Trujillo.
     Segun TRASPASOS_MODO: enviar / borradores (por defecto) / prueba.
  4. Avisa a Gustavo con el resultado.

Respaldo ({"tarea": "traspasos_diario", "respaldo": true}): si hoy ya se hizo, no hace nada.
Uso local de prueba (sin entrar a OV): python ov_traspasos.py --muestra [--modo prueba]
"""

import base64
import html as _html
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from comun_ofs import CARPETA_BASE, enviar_aviso, registrar_error


def _entrada():
    import ov_comun
    return ov_comun.resumen_entrada()
from ov_recuentos import MODOS, _apps_script, _arg, ya_hecho

TIPO = "traspasos"
LISTA = "view-interworker-transfers?p248_qf_process_status=P&clear=248"
TEXTO = ("Buenos días,\n\nTienen un traspaso sin completar del día {fecha}.\n\n"
         "Por favor, les recuerdo que el procedimiento es hacerlo en digital al mismo momento de entregarlo "
         "en físico. Si tienen alguna duda sobre esto, consúltenlo con su jefe de equipo.\n\n"
         "Un saludo,\nGustavo Perez\nAurum BC Security SL")


def _mat_nombre(subinv):
    """'370886 Abel Lopez' -> ('370886', 'Abel Lopez')."""
    partes = str(subinv or "").strip().split(" ", 1)
    return partes[0].upper(), (partes[1] if len(partes) > 1 else "")


def leer_pendientes(page):
    """Traspasos 'A la espera Aceptacion': [{num, origen, destino, creado (date), href}]."""
    from ov_comun import URL_OV

    sesion = page.evaluate("apex.env.APP_SESSION")
    page.goto(f"{URL_OV}{LISTA}&session={sesion}", wait_until="domcontentloaded")
    page.wait_for_selector(".a-IG", timeout=60000)
    page.wait_for_load_state("networkidle")
    filas = page.evaluate("""async () => {
        const id = document.querySelector('.a-IG').id.replace(/_ig$/, '');
        const m = apex.region(id).call('getViews', 'grid').model;
        await new Promise(res => { if (m.fetchAll) m.fetchAll(s => { if (s.done) res(); }); else res(); setTimeout(res, 20000); });
        const v = (r, p) => { let x = m.getValue(r, p); if (x && typeof x === 'object') x = x.d || x.v; return String(x ?? ''); };
        const out = []; m.forEach(r => out.push({num: v(r, 'TRANSFER_NUM'), origen: v(r, 'FROM_SUBINV'),
                                                 destino: v(r, 'TO_SUBINV'), creado: v(r, 'CREATED')}));
        return out;
    }""")
    # Enlaces al detalle (con su suma de control): estan en las celdas de la tabla; se recorren todas las paginas
    enlaces = {}
    for _ in range(50):
        for a in page.locator(".a-IG a[href*='interworkers-transfer-details']").all():
            enlaces[a.inner_text().strip()] = a.get_attribute("href")
        siguiente = page.locator(".a-IG button.js-pg-next:not([disabled]), .a-IG button[title='Siguiente']:not([disabled])")
        if len(enlaces) >= len(filas) or not siguiente.count():
            break
        siguiente.first.click()
        page.wait_for_load_state("networkidle")
    for f in filas:
        f["creado"] = datetime.strptime(f["creado"].strip()[:10], "%d-%m-%Y").date()
        f["href"] = enlaces.get(f["num"])
    return filas


def captura_detalle(page, href):
    """Abre el detalle del traspaso y devuelve la captura PNG de la ficha (como la de la app)."""
    from ov_comun import URL_OV
    import urllib.parse

    page.goto(urllib.parse.urljoin(URL_OV, href), wait_until="domcontentloaded")
    page.wait_for_selector(".a-IG .a-GV-table", timeout=60000)
    page.wait_for_load_state("networkidle")
    caja = page.evaluate("""() => {
        const etiqueta = [...document.querySelectorAll('body *')].find(e => e.children.length === 0 && e.textContent.trim() === 'Subinventario Origen');
        let ficha = etiqueta;
        while (ficha && !(ficha.innerText.includes('Subinventario Destino') && ficha.innerText.includes('Creada'))) ficha = ficha.parentElement;
        const tabla = document.querySelector('.a-IG');
        const rs = [ficha, tabla].filter(Boolean).map(e => e.getBoundingClientRect());
        const x = Math.min(...rs.map(r => r.left)), y = Math.min(...rs.map(r => r.top));
        return {x: Math.max(0, x - 8), y: Math.max(0, y + window.scrollY - 8),
                width: Math.max(...rs.map(r => r.right)) - x + 16, height: Math.max(...rs.map(r => r.bottom)) - y + 16};
    }""")
    return page.screenshot(clip=caja, full_page=True)


def correo(t, png):
    fecha = t["creado"].strftime("%d/%m/%Y")
    e = _html.escape
    cuerpo = f"""<div style="font-family:Arial,Helvetica,sans-serif;color:#222;max-width:720px">
<p style="font-size:14px">Buenos días,</p>
<p style="font-size:14px">Tienen un traspaso sin completar del día <b>{fecha}</b>.</p>
<p style="font-size:14px">Por favor, les recuerdo que el procedimiento es hacerlo en digital al mismo momento de entregarlo en físico.
Si tienen alguna duda sobre esto, consúltenlo con su jefe de equipo.</p>
<p><img src="cid:captura" alt="Traspaso {e(t['num'])}: {e(t['origen'])} → {e(t['destino'])}"
 style="max-width:100%;border:1px solid #ddd"></p>
<p style="font-size:14px">Un saludo,</p>
<p style="font-size:14px;margin-top:4px">Gustavo Perez<br>Aurum BC Security SL</p></div>"""
    return {
        "jde": t["num"], "nombre": f"{t['origen']} -> {t['destino']}",
        "para": [_mat_nombre(t["origen"])[0], _mat_nombre(t["destino"])[0]],
        "asunto": f"Traspaso sin completar del {fecha} – {t['num']}",
        "html": cuerpo, "texto": TEXTO.format(fecha=fecha),
        "png_b64": base64.b64encode(png).decode(), "archivo": f"Traspaso_{t['num']}.png",
    }


def main(respaldo=False):
    respaldo = respaldo or "--respaldo" in sys.argv
    ahora = datetime.now(ZoneInfo("Europe/Madrid"))
    hoy = ahora.date()
    modo = (_arg("--modo") or os.environ.get("TRASPASOS_MODO") or "borradores").strip()
    if modo not in MODOS:
        raise RuntimeError(f"TRASPASOS_MODO no valido: {modo} (usa {'/'.join(MODOS)})")
    carpeta = CARPETA_BASE / "traspasos" / hoy.isoformat()
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        if ya_hecho(hoy.isoformat(), TIPO) and respaldo:
            print("[traspasos] respaldo: hoy ya se hizo -- no se hace nada")
            return
        if "--muestra" in sys.argv:  # prueba local sin OV: el traspaso de la muestra con una imagen cualquiera
            pendientes = [{"num": "T2385001", "origen": "370886 Abel Lopez", "destino": "281315 Jorge Jhoan Jácome García",
                           "creado": hoy - timedelta(days=1), "png": base64.b64decode(
                               "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")}]
        else:
            from playwright.sync_api import sync_playwright
            from ov_comun import abrir_ov

            with sync_playwright() as p:
                browser, context, page = abrir_ov(p, ver="--ver" in sys.argv)
                try:
                    todos = leer_pendientes(page)
                    print(f"[traspasos] a la espera de aceptacion: {len(todos)}")
                    pendientes = [t for t in todos if t["creado"] < hoy]
                    for t in pendientes:
                        if not t["href"]:
                            raise RuntimeError(f"No encuentro el enlace al detalle de {t['num']}")
                        t["png"] = captura_detalle(page, t["href"])
                        (carpeta / f"{t['num']}.png").write_bytes(t["png"])
                finally:
                    browser.close()
        print(f"[traspasos] de dias anteriores (se avisa): {len(pendientes)}")

        items = [correo(t, t["png"]) for t in pendientes]
        res = _apps_script({"modo": modo, "fecha": hoy.isoformat(), "jefes": items}, TIPO)
        lineas = [f"[{'OK ' if r['ok'] else 'ERR'}] {r['jde']}: para {r.get('para', '')} cc {r.get('cc', '')} {r.get('error', '')}"
                  for r in res["resultado"]]
        print("\n".join(lineas))
        errores = sum(1 for r in res["resultado"] if not r["ok"])
        if items or errores:
            que = {"borradores": "Borradores creados en Gmail", "enviar": "Avisos ENVIADOS",
                   "prueba": "Modo prueba: no se creo ni envio nada"}[modo]
            enviar_aviso(f"Traspasos {hoy:%d/%m}: {len(items)} sin completar" + (f" -- {errores} con error" if errores else ""),
                         _entrada() + f"{que}.\n\n" + "\n".join(lineas))
        if errores:
            sys.exit(1)
    except Exception as e:
        registrar_error("ov_traspasos", str(e))
        siguiente = ("Lanzalo a mano desde Lambda -> Test con {\"tarea\": \"traspasos_diario\"}." if respaldo
                     else "A las 9:30 el respaldo lo intenta otra vez solo.")
        enviar_aviso(f"Traspasos {hoy:%d/%m}: fallo" + (" (respaldo)" if respaldo else ""),
                     f"El aviso de traspasos sin completar fallo:\n\n{e}\n\n{siguiente}")
        raise


if __name__ == "__main__":
    main()
