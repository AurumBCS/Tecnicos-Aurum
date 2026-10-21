"""
Envio de los lotes de Upselling al Microsoft Form "UPSELLING" (tarea "upselling_envio" de la
Lambda). No tiene horario: la arranca el Apps Script por la URL de funcion de la Lambda cuando Anna
pulsa "Enviar al Form" (o "Reintentar") en la app -- ver _desde_url en lambda_handler.py.

  1. Pregunta al Apps Script de la app (Upselling.gs, accion ups-lambda-siguiente) por el lote
     aprobado. Al terminarlo pide el siguiente, hasta que no quede ninguno.
  2. Abre el Form con la sesion de Microsoft guardada de la app OV (sesion_ov.json, misma cuenta
     de Verisure de Gustavo); si Microsoft pide entrar, usa el mismo inicio de sesion con
     Authenticator que el resto de tareas.
  3. Comprueba que el Form sigue teniendo las 10 preguntas esperadas (si alguien lo cambia, para
     sin enviar nada) y lo rellena fila a fila igual que a mano: rellenar, leer lo escrito y
     compararlo con la fila, Enviar, esperar la confirmacion y "Enviar otra respuesta".
  4. Antes de pulsar Enviar marca la fila "Enviando" y al ver la confirmacion "Enviado"; si la
     Lambda se corta entre medias, la fila queda para revisar a mano y nunca se reenvia sola.
  5. Avisa a Gustavo con el resultado. Si se queda sin tiempo (lote muy grande), se vuelve a
     arrancar a si misma para seguir.

Uso local de prueba: python forms_upselling.py --ver --sin-enviar
  (rellena una fila de ejemplo, hace una captura y NO pulsa Enviar ni cambia nada en la hoja)
"""

import json
import os
import re
import sys
import time
import urllib.request

import comun_ofs
from comun_ofs import LAUNCH_ARGS, enviar_aviso, es_pagina_microsoft, iniciar_sesion_microsoft, registrar_error

URL_FORM = os.environ.get(
    "UPS_FORM_URL",
    "https://forms.cloud.microsoft/Pages/ResponsePage.aspx?id="
    "f_pVMESpJ0mAHqYrYxGeQ2sbbp3XXPlBhjysq_Fp-PlUNUI5TFYzWE9FQThOSFBPNUhMWk9ERURNUi4u")
# Preguntas del Form en orden (lo que tiene que contener su titulo) y campo de la fila que va en cada una
PREGUNTAS = [
    ("Número de instalación", "inst", "texto"),
    ("Número de Mantenimiento", "mant", "texto"),
    ("Matricula", "mat", "texto"),
    ("Panel", "panel", "lista"),
    ("Interno o empresa externa", "emp", "lista"),
    ("Referencia ampliada", "ref", "texto"),
    ("Cantidad ampliada", "cant", "lista"),
    ("Cuota ampliada", "cuota", "texto"),
    ("Importe facturado sin IVA", "imp", "texto"),
    ("Tipo ampliacion", "tipo", "opcion"),
]
PREGUNTA = '[data-automation-id="questionItem"]'
OTRA_RESPUESTA = "Enviar otra respuesta"
MARGEN_MS = 90 * 1000          # no empezar otra fila si a la Lambda le queda menos que esto
ERRORES_SEGUIDOS_MAX = 3       # con 3 filas seguidas fallando se para (el Form o la sesion van mal)


def _entorno(nombre):
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise RuntimeError(f"Falta la variable {nombre} en la Lambda")
    return valor


