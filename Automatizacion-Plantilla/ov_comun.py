"""
Entrada a la app de inventario Order Validation (OV, Oracle APEX), de donde
salen los conteos (recuentos), las devoluciones y demas datos de inventario
de los tecnicos de Aurum (organizacion PESIAU).

Mismo procedimiento que la consola nueva (consola_sso.py): la app redirige a
Oracle Identity -> Microsoft (cuenta de Verisure de Gustavo); se escribe
correo + contraseña y Microsoft muestra un numero de 2 digitos que se le
manda por correo a Gustavo para que lo escriba en Microsoft Authenticator.
Nunca se aprueba nada por cuenta propia.

La sesion (cookies de Microsoft, Oracle Identity y la app) se guarda en
sesion_ov.json y se reutiliza mientras siga vigente, igual que hace un
navegador normal: si Microsoft la acepta, se entra sin pedir Authenticator.
En Lambda /tmp se borra entre ejecuciones, asi que si existe la variable
SESION_BUCKET el archivo se baja de / se sube a s3://<SESION_BUCKET>/sesion_ov.json
(bucket privado y cifrado; el rol de la Lambda solo puede leer/escribir ese archivo).
Ese archivo equivale a una sesion abierta de la cuenta: nunca se comparte ni se sube a otro sitio.
"""

import os
from urllib.parse import urlparse

import comun_ofs
from comun_ofs import CARPETA_BASE, LAUNCH_ARGS, es_pagina_microsoft, iniciar_sesion_microsoft
from consola_sso import leer_credenciales_sso

URL_OV = "https://sup6goj9xrtj2vv-nextprod.adb.eu-frankfurt-1.oraclecloudapps.com/ords/r/order_validation/ov/"
HOST_OV = urlparse(URL_OV).hostname
ARCHIVO_SESION = CARPETA_BASE / "sesion_ov.json"
CLAVE_S3 = "sesion_ov.json"
# Como entro la ultima vez abrir_ov(): "sesion guardada" o "Authenticator" (se cuenta en los avisos)
ULTIMA_ENTRADA = ""


def resumen_entrada():
    """Linea para los avisos: si se entro sin pedir Authenticator (sesion guardada) o con el."""
    return f"Entrada a la app OV: {ULTIMA_ENTRADA}\n\n" if ULTIMA_ENTRADA else ""


def _s3():
    bucket = os.environ.get("SESION_BUCKET", "").strip()
    if not bucket:
        return None, None
    import boto3
    return boto3.client("s3"), bucket


def bajar_sesion():
    cliente, bucket = _s3()
    if not cliente:
        return
    try:
        cliente.download_file(bucket, CLAVE_S3, str(ARCHIVO_SESION))
        os.chmod(ARCHIVO_SESION, 0o600)
        print("[ov] sesion guardada descargada de S3")
    except Exception as e:  # primera vez (no existe) o sin permiso: se entra con Authenticator
        print(f"[ov] sin sesion guardada en S3 ({type(e).__name__})")


def subir_sesion():
    cliente, bucket = _s3()
    if not cliente:
        return
    try:
        cliente.upload_file(str(ARCHIVO_SESION), bucket, CLAVE_S3, ExtraArgs={"ServerSideEncryption": "AES256"})
        print("[ov] sesion guardada en S3")
    except Exception as e:
        print(f"[ov] no se pudo guardar la sesion en S3: {e}")


def en_ov(page):
    return (urlparse(page.url).hostname or "") == HOST_OV


def abrir_ov(p, ver=False):
    """Devuelve (browser, context, page) ya dentro de la app OV."""
    global ULTIMA_ENTRADA
    bajar_sesion()
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
    # Con sesion guardada la app pasa sola por Oracle Identity y Microsoft y vuelve: esperar a que
    # termine esa cadena de redirecciones o a que Microsoft pida de verdad datos/aprobacion
    pide_login = "input[name=loginfmt]:visible, input[name=passwd]:visible, #idRichContext_DisplaySign:visible, " \
                 "[data-value=PhoneAppNotification]:visible, #idDiv_SAOTCAS_Title:visible"
    for _ in range(20):
        page.wait_for_timeout(1000)
        if en_ov(page) or (es_pagina_microsoft(page) and page.locator(pide_login).count()):
            break
    ULTIMA_ENTRADA = "sesion guardada" if en_ov(page) else "Authenticator"

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
    subir_sesion()
    print(f"[ov] dentro ({ULTIMA_ENTRADA}): {page.title()}")
    return browser, context, page


def descargar_ig(page, ruta, destino):
    """Abre una pagina de la app (ruta relativa a URL_OV, sin la sesion) y descarga en Excel su
    tabla interactiva (Acciones -> Descargar -> Excel). Devuelve el rango de filas que muestra."""
    sesion = page.evaluate("apex.env.APP_SESSION")
    union = "&" if "?" in ruta else "?"
    page.goto(f"{URL_OV}{ruta}{union}session={sesion}", wait_until="domcontentloaded")
    page.wait_for_selector(".a-IG .a-GV-table", timeout=60000)
    page.wait_for_load_state("networkidle")
    rango = page.locator(".a-IG .a-GV-pageRange")
    filas = rango.first.inner_text().strip() if rango.count() else "sin filas"
    # La region no tiene id estatico: se toma el de la tabla de la pagina
    region = page.evaluate("document.querySelector('.a-IG').id.replace(/_ig$/, '')")
    page.evaluate(f"apex.region('{region}').call('getActions').invoke('show-download-dialog')")
    dialogo = page.locator(".ui-dialog:visible").last
    dialogo.locator("[data-value='XLSX']").first.click()
    with page.expect_download(timeout=120000) as descarga:
        dialogo.get_by_role("button", name="Descargar").click()
    descarga.value.save_as(str(destino))
    print(f"[ov] {ruta.split('?')[0]}: {filas} -> {destino.name} ({destino.stat().st_size} bytes)")
    return filas
