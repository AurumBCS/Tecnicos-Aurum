"""
Modo diagnostico de una sola vez. Entra con el usuario de CAPTURAS
(ETADIRECT_USER_CAPTURAS), baja por el panel izquierdo de la consola y
escribe en el log TODOS los nombres de bucket/zona que ve, en orden.

Sirve para armar a mano la lista estatica de buckets a exportar: el
usuario de capturas SI puede exportar, pero solo bucket por bucket (no
hay un export unico como con la cuenta de mantenimientos que ya no
tenemos acceso). Los buckets reales empiezan en "Alicante Benidorm
Aurum" hacia abajo; se saltan los vacios (terminan en "(0)") y todo lo
que diga "pendiente de agendar".

No descarga nada ni manda correo. Correr con {"tarea": "listar_buckets"}
en la pestaña Probar de la Lambda, y pegar el log resultante.
"""

import sys

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from comun_ofs import (
    LAUNCH_ARGS,
    ruta_sesion,
    leer_credenciales_ofs,
    abrir_sesion_ofs,
    registrar_error,
)

ARCHIVO_SESION = ruta_sesion("capturas")


def main():
    usuario, clave = leer_credenciales_ofs("_CAPTURAS")

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

            # Pista sobre la estructura del DOM del panel, por si hay que
            # afinar el selector despues.
            try:
                muestra = page.evaluate(
                    """() => {
                        const el = document.querySelector('.rtl-prov-name');
                        if (!el) return 'no se encontro ningun .rtl-prov-name';
                        const cont = el.closest('div[class]');
                        return cont ? cont.className : '(sin contenedor div con clase)';
                    }"""
                )
                print(f"[buckets] contenedor de .rtl-prov-name: {muestra!r}")
            except Exception as e_diag:
                print(f"[buckets] no se pudo leer el contenedor: {e_diag}")

            # Baja por el panel acumulando los textos visibles en orden, sin
            # duplicar. El panel es virtualizado (recicla los nodos al hacer
            # scroll), por eso se recolecta en cada paso antes de seguir
            # bajando. (200, 400) cae dentro del panel izquierdo.
            vistos = []
            vistos_set = set()
            sin_novedad = 0
            for _ in range(300):
                textos = page.evaluate(
                    """() => Array.from(document.querySelectorAll('.rtl-prov-name'))
                        .filter(el => el.offsetParent !== null)
                        .map(el => el.textContent.trim())
                        .filter(t => t.length > 0)"""
                )
                nuevos = 0
                for t in textos:
                    if t not in vistos_set:
                        vistos_set.add(t)
                        vistos.append(t)
                        nuevos += 1
                if nuevos == 0:
                    sin_novedad += 1
                    if sin_novedad >= 5:
                        break
                else:
                    sin_novedad = 0
                page.mouse.move(200, 400)
                page.mouse.wheel(0, 400)
                page.wait_for_timeout(400)

            print(f"[buckets] === {len(vistos)} entradas vistas en el panel (en orden) ===")
            for i, t in enumerate(vistos):
                print(f"[buckets] [{i:03d}] {t!r}")

            # Sugerencia de lista filtrada: de "Alicante Benidorm" hacia
            # abajo, sin los "(0)" ni los "pendiente".
            try:
                arranque = next(
                    i for i, t in enumerate(vistos)
                    if "alicante benidorm" in t.lower()
                )
            except StopIteration:
                arranque = None

            if arranque is not None:
                candidatos = [
                    t for t in vistos[arranque:]
                    if "(0)" not in t and "pendiente" not in t.lower()
                ]
                print(f"[buckets] === sugerencia: {len(candidatos)} buckets con tecnicos ===")
                for t in candidatos:
                    print(f"[buckets]     {t!r}")
            else:
                print("[buckets] no se encontro 'Alicante Benidorm' en la lista -- revisar el dump de arriba")
        except PlaywrightTimeoutError as e:
            registrar_error(
                "listar_buckets",
                f"la pagina tardo demasiado o no encontro un elemento esperado: {e}",
            )
            sys.exit(1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
