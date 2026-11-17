"""
Consola de despacho NUEVA (securitasdirect.fs.ocs.oraclecloud.com) con la
cuenta de Verisure de Gustavo (JE-BCN-GD5381), que entra por "Sign in with
SSO" -> Microsoft -> aprobacion en Microsoft Authenticator.

Recorrido confirmado en vivo con Gustavo el 2026-10-15:
  1. Sign in with SSO -> Microsoft (correo, contraseña, Authenticator).
  2. Se abre en "Mi ruta"; menu (☰) -> "Actividades" = Consola de despacho.
  3. Panel izquierdo:
     - Arriba, con estrella, los FAVORITOS (un equipo por JE). No se usan
       (el correo de la mañana con capturas se retiro el 2026-10-16).
     - Abajo, los grupos/buckets. Los que tienen tecnicos son los de icono
       de personas (res-type 2 o 3) cuyo nombre lleva "Aurum" (los de
       Viatek y Smart NO se sacan). Bolsas / Pendiente de Agendar no tienen
       tecnicos y se ignoran.
  4. "Acciones -> Exportar" de un grupo solo pide a la consola esta
     direccion, que devuelve un CSV:
       /?m=gridexport&a=download&itype=manage&providerId=<pid>&date=<AAAA-MM-DD>
         &panel=top&view=time&downloadId=<aleatorio>&dates=<AAAA-MM-DD>
     Se pide directamente para cada grupo (los 78 grupos tardan ~11 s), en
     vez de hacer clic grupo por grupo. Es la misma peticion que hace el
     boton, con la misma sesion.
  5. En el CSV la columna "Técnico" trae solo la matricula; se copia a una
     columna "Matrícula", que es la que usa confirmaciones-sms para filtrar
     por equipo.
"""

import csv
import io
import os
import random
import string

from comun_ofs import (
    es_pagina_microsoft,
    iniciar_sesion_microsoft,
    registrar_error,
)

URL_CONSOLA = "https://securitasdirect.fs.ocs.oraclecloud.com/"
SELECTOR_GRUPOS = ".edt-root .edt-label[data-label-pid]"


CORREO_SSO_DEFECTO = "gustavoa.perez@verisure.es"


def leer_credenciales_sso():
    """Correo y contraseña de Microsoft (cuenta de Verisure) para el SSO.

    En la pantalla de la consola NO se escribe ningun usuario: se pulsa
    "Sign in with SSO" y se entra con estos datos en Microsoft. El correo es
    fijo (CORREO_SSO_DEFECTO, o MS_EMAIL si existe) -- ETADIRECT_USER NO se
    usa. La contraseña de Microsoft se guarda en ETADIRECT_PASS (o MS_PASS).
    """
    correo = (os.environ.get("MS_EMAIL") or CORREO_SSO_DEFECTO).strip()
    clave = (os.environ.get("MS_PASS") or os.environ.get("ETADIRECT_PASS") or "").strip()
    if not clave:
        raise RuntimeError("Falta ETADIRECT_PASS (contraseña de Microsoft de la cuenta de Verisure) en las variables de la Lambda")
    return correo, clave


# Oracle abre en la ultima pantalla que se vio (p. ej. "Detalles de actividad" tras leer fichas), y ahi el
# boton del menu se llama "Menú de navegador" en vez de "Menú" (visto 2026-11-16).
BOTON_MENU = "button[aria-label^='Menú']:visible, button[aria-label^='Menu']:visible"
ENLACE_ACTIVIDADES = "a.global-navigation-item--activities"


def _recargar_si_no_cargo(page, veces=3):
    """Oracle a veces responde "The application could not load" al abrir la consola (visto 2026-11-16, una de
    cada dos cargas en el Chrome compartido). Recarga hasta que entre. True si hubo que recargar."""
    hubo = False
    for _ in range(veces):
        try:
            # (por el titulo: el texto del aviso esta siempre en la pagina, oculto)
            if not page.title().startswith("The application could not load"):
                break
        except Exception:
            break
        hubo = True
        print("[consola] la consola no cargo: se recarga", flush=True)
        page.wait_for_timeout(3000)
        try:
            page.goto(URL_CONSOLA, wait_until="domcontentloaded")
        except Exception:
            pass
        page.wait_for_timeout(4000)
    return hubo


