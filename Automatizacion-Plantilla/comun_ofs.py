"""
Login compartido para Oracle Field Service, usado por los scripts de
automatizacion. Hay DOS usuarios distintos de la consola:

  - Usuario "mantenimientos" (ETADIRECT_USER / ETADIRECT_PASS): exporta el
    Excel de mantenimientos (7:30am) y el de ruta del dia siguiente (2pm y
    6pm). Usado por enviar_correo_matutino.py y descargar_ruta_y_subir.py.
  - Usuario "capturas" (ETADIRECT_USER_CAPTURAS / ETADIRECT_PASS_CAPTURAS):
    solo toma las capturas de pantalla de la plantilla (7:30am). Usado por
    tomar_capturas.py.

Cada uno guarda su propia sesion (archivo distinto) para no pisarse entre
si. Credenciales: SIEMPRE desde variables de entorno, nunca en el codigo.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

URL_LOGIN = "https://securitasdirect.etadirect.com/"

# En AWS Lambda solo /tmp es escribible (el resto del contenedor, incluida
# la carpeta del script, es de solo lectura). AWS pone AWS_LAMBDA_FUNCTION_NAME
# automaticamente en el entorno de ejecucion, asi que sirve para detectar
# Lambda sin tocar nada en local/GitHub Actions.
EN_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
CARPETA_BASE = Path("/tmp") if EN_LAMBDA else Path(__file__).parent
LOG_FILE = CARPETA_BASE / "automatizacion.log"

# Chromium necesita estos flags para arrancar dentro del contenedor de
# Lambda. --single-process es el importante: el entorno restringido de
# Lambda no soporta el modelo normal de Chromium de varios procesos
# (zygote + renderers separados) -- sin el, el navegador se cae apenas
# arranca con "Connection closed while reading from the driver" (visto en
# vivo). Los demas evitan el sandbox normal (no soportado en Lambda) y el
# uso de /dev/shm (viene muy limitado de tamaño ahi). No se aplican fuera
# de Lambda porque GitHub Actions/local ya funcionan bien sin ellos.
LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--single-process",
] if EN_LAMBDA else []


def registrar_error(script, mensaje):
    """
    Guarda un error en un log compartido (automatizacion.log), ademas de
    imprimirlo. El Programador de tareas de Windows NO guarda lo que
    imprimen los scripts, asi que sin esto un fallo silencioso (ej. el
    envio de correo, que no toca Playwright) no deja ningun rastro.
    """
    linea = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {script}: {mensaje}"
    print(linea)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except Exception:
        pass


def ruta_sesion(perfil):
    """Archivo de sesion guardada para un perfil ("mantenimientos", "capturas", etc)."""
    return CARPETA_BASE / f"sesion_ofs_{perfil}.json"


def leer_credenciales_ofs(sufijo=""):
    """
    sufijo="" lee ETADIRECT_USER / ETADIRECT_PASS (usuario de mantenimientos).
    sufijo="_CAPTURAS" lee ETADIRECT_USER_CAPTURAS / ETADIRECT_PASS_CAPTURAS.
    """
    usuario = os.environ.get(f"ETADIRECT_USER{sufijo}")
    clave = os.environ.get(f"ETADIRECT_PASS{sufijo}")
    if not usuario or not clave:
        print(
            f"Faltan ETADIRECT_USER{sufijo} / ETADIRECT_PASS{sufijo} como "
            "variables de entorno. Revisa el README.md."
        )
        sys.exit(1)
    return usuario, clave


def _completar_formulario_login(page, usuario, clave):
    """
    Rellena usuario/contraseña y envia, asumiendo que el formulario de
    login (campos #username / #password / boton #sign-in) ya esta visible
    en la pagina actual. El campo "organization" ya viene prellenado con
    "securitasdirect" y oculto, no hace falta tocarlo.
    """
    page.wait_for_selector("#username", timeout=15000)
    page.fill("#username", usuario)
    page.fill("#password", clave)
    page.click("#sign-in")
    page.wait_for_timeout(1500)

    # Caso observado en vivo (causante real de las fallas del 2026-08-24/25):
    # si la cuenta ya tiene demasiadas sesiones abiertas -- por ejemplo,
    # corridas previas que fallaron y nunca cerraron sesion del lado del
    # servidor -- OFS no deja pasar directo a la consola. En su lugar
    # muestra "Maximum number of sessions exceeded" con la opcion "Delete
    # the oldest user session and login" (un radio/checkbox de Oracle JET,
    # igual que el combobox de "Empresa Contratista" en aplicar_filtro_aurum:
    # el control real esta detras de una capa decorativa que Playwright
    # marca "no visible", por eso hace falta force=True) y despues hay que
    # volver a apretar el mismo boton "Sign in" (#sign-in) para confirmar.
    # Sin force=True el clic "funciona" pero no marca de verdad la opcion,
    # y el boton #sign-in queda disabled para siempre (confirmado en vivo:
    # Page.click en #sign-in agotaba su propio timeout esperando que se
    # habilitara).
    aviso_sesiones = page.get_by_text("Delete the oldest user session and login")
    if aviso_sesiones.count() > 0 and aviso_sesiones.first.is_visible():
        try:
            html_opcion = aviso_sesiones.first.locator("xpath=..").first.evaluate("el => el.outerHTML")
            print(f"[diagnostico] HTML alrededor de la opcion 'Delete the oldest...': {html_opcion!r}")
        except Exception as e_diag:
            print(f"[diagnostico] No se pudo leer el HTML de la opcion: {e_diag}")

        aviso_sesiones.first.click(force=True)
        page.wait_for_timeout(800)

        boton_signin = page.locator("#sign-in")
        try:
            print(f"[diagnostico] #sign-in disabled tras marcar la opcion: {boton_signin.get_attribute('disabled')!r}")
        except Exception as e_diag:
            print(f"[diagnostico] No se pudo leer el atributo disabled de #sign-in: {e_diag}")

        boton_signin.click(force=True)
        page.wait_for_timeout(1500)

    # Esperar a que cargue la consola de despacho (la tabla de tecnicos).
    page.wait_for_selector(".toaGantt-provTree", timeout=60000)


def iniciar_sesion(page, usuario, clave):
    """Navega al login desde cero y lo completa."""
    page.goto(URL_LOGIN, wait_until="networkidle")
    _completar_formulario_login(page, usuario, clave)


def abrir_sesion_ofs(context, page, usuario, clave, archivo_sesion):
    """
    Reutiliza la sesion guardada (archivo_sesion) si sigue vigente; si
    expiro, inicia sesion normal. Cada usuario (mantenimientos, capturas)
    usa su propio archivo_sesion para no pisarse entre si.

    Caso observado en vivo (y causante de una falla real en produccion): si
    la sesion expiro solo a medias, la consola muestra un dialogo
    "Timeout de sesión" pidiendo unicamente la contraseña de nuevo (sin
    campo de usuario), con un boton "Cerrar sesión" -- pero la tabla de
    tecnicos (".toaGantt-provTree") puede seguir presente en el DOM
    *detras* de ese dialogo, asi que revisar solo su presencia no alcanza
    para saber si la sesion sigue vigente. Por eso aqui se revisa PRIMERO,
    siempre, si el dialogo de timeout esta visible, antes de asumir que la
    sesion esta bien. Ese clic en "Cerrar sesión" YA redirige solo al
    formulario de login completo — por eso NO se vuelve a llamar
    page.goto() despues del clic (hacerlo competia con la propia
    redireccion del clic y producia net::ERR_ABORTED); simplemente se
    completa el formulario que queda visible.
    """
    if archivo_sesion.exists():
        page.goto(URL_LOGIN, wait_until="networkidle")

        cerrar_sesion_btn = page.locator(
            "button:has-text('Cerrar sesión'), button:has-text('Log Out'), button:has-text('Sign Out')"
        )
        if cerrar_sesion_btn.count() > 0 and cerrar_sesion_btn.first.is_visible():
            cerrar_sesion_btn.first.click()
            page.wait_for_load_state("networkidle")
            _completar_formulario_login(page, usuario, clave)
        else:
            sesion_vigente = page.locator(".toaGantt-provTree:visible").count() > 0
            if not sesion_vigente:
                iniciar_sesion(page, usuario, clave)
    else:
        iniciar_sesion(page, usuario, clave)

    # Guarda la sesion fresca para la proxima corrida
    context.storage_state(path=str(archivo_sesion))


def _escribir_y_elegir_jet(page, texto_busqueda, texto_opcion, timeout_ms=10000):
    """
    Escribe `texto_busqueda` en un combobox de Oracle JET ya abierto y hace
    clic en la sugerencia cuyo texto es exactamente `texto_opcion`. Con
    Enter el panel se cierra por completo en vez de seleccionar la opcion
    (visto en vivo), asi que hay que clickear la sugerencia directamente.

    No se asume ninguna clase/contenedor especifico (los distintos campos
    de "Vista" usan variantes de widget con clases distintas) -- se busca
    por texto en toda la pagina y se toma el primer elemento que sea
    realmente visible, ignorando coincidencias ocultas de listbox de otros
    campos.
    """
    page.keyboard.type(texto_busqueda)
    page.wait_for_timeout(800)

    candidatos = page.get_by_text(texto_opcion, exact=True)
    tiempo_restante = timeout_ms
    paso = 200
    while tiempo_restante > 0:
        for i in range(candidatos.count()):
            el = candidatos.nth(i)
            if el.is_visible():
                el.click(force=True)
                return
        page.wait_for_timeout(paso)
        tiempo_restante -= paso

    raise RuntimeError(f"No aparecio ninguna opcion visible con el texto '{texto_opcion}'")


def aplicar_filtro_aurum(page):
    """
    Aplica el filtro de "Vista" -> Filtros: Empresa Contratista -> AURUM,
    necesario para que la consola muestre solo tecnicos/actividades de
    AURUM (sin esto, la vista trae tecnicos de otras empresas mezclados).

    NO VERIFICADO en vivo todavia (escrito a partir de una captura de
    pantalla del panel "Vista", no de inspeccion del DOM real). Probar
    con headless=False; si falla, avisar en que paso exacto se traba
    para ajustar el selector correspondiente aqui.
    """
    page.get_by_role("button", name="Vista", exact=True).click()
    page.wait_for_timeout(500)

    # El desplegable "Filtros" viene por defecto en "*" (todos). Hay que
    # abrirlo y buscar "Empresa Contratista" en la lista (puede requerir
    # scroll). Se hace siempre, sin detectar "ya aplicado", porque el
    # panel "Vista" reinicia su estado en cada carga de pagina.
    #
    # El <input role="combobox"> real de estos selects de Oracle JET esta
    # tecnicamente presente pero Playwright lo marca "no visible" (queda
    # detras de un contenedor decorativo que es lo que se ve en pantalla),
    # por eso se usa force=True para saltar esa verificacion y hacer clic
    # igual -- el manejador de clic esta atado al input real.
    page.get_by_label("Filtros").first.click(force=True)
    page.wait_for_timeout(300)
    # Borra el "*" que trae por defecto antes de escribir, si no queda
    # "*Emp" y no filtra nada.
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    _escribir_y_elegir_jet(page, "Emp", "Empresa Contratista")
    page.wait_for_timeout(500)

    # El campo que aparece debajo (para elegir el valor del filtro) es
    # otro combobox de Oracle JET (no un <input> normal): hay que abrirlo
    # con clic y luego escribir para buscar la opcion, no se puede usar
    # .fill() directo.
    combobox = page.get_by_label("Empresa Contratista").first
    combobox.click(force=True)
    page.wait_for_timeout(300)
    _escribir_y_elegir_jet(page, "AUR", "AURUM")
    page.wait_for_timeout(300)

    # Asegurar que "Aplicar jerárquicamente" este marcado
    checkbox = page.get_by_role("checkbox", name="Aplicar jerárquicamente")
    if checkbox.count() > 0 and not checkbox.is_checked():
        checkbox.check()

    page.get_by_role("button", name="Aplicar", exact=True).click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)


def exportar_excel(page, ruta_destino):
    """
    Abre el menu "Acciones" y hace clic en "Exportar" para descargar el
    Excel de actividades/mantenimientos del dia mostrado en la consola,
    y lo guarda en ruta_destino. Usado tanto para el Excel de mantenimientos
    adjunto al correo de las 7:30am como para la ruta del dia siguiente
    en el script de las 17:30.

    El texto "Acciones" / "Exportar" esta confirmado (visto en captura real
    de la consola). Lo que falta verificar es si "Exportar" descarga el
    archivo directo o abre antes un dialogo con opciones; si abre un
    dialogo, hay que agregar aqui el paso para confirmarlo.
    """
    page.get_by_text("Acciones", exact=True).click()
    with page.expect_download() as descarga_info:
        page.get_by_text("Exportar", exact=True).click()
    descarga = descarga_info.value
    descarga.save_as(str(ruta_destino))
    return ruta_destino
