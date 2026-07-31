"""
Captura diaria de la plantilla de tecnicos (Oracle Field Service). Usa un
usuario DISTINTO al de mantenimientos/ruta (ETADIRECT_USER_CAPTURAS /
ETADIRECT_PASS_CAPTURAS). Solo guarda las capturas en capturas/ -- no envia
correo (eso lo hace enviar_correo_matutino.py, que junta estas capturas con
el Excel de mantenimientos del otro usuario).

Este usuario ya ve solo datos de AURUM por defecto (no hace falta aplicar
el filtro de "Vista" como con el otro usuario). En el panel izquierdo
aparecen los 9 equipos (jefes de equipo); hay que hacer clic en cada uno,
en orden, y tomar una captura de pantalla completa por cada uno.

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
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from comun_ofs import ruta_sesion, leer_credenciales_ofs, abrir_sesion_ofs, registrar_error

# ── Configuracion ──────────────────────────────────────────────────────────

CARPETA_CAPTURAS = Path(__file__).parent / "capturas"
ARCHIVO_SESION = ruta_sesion("capturas")

# Los 9 equipos del panel izquierdo, en el orden en que hay que capturarlos
# (de "Ezequiel Pugliese" a "Jose Luis Osorio"). Se busca por el nombre
# porque es la parte estable del texto -- el codigo delante (BCN-286800,
# MD-273371, etc) tiene formato inconsistente en distintas filas.
EQUIPOS = [
    "Ezequiel Pugliese",
    "Armando Jose Madrid",
    "Humberto Chacon",
    "Pablo Marques",
    "Carlos Enrique Pernas Ortiz",
    "Manuel Enrique Sequeira",
    "Maykel Ramon Gutierrez",
    "Fernando David Alves Andujar",
    "Jose Luis Osorio",
]


def tomar_capturas(page):
    """
    Hace clic en cada uno de los 9 equipos del panel izquierdo (en el
    orden de EQUIPOS) y toma una captura de pantalla completa por cada
    uno, esperando a que la vista termine de cargar antes de capturar.
    """
    CARPETA_CAPTURAS.mkdir(exist_ok=True)
    fecha = datetime.now().strftime("%Y-%m-%d")

    page.wait_for_selector(".toaGantt-provTree", timeout=30000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    rutas = []
    for numero, nombre in enumerate(EQUIPOS, start=1):
        equipo = page.get_by_text(nombre, exact=False).first
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
        browser = p.chromium.launch(headless=True)

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
            sys.exit(1)
        finally:
            browser.close()

    print(f"Listo: {len(rutas_capturas)} capturas guardadas en {CARPETA_CAPTURAS}")


if __name__ == "__main__":
    main()
