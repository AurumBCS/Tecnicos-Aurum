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


def entrar_a_consola(page, correo, clave):
    """Login por SSO y abre Actividades (Consola de despacho)."""
    # El navegador del servidor no puede usar llave de acceso / huella, pero
    # Microsoft la intenta igual si el navegador dice que la soporta, y al
    # cancelarla vuelve a pedir el correo (bucle visto en vivo). Se le oculta
    # la API de llaves de acceso (WebAuthn) para que ofrezca la contraseña,
    # igual que haria cualquier navegador sin soporte.
    page.context.add_init_script(
        "try { delete window.PublicKeyCredential; } catch (e) {}"
        "try { Object.defineProperty(navigator, 'credentials', { get: () => undefined }); } catch (e) {}"
    )
    page.goto(URL_CONSOLA, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    if not es_pagina_microsoft(page) and page.locator(SELECTOR_GRUPOS).count() == 0:
        boton_sso = page.get_by_role("button", name="Sign in with SSO")
        if boton_sso.count() == 0:
            boton_sso = page.get_by_text("Sign in with SSO")
        if boton_sso.count() > 0:
            boton_sso.first.click()
            page.wait_for_timeout(3000)

    if es_pagina_microsoft(page):
        iniciar_sesion_microsoft(page, correo, clave)

    # Tras el login se abre "Mi ruta" (Lista de actividades); la consola esta en
    # menu (☰) -> Actividades. Confirmado en vivo: hay DOS botones "Menú" y el
    # primero esta escondido, y el enlace es a.global-navigation-item--activities
    # (no depende del idioma).
    enlace = "a.global-navigation-item--activities"
    page.wait_for_selector("button[aria-label='Menú']:visible, button[aria-label='Menu']:visible, "
                           + enlace + ":visible, " + SELECTOR_GRUPOS, timeout=90000)
    # (los grupos pueden estar cargados pero ocultos en "Mi ruta": mirar los visibles)
    if page.locator(SELECTOR_GRUPOS + ":visible").count() == 0:
        if page.locator(enlace + ":visible").count() == 0:
            page.locator("button[aria-label='Menú']:visible, button[aria-label='Menu']:visible").first.click()
            page.wait_for_selector(enlace + ":visible", timeout=15000)
        page.locator(enlace + ":visible").first.click()
    page.wait_for_selector(SELECTOR_GRUPOS + ":visible", timeout=90000)
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