def _salir_de_cierre_fallido(page, forzar=False):
    """Microsoft a veces deja la pagina en "Lo sentimos, tenemos problemas para cerrar su sesión"
    (AADSTS50070), p. ej. cuando Oracle cierra la sesion por su cuenta (visto 2026-11-17 a las 8:00). Esa
    pantalla no es de entrar: se vuelve a la consola, que lleva otra vez al inicio de sesion normal."""
    try:
        texto = page.locator("body").inner_text(timeout=5000)
    except Exception:
        texto = ""
    if forzar or "AADSTS50070" in texto or "cerrar su sesión" in texto or "signing you out" in texto.lower():
        print("[consola] Microsoft se quedó en un cierre de sesión: se vuelve a la consola", flush=True)
        try:
            page.goto(URL_CONSOLA, wait_until="domcontentloaded")
        except Exception:
            pass
        page.wait_for_timeout(5000)
        _recargar_si_no_cargo(page)


def volver_a_actividades(page, espera_ms=20000):
    """Deja la consola en Actividades (la pantalla de los tecnicos). True si se ve el arbol de grupos.
    Se usa al terminar una tarea en el Chrome compartido, para que Gustavo no se encuentre la ultima ficha."""
    try:
        if page.locator(SELECTOR_GRUPOS + ":visible").count() > 0:
            return True
        if page.locator(ENLACE_ACTIVIDADES + ":visible").count() == 0:
            try:
                page.locator(BOTON_MENU).first.click(timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(1200)
        page.evaluate(
            """sel => {
                const a = [...document.querySelectorAll(sel)].find(e => e.getBoundingClientRect().width > 0)
                          || document.querySelector(sel);
                if (a) a.click();
            }""", ENLACE_ACTIVIDADES)
        page.wait_for_selector(SELECTOR_GRUPOS + ":visible", timeout=min(espera_ms, 8000))
        return True
    except Exception:
        pass
    # Con una ficha abierta el menu no cambia de pantalla (visto 2026-11-16): la ficha esta "encima" de la
    # consola en el historial de la pagina, y con Atras se vuelve a ella.
    for _ in range(3):
        try:
            page.go_back(wait_until="domcontentloaded", timeout=15000)
            page.wait_for_selector(SELECTOR_GRUPOS + ":visible", timeout=8000)
            return True
        except Exception:
            if page.locator(SELECTOR_GRUPOS + ":visible").count() > 0:
                return True
    return False


def cerrar_sesion(page):
    """Cierra la sesion de Oracle (menu de usuario -> "Cerrar sesión") para no dejarla ocupando una de las 3
    que permite Oracle por usuario. True si se llego a la pantalla de entrada. Nunca lanza excepcion.
    No usar en el Chrome compartido del Mac: ahi la sesion es tambien la de Gustavo."""
    try:
        page.locator("button.user-menu:visible").first.click(timeout=8000)
        page.locator(".item-caption--logout:visible").first.click(timeout=8000)
        for _ in range(20):
            page.wait_for_timeout(1000)
            if page.locator("button.user-menu:visible").count() == 0:
                print("[consola] sesion de Oracle cerrada", flush=True)
                return True
    except Exception as e:
        print(f"[consola] no se pudo cerrar la sesion: {e.__class__.__name__}", flush=True)
    return False


def entrar_a_consola(page, correo, clave):
    """Login por SSO y abre Actividades (Consola de despacho)."""
    # El navegador del servidor no puede usar llave de acceso / huella, pero
    # Microsoft la intenta igual si el navegador dice que la soporta, y al
    # cancelarla vuelve a pedir el correo (bucle visto en vivo). Se le oculta
    # la API de llaves de acceso (WebAuthn) para que ofrezca la contraseña,
    # igual que haria cualquier navegador sin soporte.
    # (en la pagina y no en el contexto: en el Chrome compartido el contexto es tambien el de Gustavo)
    page.add_init_script(
        # Solo en las paginas de Microsoft: aplicado tambien a Oracle, la consola no carga ("The application
        # could not load") cuando arranca en "Detalles de actividad" (visto 2026-11-16).
        "if (/(microsoftonline|microsoft|live)\\.com$/.test(location.hostname)) {"
        "try { delete window.PublicKeyCredential; } catch (e) {}"
        "try { Object.defineProperty(navigator, 'credentials', { get: () => undefined }); } catch (e) {}"
        "}"
    )
    page.goto(URL_CONSOLA, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    _recargar_si_no_cargo(page)

    if not es_pagina_microsoft(page) and page.locator(SELECTOR_GRUPOS).count() == 0:
        # Con red lenta (internet del movil) el primer clic puede perderse si la pagina aun
        # no ha terminado de cargar (visto 2026-11-04): esperar a que cargue y reintentar
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        for _ in range(3):
            boton_sso = page.get_by_role("button", name="Sign in with SSO")
            if boton_sso.count() == 0:
                boton_sso = page.get_by_text("Sign in with SSO")
            if boton_sso.count() == 0:
                break
            boton_sso.first.click()
            for _ in range(20):
                page.wait_for_timeout(1000)
                if es_pagina_microsoft(page) or not boton_sso.count():
                    break
            if es_pagina_microsoft(page) or not boton_sso.count():
                break

    if es_pagina_microsoft(page):
        _salir_de_cierre_fallido(page)
    if es_pagina_microsoft(page):
        iniciar_sesion_microsoft(page, correo, clave)

    # Tras el login se abre "Mi ruta" (Lista de actividades); la consola esta en
    # menu (☰) -> Actividades. Confirmado en vivo: hay DOS botones "Menú" y el
    # primero esta escondido, y el enlace es a.global-navigation-item--activities
    # (no depende del idioma).
    enlace = "a.global-navigation-item--activities"
    listo = (BOTON_MENU + ", " + enlace + ":visible, " + SELECTOR_GRUPOS + ":visible")
    for intento in range(3):
        try:
            page.wait_for_selector(listo, timeout=30000)
            break
        except Exception:
            if intento == 2:
                raise
            # "The application could not load": pasa a veces al cargar la consola; con recargar entra
            if _recargar_si_no_cargo(page):
                continue
            # La sesion de Oracle se cerro mientras tanto y la pagina acabo en Microsoft (17/11/2026):
            # se vuelve a la consola y, si pide entrar, se entra
            print(f"[consola] no se ve la consola (pantalla: {page.title().split('.')[0][:30]!r}): se vuelve a intentar", flush=True)
            _salir_de_cierre_fallido(page, forzar=True)
            if not es_pagina_microsoft(page) and page.get_by_text("Sign in with SSO").count():
                page.get_by_text("Sign in with SSO").first.click()
                page.wait_for_timeout(5000)
            if es_pagina_microsoft(page):
                iniciar_sesion_microsoft(page, correo, clave)
    # Dejar que "Mi ruta" termine de cargar: un clic demasiado pronto se ignora
    # (visto en vivo 2026-10-16: se quedo en "Lista de actividades").
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    page.wait_for_timeout(3000)

    for intento in range(1, 4):
        # (los grupos pueden estar cargados pero ocultos en "Mi ruta": mirar los visibles)
        if page.locator(SELECTOR_GRUPOS + ":visible").count() > 0:
            break
        print(f"[consola] abriendo Actividades (intento {intento})")
        if page.locator(enlace + ":visible").count() == 0:
            boton_menu = page.locator(BOTON_MENU).first
            try:
                boton_menu.click(timeout=5000)
            except Exception:
                boton_menu.dispatch_event("click")
            page.wait_for_timeout(1500)
        # Clic directo sobre el elemento (como se probo en vivo con exito)
        page.evaluate(
            """sel => {
                const a = [...document.querySelectorAll(sel)].find(e => e.getBoundingClientRect().width > 0)
                          || document.querySelector(sel);
                if (a) a.click();
            }""",
            enlace,
        )
        try:
            page.wait_for_selector(SELECTOR_GRUPOS + ":visible", timeout=25000)
            break
        except Exception:
            # (sin el titulo: en "Detalles de actividad" lleva el nombre del tecnico o del cliente)
            print(f"[consola] Actividades no se abrio todavia (pantalla: {page.title().split('.')[0][:30]!r})")
            if volver_a_actividades(page, espera_ms=8000):
                break
    # Ultimo recurso: para descargar solo hacen falta los identificadores de los
    # grupos, que estan en la pagina aunque el panel no se vea.
    page.wait_for_selector(SELECTOR_GRUPOS, state="attached", timeout=30000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)


def grupos_aurum(page):
    """[{pid, nombre}] de los grupos con tecnicos de Aurum (sin Viatek/Smart)."""
    grupos = page.evaluate(
        """sel => {
            const vistos = new Set();
            return [...document.querySelectorAll(sel)].map(b => {
                const ic = b.parentElement.querySelector('.edt-icon');
                const span = b.querySelector('span.rtl-text');
                return { pid: b.dataset.labelPid, nombre: span ? span.innerText.trim() : '',
                         tipo: ic ? ic.getAttribute('res-type') : '' };
            }).filter(g => {
                if (vistos.has(g.pid)) return false;
                vistos.add(g.pid);
                return (g.tipo === '2' || g.tipo === '3') && /aurum/i.test(g.nombre);
            });
        }""",
        SELECTOR_GRUPOS,
    )
    if not grupos:
        raise RuntimeError("No se encontro ningun grupo Aurum en el panel izquierdo")
    return grupos


def _id_descarga():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=18))


