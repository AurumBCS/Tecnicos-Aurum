"""
Prueba de entrada a la app OV (inventario): inicia sesion (con aprobacion en
Authenticator si hace falta) y manda a Gustavo un correo con la captura de la
pagina de inicio y la lista de menus. Sirve para comprobar que el login
funciona en Lambda antes de automatizar las descargas (conteos, devoluciones).

Uso local: python ov_prueba.py [--ver]
"""

import sys

from comun_ofs import enviar_aviso, registrar_error


def main():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, context, page = None, None, None
        try:
            from ov_comun import abrir_ov

            browser, context, page = abrir_ov(p, ver="--ver" in sys.argv)
            page.wait_for_load_state("networkidle")
            menus = page.evaluate(
                "() => [...document.querySelectorAll('#t_TreeNav .a-TreeView-label')]"
                ".map(e => e.textContent.trim()).filter(Boolean)")
            print("[ov] menus:", menus)
            enviar_aviso("App OV: entrada correcta",
                         "Se entro a la app OV de inventario.\n\n" + __import__("ov_comun").resumen_entrada() + "Menus:\n- " + "\n- ".join(menus),
                         captura=page.screenshot(full_page=False))
        except Exception as e:
            registrar_error("ov_prueba", str(e))
            captura = None
            try:
                captura = page.screenshot() if page else None
            except Exception:
                pass
            enviar_aviso("App OV: fallo la entrada", str(e), captura=captura)
            sys.exit(1)
        finally:
            if browser:
                browser.close()


if __name__ == "__main__":
    main()
