"""
Captura diaria de la plantilla de tecnicos (Oracle Field Service). Usa un
usuario DISTINTO al de mantenimientos/ruta (ETADIRECT_USER_CAPTURAS /
ETADIRECT_PASS_CAPTURAS). Solo guarda las capturas en capturas/ -- no envia
correo (eso lo hace enviar_correo_matutino.py, que junta estas capturas con
el Excel de mantenimientos del otro usuario).

Este usuario ya ve solo datos de AURUM por defecto (no hace falta aplicar
el filtro de "Vista" como con el otro usuario). En el panel izquierdo
aparecen los equipos (jefes de equipo, ver lista EQUIPOS mas abajo); hay
que hacer clic en cada uno, en orden, y tomar una captura de pantalla
completa por cada uno.

Variables de entorno requeridas:
  ETADIRECT_USER_CAPTURAS   Usuario de la consola de despacho (para capturas)
  ETADIRECT_PASS_CAPTURAS   Contraseña de ese usuario

Uso manual (para probar):
  python tomar_capturas.py

Programacion diaria: ver README.md (Task Scheduler), un poco antes de las
7:30am para que enviar_correo_matutino.py encuentre las capturas listas.
"""

import sys
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from comun_ofs import CARPETA_BASE, LAUNCH_ARGS, ruta_sesion, leer_credenciales_ofs, abrir_sesion_ofs, registrar_error

# ── Configuracion ──────────────────────────────────────────────────────────

CARPETA_CAPTURAS = CARPETA_BASE / "capturas"
ARCHIVO_SESION = ruta_sesion("capturas")

# Los equipos del panel izquierdo, en el orden en que hay que capturarlos.
# Se busca por el nombre porque es la parte estable del texto -- el codigo
# delante (BCN-286800, MD-273371, etc) tiene formato inconsistente en
# distintas filas.
#
# "Jose Luis Osorio" se renombro a "GD5381-TF - Gustavo Perez" en la
# consola (visto en vivo el 2026-08-25) -- mismo equipo, nombre nuevo.
# Christian Alexander Reyna y Carlos Enrique Marcano Mora se agregaron
# como equipos nuevos (visto en vivo el 2026-09-08), al final de la lista.
EQUIPOS = [
    "Gustavo Perez",
    "Ezequiel Pugliese",
    "Armando Jose Madrid",
    "Humberto Chacon",
    "Pablo Marques",
    "Carlos Enrique Pernas Ortiz",
    "Manuel Enrique Sequeira",
    "Maykel Ramon Gutierrez",
    "Fernando David Alves Andujar",
    "Christian Alexander Reyna",
    "Carlos Enrique Marcano Mora",
]


def _encontrar_equipo_visible(page, nombre, intentos=15):
    """
    Busca `nombre` en la pagina y devuelve la coincidencia que esta
    VISIBLE -- no la primera del DOM sin mas.

    Confirmado en vivo (2026-09-08): ademas de la entrada real y visible
    del panel izquierdo, puede haber varias copias OCULTAS del mismo
    nombre en otras partes de la pagina -- filas "JEE-..." (Jefe de
    Equipo) en el panel de tecnicos de la derecha, mientras que la entrada
    real del panel izquierdo es la que empieza con "JR9426-..." (o
    "GD5381-TF - ..." para el caso especial de Gustavo Perez). Tomar
    simplemente el primer resultado del DOM (`.first`) agarra cualquiera
    de esas copias ocultas segun el orden en que aparezcan, no
    necesariamente la real -- por eso se recorren TODAS las coincidencias
    buscando una visible, con scroll de rueda de mouse entre intento e
    intento por si la real esta mas abajo en una lista larga.
    """
    candidatos = page.get_by_text(nombre, exact=False)
    for _ in range(intentos):
        for i in range(candidatos.count()):
            candidato = candidatos.nth(i)
            if candidato.is_visible():
                return candidato
        page.mouse.move(200, 400)
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(300)

    # Ninguna coincidencia se volvio visible -- diagnostico antes de
    # devolver la primera igual, para que el error normal de Playwright
    # (al intentar clickearla) tenga contexto util en el log.
    try:
        n = candidatos.count()
        print(f"[diagnostico] Coincidencias de '{nombre}' en la pagina: {n}")
        for i in range(min(n, 5)):
            try:
                visible = candidatos.nth(i).is_visible()
                html = candidatos.nth(i).evaluate("el => el.outerHTML")
                print(f"[diagnostico] match #{i} (visible={visible}): {html!r}")
            except Exception as e_diag:
                print(f"[diagnostico] Error leyendo match #{i}: {e_diag}")
    except Exception as e_diag:
        print(f"[diagnostico] Error buscando coincidencias de '{nombre}': {e_diag}")

    return candidatos.first


def tomar_capturas(page):
    """
    Hace clic en cada uno de los equipos del panel izquierdo (en el
    orden de EQUIPOS) y toma una captura de pantalla completa por cada
    uno, esperando a que la vista termine de cargar antes de capturar.
    """
    CARPETA_CAPTURAS.mkdir(exist_ok=True)
    fecha = datetime.now().strftime("%Y-%m-%d")

    page.wait_for_selector(".toaGantt-provTree", timeout=60000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    rutas = []
    for numero, nombre in enumerate(EQUIPOS, start=1):
        equipo = _encontrar_equipo_visible(page, nombre)
        equipo.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        ruta = CARPETA_CAPTURAS / f"plantilla_{fecha}_{numero}.png"
        page.screenshot(path=str(ruta))
        rutas.append(ruta)

    return rutas


def main():
    usuario, clave = leer_credenciales_ofs("_CAPTURAS")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)

        # Ventana grande para que se vean mas horas en cada captura (de 7 a
        # 23 o mas, a pantalla completa).
        if ARCHIVO_SESION.exists():
            context = browser.new_context(
                storage_state=str(ARCHIVO_SESION), viewport={"width": 1920, "height": 1080}
            )
        else:
            context = browser.new_context(viewport={"width": 1920, "height": 1080})

        page = context.new_page()

        try:
            abrir_sesion_ofs(context, page, usuario, clave, ARCHIVO_SESION)
            rutas_capturas = tomar_capturas(page)
        except PlaywrightTimeoutError as e:
            registrar_error("tomar_capturas", f"la pagina tardo demasiado o no encontro un elemento esperado: {e}")
            CARPETA_CAPTURAS.mkdir(exist_ok=True)
            page.screenshot(path=str(CARPETA_CAPTURAS / "error_debug.png"))
            # Diagnostico: el screenshot queda en /tmp de Lambda, inaccesible
            # desde CloudWatch -- imprimir URL y texto visible es lo unico
            # que sale en el log para saber en que pantalla se quedo.
            try:
                print(f"[diagnostico] URL al momento del error: {page.url}")
                print(f"[diagnostico] Texto visible (primeros 1000 caracteres): {page.locator('body').inner_text()[:1000]!r}")
            except Exception as e_diag:
                print(f"[diagnostico] No se pudo leer URL/texto de la pagina: {e_diag}")
            sys.exit(1)
        finally:
            browser.close()

    print(f"Listo: {len(rutas_capturas)} capturas guardadas en {CARPETA_CAPTURAS}")


if __name__ == "__main__":
    main()