def descargar_csv_grupos(page, fecha_iso):
    """Descarga el CSV de cada grupo Aurum para fecha_iso. Devuelve [(nombre, texto)]."""
    resultados = []
    for g in grupos_aurum(page):
        url = (
            f"{URL_CONSOLA}?m=gridexport&a=download&itype=manage&providerId={g['pid']}"
            f"&date={fecha_iso}&panel=top&view=time&downloadId={_id_descarga()}&dates={fecha_iso}"
        )
        try:
            resp = page.request.get(url, timeout=60000)
            if not resp.ok:
                registrar_error("consola_sso", f"{g['nombre']}: HTTP {resp.status}")
                continue
            texto = resp.body().decode("utf-8-sig", errors="replace")
            resultados.append((g["nombre"], texto))
        except Exception as e:
            registrar_error("consola_sso", f"{g['nombre']}: {e}")
    print(f"[consola] CSV descargados: {len(resultados)} grupos")
    return resultados


def unir_csv_en_xlsx(csvs, ruta_final):
    """Une los CSV en un solo .xlsx (una cabecera) y añade la columna "Matrícula".

    Devuelve el numero de filas de datos.
    """
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    cabecera = None
    i_tecnico = None
    filas = 0
    for nombre, texto in csvs:
        lector = list(csv.reader(io.StringIO(texto)))
        lector = [f for f in lector if any(c.strip() for c in f)]
        if not lector:
            continue
        if cabecera is None:
            cabecera = lector[0]
            i_tecnico = cabecera.index("Técnico") if "Técnico" in cabecera else None
            ws.append(cabecera + ["Matrícula"])
        elif lector[0] != cabecera:
            registrar_error("consola_sso", f"{nombre}: columnas distintas, se omite")
            continue
        for fila in lector[1:]:
            fila = fila + [""] * (len(cabecera) - len(fila))
            matricula = fila[i_tecnico].strip() if i_tecnico is not None else ""
            ws.append(fila[: len(cabecera)] + [matricula])
            filas += 1
    if cabecera is None:
        raise RuntimeError("Ningun CSV traia datos para armar el Excel")
    wb.save(str(ruta_final))
    return filas
