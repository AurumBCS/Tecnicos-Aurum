"""
Entrada a la app de inventario Order Validation (OV, Oracle APEX), de donde
salen los conteos (recuentos), las devoluciones y demas datos de inventario
de los tecnicos de Aurum (organizacion PESIAU).

Mismo procedimiento que la consola nueva (consola_sso.py): la app redirige a
Oracle Identity -> Microsoft (cuenta de Verisure de Gustavo); se escribe
correo + contraseña y Microsoft muestra un numero de 2 digitos que se le
manda por correo a Gustavo para que lo escriba en Microsoft Authenticator.
Nunca se aprueba nada por cuenta propia.

La sesion se guarda en sesion_ov.json (en /tmp dentro de Lambda) y se
reutiliza mientras siga vigente, para no pedir Authenticator en cada tarea
del mismo arranque.
"""

import os
from urllib.parse import urlparse

import comun_ofs
from comun_ofs import CARPETA_BASE, LAUNCH_ARGS, es_pagina_microsoft, iniciar_sesion_microsoft
from consola_sso import leer_credenciales_sso

URL_OV = "https://sup6goj9xrtj2vv-nextprod.adb.eu-frankfurt-1.oraclecloudapps.com/ords/r/order_validation/ov/"
HOST_OV = urlparse(URL_OV).hostname
ARCHIVO_SESION = CARPETA_BASE / "sesion_ov.json"


def en_ov(page):
    return (urlparse(page.url).hostname or "") == HOST_OV


def abrir_ov(p, ver=False):
    """Devuelve (browser, context, page) ya dentro de la app OV."""
    browser = p.chromium.launch(headless=not ver, args=LAUNCH_ARGS)
    context = browser.new_context(
        storage_state=str(ARCHIVO_SESION) if ARCHIVO_SESION.exists() else None,
        accept_downloads=True, locale="es-ES", viewport={"width": 1400, "height": 900})
    # Sin llaves de acceso (WebAuthn), para que Microsoft ofrezca la contraseña (ver consola_sso.py)
    context.add_init_script(
        "try { delete window.PublicKeyCredential; } catch (e) {}"
        "try { Object.defineProperty(navigator, 'credentials', { get: () => undefined }); } catch (e) {}")
    page = context.new_page()
    page.goto(URL_OV + "home", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    if not en_ov(page):
        print("[ov] sin sesion vigente -> inicio de sesion de Microsoft")
        # Oracle Identity suele redirigir solo a Microsoft; si muestra su pantalla, elegir el acceso de Microsoft
        for _ in range(10):
            if es_pagina_microsoft(page) or en_ov(page):
                break
            for texto in ("Microsoft", "Azure", "Verisure", "SSO"):
                boton = page.get_by_role("button", name=texto)
                if boton.count() and boton.first.is_visible():
                    boton.first.click()
                    break
            page.wait_for_timeout(1500)
        if es_pagina_microsoft(page):
            comun_ofs.MOTIVO_AVISO = "La entrada a la app OV (inventario)"
            correo, clave = leer_credenciales_sso()
            iniciar_sesion_microsoft(page, correo, clave)
        page.wait_for_url(lambda u: (urlparse(u).hostname or "") == HOST_OV, timeout=60000)
        page.wait_for_load_state("domcontentloaded")

    if not en_ov(page):
        raise RuntimeError(f"No se pudo entrar a la app OV. Ultima direccion: {page.url.split('?')[0]}")
    context.storage_state(path=str(ARCHIVO_SESION))
    os.chmod(ARCHIVO_SESION, 0o600)
    print(f"[ov] dentro: {page.title()}")
    return browser, context, page
