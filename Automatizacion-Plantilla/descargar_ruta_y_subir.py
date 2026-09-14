"""
Descarga diaria de la ruta (Excel de actividades) del dia siguiente desde
Oracle Field Service y la sube a la app Aurum (confirmaciones-sms) para
que salgan las citas a confirmar.

El Excel se arma exportando bucket por bucket con el usuario de CAPTURAS
(ETADIRECT_USER_CAPTURAS) y pegando todos los .xlsx en uno solo -- ver
`exportar_todos_los_buckets` en comun_ofs.py y la seccion "modo
degradado" del README. (Antes se exportaba de una sola vez con el
usuario de mantenimientos, al que ya no tenemos acceso.)

Regla de fecha: SIEMPRE se descarga la ruta del dia SIGUIENTE a hoy, excepto
que ese dia siguiente caiga domingo, en cuyo caso se salta al lunes. Esto se
hace navegando con las flechas de fecha de la consola (1 o 2 clics hacia
adelante), nunca escribiendo la fecha a mano.

Credenciales: se leen SIEMPRE de variables de entorno (ver README.md).

Variables de entorno requeridas:
  ETADIRECT_USER_CAPTURAS   Usuario de la consola (capturas)
  ETADIRECT_PASS_CAPTURAS   Su contraseña

Uso manual (para probar):
  python descargar_ruta_y_subir.py

Programacion diaria: ver README.md (EventBridge Scheduler).
"""

import sys
from datetime import date, timedelta

import requests
from playwright.sync_api import sync_playwright

from comun_ofs import (
    CARPETA_BASE,
    LAUNCH_ARGS,
    ruta_sesion,
    leer_credenciales_ofs,
    abrir_sesion_ofs,
    exportar_todos_los_buckets,
    registrar_error,
)

# ── Configuracion ──────────────────────────────────────────────────────────

CARPETA_DESCARGAS = CARPETA_BASE / "descargas"
ARCHIVO_SESION = ruta_sesion("capturas")  # mismo usuario que capturas/correo matutino
URL_SUBIDA = "https://tecnicos-aurum.onrender.com/upload"
MATRICULA_SUBIDA = "GD5381"  # uploader autorizado sin filtro (Gustavo Perez)


def calcular_fecha_objetivo():
    """Siempre el dia siguiente a hoy; si ese dia es domingo, salta al lunes."""
    hoy = date.today()
    objetivo = hoy + timedelta(days=1)
    if objetivo.weekday() == 6:  # 6 = domingo
        objetivo += timedelta(days=1)
    return objetivo


def calcular_clics_dia_siguiente(fecha_objetivo):
    # La consola siempre abre en el dia de hoy, asi que basta con contar
    # cuantos dias hay que avanzar (siempre 1 o 2, nunca mas).
    return (fecha_objetivo - date.today()).days


def _localizar_flecha_siguiente(page):
    """
    Localiza el boton de "dia siguiente" de la barra de fecha.

    NO VERIFICADO todavia contra la consola real (ver README.md, seccion
    "Verificar selectores"). Se intentan varias variantes comunes; si
    ninguna funciona hay que inspeccionar el boton real (clic derecho ->
    Inspeccionar) y ajustar la lista de candidatos aqui.
    """
    candidatos = [
        page.get_by_role("button", name="Next"),
        page.get_by_role("button", name="Siguiente"),
        page.locator("[aria-label='Next']"),
        page.locator("[aria-label='Siguiente']"),
        page.locator("[title='Next']"),
        page.locator("[title='Siguiente']"),
        page.locator(".oj-inputdatetime-next-icon"),
    ]
    for candidato in candidatos:
        try:
            if candidato.count() == 1:
                return candidato
        except Exception:
            continue
    raise RuntimeError(
        "No se pudo localizar la flecha de 'dia siguiente' en la barra de "
        "fecha. Hay que inspeccionar el boton en la consola real y ajustar "
        "_localizar_flecha_siguiente() en este script."
    )


def navegar_a_fecha_objetivo(page, fecha_objetivo):
    clics = calcular_clics_dia_siguiente(fecha_objetivo)
    flecha = _localizar_flecha_siguiente(page)
    for _ in range(clics):
        flecha.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)


def subir_excel(ruta_excel):
    with open(ruta_excel, "rb") as f:
        resp = requests.post(
            URL_SUBIDA,
            files={"excel": (ruta_excel.name, f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"matricula": MATRICULA_SUBIDA},
            timeout=60,
        )
    resp.raise_for_status()
    return resp


def main():
    usuario, clave = leer_credenciales_ofs("_CAPTURAS")
    fecha_objetivo = calcular_fecha_objetivo()
    CARPETA_DESCARGAS.mkdir(exist_ok=True)
    ruta_excel = CARPETA_DESCARGAS / f"ruta_{fecha_objetivo.isoformat()}.xlsx"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        context = (
            browser.new_context(
                storage_state=str(ARCHIVO_SESION),
                viewport={"width": 1920, "height": 1080},
            )
            if ARCHIVO_SESION.exists()
            else browser.new_context(viewport={"width": 1920, "height": 1080})
        )
        page = context.new_page()

        try:
            abrir_sesion_ofs(context, page, usuario, clave, ARCHIVO_SESION)
            page.wait_for_selector(".toaGantt-provTree", timeout=60000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            navegar_a_fecha_objetivo(page, fecha_objetivo)

            exportar_todos_los_buckets(
                page, CARPETA_DESCARGAS / "buckets_ruta", ruta_excel
            )
        except Exception as e:
            registrar_error("descargar_ruta_y_subir", f"la pagina tardo demasiado o algo fallo: {e}")
            try:
                page.screenshot(path=str(CARPETA_DESCARGAS / "error_debug.png"))
            except Exception:
                pass
            try:
                print(f"[diagnostico] URL al momento del error: {page.url}")
                print(f"[diagnostico] Texto visible (primeros 1000 caracteres): {page.locator('body').inner_text()[:1000]!r}")
            except Exception as e_diag:
                print(f"[diagnostico] No se pudo leer URL/texto de la pagina: {e_diag}")
            sys.exit(1)
        finally:
            browser.close()

    try:
        resp = subir_excel(ruta_excel)
    except Exception as e:
        registrar_error("descargar_ruta_y_subir", f"fallo al subir el excel al servidor de confirmaciones: {e}")
        sys.exit(1)

    print(
        f"Listo: ruta del {fecha_objetivo.isoformat()} descargada y subida "
        f"(matricula {MATRICULA_SUBIDA}). Respuesta del servidor: {resp.status_code}"
    )


if __name__ == "__main__":
    main()