def _apps_script(accion, **datos):
    """POST a Upselling.gs (accion ups-lambda-*) por el doPost de la app."""
    cuerpo = dict(datos, mat="LAMBDA", accion=accion, token=_entorno("UPS_TOKEN"))
    req = urllib.request.Request(_entorno("UPS_SCRIPT_URL"), data=json.dumps(cuerpo).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        texto = r.read().decode()
    try:
        res = json.loads(texto)
    except ValueError:
        raise RuntimeError("El Apps Script no devolvio JSON (¿falta la linea ups- en doPost?): " + texto[:300])
    if not res.get("ok"):
        raise RuntimeError("Error del Apps Script: " + str(res.get("error")))
    return res


def en_form(page):
    return page.locator(PREGUNTA).count() == len(PREGUNTAS)


def abrir_form(p, ver=False):
    """Devuelve (browser, context, page) con el Form abierto y vacio."""
    import ov_comun

    ov_comun.bajar_sesion()
    browser = p.chromium.launch(headless=not ver, args=LAUNCH_ARGS)
    archivo = ov_comun.ARCHIVO_SESION
    context = browser.new_context(storage_state=str(archivo) if archivo.exists() else None,
                                  locale="es-ES", viewport={"width": 1200, "height": 900})
    # Sin llaves de acceso (WebAuthn), para que Microsoft ofrezca la contraseña (ver consola_sso.py)
    context.add_init_script(
        "try { delete window.PublicKeyCredential; } catch (e) {}"
        "try { Object.defineProperty(navigator, 'credentials', { get: () => undefined }); } catch (e) {}")
    page = context.new_page()
    page.goto(URL_FORM, wait_until="domcontentloaded")
    for _ in range(30):
        page.wait_for_timeout(1000)
        if en_form(page) or (es_pagina_microsoft(page) and page.locator(
                "input[name=loginfmt]:visible, input[name=passwd]:visible, #idRichContext_DisplaySign:visible, "
                "#tilesHolder:visible, [data-value=PhoneAppNotification]:visible").count()):
            break
    if not en_form(page) and es_pagina_microsoft(page):
        print("[upselling] sin sesion vigente -> inicio de sesion de Microsoft")
        comun_ofs.MOTIVO_AVISO = "El envio de Upselling al Form"
        from consola_sso import leer_credenciales_sso
        correo, clave = leer_credenciales_sso()
        iniciar_sesion_microsoft(page, correo, clave)
    page.wait_for_selector(PREGUNTA, timeout=60000)
    if not en_form(page):
        raise RuntimeError(f"El Form no tiene las {len(PREGUNTAS)} preguntas esperadas ({page.locator(PREGUNTA).count()})")
    context.storage_state(path=str(archivo))
    os.chmod(archivo, 0o600)
    ov_comun.subir_sesion()
    return browser, context, page


def comprobar_preguntas(page):
    """Para sin enviar nada si el Form ya no tiene las preguntas en el orden esperado."""
    titulos = [t.replace("\n", " ") for t in page.locator(PREGUNTA).all_inner_texts()]
    for i, (texto, _, _) in enumerate(PREGUNTAS):
        if texto.lower() not in titulos[i].lower():
            raise RuntimeError(f"El Form ha cambiado: la pregunta {i + 1} deberia ser '{texto}' y es '{titulos[i][:80]}'")


def leer_valores(page):
    return page.evaluate("""(sel) => [...document.querySelectorAll(sel)].map(q => {
        const campo = q.querySelector('textarea, input[type=text], input:not([type])');
        const lista = q.querySelector('[aria-haspopup="listbox"]');
        const opcion = q.querySelector('input[type=radio]:checked');
        return (campo ? campo.value : lista ? lista.innerText : opcion ? opcion.value : '').trim();
    })""", PREGUNTA)


def rellenar(page, fila):
    preguntas = page.locator(PREGUNTA)
    for i, (_, campo, tipo) in enumerate(PREGUNTAS):
        q, valor = preguntas.nth(i), str(fila[campo])
        if tipo == "texto":
            q.locator("textarea, input[type=text], input:not([type])").first.fill(valor)
        elif tipo == "lista":
            q.locator('[aria-haspopup="listbox"]').first.click()
            page.get_by_role("option", name=valor, exact=True).click()
        else:
            q.get_by_role("radio", name=re.compile("^" + re.escape(valor))).check()
    escrito = leer_valores(page)
    distinto = [f"{PREGUNTAS[i][0]}: '{escrito[i]}' en vez de '{fila[c]}'"
                for i, (_, c, _) in enumerate(PREGUNTAS) if escrito[i].upper() != str(fila[c]).strip().upper()]
    if distinto:
        raise RuntimeError("El Form no quedo como la fila -- " + "; ".join(distinto))


def enviar(page):
    page.get_by_role("button", name="Enviar", exact=True).click()
    page.get_by_text(OTRA_RESPUESTA).wait_for(timeout=30000)


def nueva_respuesta(page):
    """Deja el Form vacio para la siguiente fila (o lo vuelve a abrir si algo fue mal)."""
    otra = page.get_by_text(OTRA_RESPUESTA)
    if otra.count():
        otra.first.click()
    else:
        page.goto(URL_FORM, wait_until="domcontentloaded")
    page.wait_for_function(f"document.querySelectorAll('{PREGUNTA}').length === {len(PREGUNTAS)}", timeout=30000)
    page.wait_for_timeout(500)


def _poco_tiempo(context_lambda):
    return bool(context_lambda) and context_lambda.get_remaining_time_in_millis() < MARGEN_MS


def relanzar(context_lambda):
    """Sin tiempo y con filas pendientes: la Lambda se vuelve a arrancar a si misma (asincrona) para seguir."""
    import boto3

    boto3.client("lambda").invoke(FunctionName=context_lambda.function_name, InvocationType="Event",
                                  Payload=json.dumps({"tarea": "upselling_envio"}).encode())
    print("[upselling] sin tiempo: se arranca otra vez la Lambda para seguir con lo pendiente")


def enviar_lote(page, lote, filas, context_lambda):
    """Envia las filas pendientes de un lote. Devuelve (enviadas, errores, sin_tiempo).
    Lanza excepcion si hay que parar el lote entero (Form cambiado, sesion caida...)."""
    enviadas, errores, seguidos = 0, [], 0
    for fila in filas:
        if _poco_tiempo(context_lambda):
            return enviadas, errores, True
        pulsado = False
        try:
            rellenar(page, fila)
            _apps_script("ups-lambda-fila", lote=lote, fila=fila["fila"], estado="Enviando")
            pulsado = True
            enviar(page)
            _apps_script("ups-lambda-fila", lote=lote, fila=fila["fila"], estado="Enviado")
            enviadas += 1
            seguidos = 0
        except Exception as e:
            msg = str(e).split("\n")[0][:200]
            print(f"[upselling] fila {fila['fila']} ({fila['inst']}): {msg}")
            # Antes de pulsar Enviar no llego al Form (Error); despues puede haber llegado o no (Revisar)
            _apps_script("ups-lambda-fila", lote=lote, fila=fila["fila"], estado="Revisar" if pulsado else "Error",
                         detalle=("Sin confirmacion del Form: comprobar si llego. " if pulsado else "") + msg)
            errores.append(f"{fila['inst']}: {msg}")
            seguidos += 1
            if seguidos >= ERRORES_SEGUIDOS_MAX:
                raise RuntimeError(f"{seguidos} filas seguidas con error, se para. Ultimo: {msg}")
        nueva_respuesta(page)
    return enviadas, errores, False


def prueba_sin_enviar():
    """Prueba local: rellena una fila de ejemplo, hace una captura y NO envia ni toca la hoja."""
    from playwright.sync_api import sync_playwright

    fila = dict(fila=1, inst="7249928", mant="143702067", mat="359682", panel="VERISURE", emp="AURUM",
                ref="MONTR", cant="1", cuota="0", imp="59", tipo="303 - ELEMENTO")
    with sync_playwright() as p:
        browser, _, page = abrir_form(p, ver="--ver" in sys.argv)
        try:
            comprobar_preguntas(page)
            rellenar(page, fila)
            page.screenshot(path="upselling_prueba.png", full_page=True)
            print("[upselling] prueba: Form rellenado sin enviar -> upselling_prueba.png")
        finally:
            browser.close()


def main(context_lambda=None):
    """Envia todos los lotes aprobados, uno detras de otro (se arranca al pulsar "Enviar al Form" en la app)."""
    if "--sin-enviar" in sys.argv:
        return prueba_sin_enviar()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page = None, None
        try:
            while True:
                if _poco_tiempo(context_lambda):
                    relanzar(context_lambda)
                    return
                pedido = _apps_script("ups-lambda-siguiente")
                lote, filas = pedido.get("lote"), pedido.get("filas") or []
                if not lote:
                    print("[upselling] " + ("otra Lambda esta enviando" if pedido.get("ocupado") else "no hay mas lotes aprobados"))
                    return
                print(f"[upselling] lote {lote} (enviado por {pedido.get('aprobadoPor')}): {len(filas)} filas pendientes")
                inicio, enviadas, errores, sin_tiempo, error_lote, captura = time.time(), 0, [], False, "", None
                try:
                    if filas:
                        if page is None:
                            browser, _, page = abrir_form(p, ver="--ver" in sys.argv)
                            comprobar_preguntas(page)
                        enviadas, errores, sin_tiempo = enviar_lote(page, lote, filas, context_lambda)
                except Exception as e:
                    error_lote = str(e).split("\n")[0][:300]
                    registrar_error("forms_upselling", error_lote)
                    try:
                        captura = page.screenshot() if page else None
                    except Exception:
                        pass
                res = _apps_script("ups-lambda-fin", lote=lote, error=error_lote)
                resumen = (f"Lote {lote} (enviado por {pedido.get('aprobadoPor')}): {enviadas} enviadas, "
                           f"{len(errores)} con error, {res.get('quedan', 0)} pendientes. Estado: {res.get('estado')}. "
                           f"Tiempo: {(time.time() - inicio) / 60:.1f} min.")
                print("[upselling] " + resumen)
                if error_lote or errores:
                    enviar_aviso(f"Upselling: {res.get('estado')}",
                                 resumen + "\n\n" + (f"Motivo: {error_lote}\n\n" if error_lote else "") + "\n".join(errores),
                                 captura=captura)
                elif res.get("estado") == "Terminado":
                    enviar_aviso("Upselling: lote enviado", resumen)
                if error_lote:
                    sys.exit(1)   # Form cambiado / sesion caida: no seguir con otros lotes
                if sin_tiempo:
                    relanzar(context_lambda)
                    return
        finally:
            if browser:
                browser.close()


if __name__ == "__main__":
    main()
