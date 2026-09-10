"""
Correo matutino (7:30am): arma el Excel de mantenimientos del dia y lo
manda por correo a Mercedes junto con las capturas de pantalla que ya
dejo guardadas tomar_capturas.py.

El Excel se arma exportando bucket por bucket con el usuario de CAPTURAS
(ETADIRECT_USER_CAPTURAS) y pegando todos los .xlsx en uno solo -- ver
`exportar_todos_los_buckets` en comun_ofs.py y la seccion "modo
degradado" del README. (Antes se exportaba de una sola vez con el
usuario de mantenimientos, al que ya no tenemos acceso.)

Si la exportacion por buckets falla, el correo igual sale con las
capturas solas (con una nota en el cuerpo) -- mejor eso que nada.

Este script NO toma capturas -- eso lo hace tomar_capturas.py, que se
corre en la misma invocacion de Lambda unos pasos antes (comparten el
/tmp y la sesion del usuario de capturas).

Credenciales: se leen SIEMPRE de variables de entorno, nunca estan
escritas en este archivo.

Variables de entorno:
  ETADIRECT_USER_CAPTURAS   Usuario de la consola (capturas) -- obligatoria para el Excel
  ETADIRECT_PASS_CAPTURAS   Su contraseña
  GMAIL_USER                gustavo.perez@aurumbcs.com
  GMAIL_APP_PASSWORD        Contraseña de aplicacion de Gmail (NO la normal) -- obligatoria

Uso manual (para probar):
  python enviar_correo_matutino.py
"""

import os
import sys
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication

from playwright.sync_api import sync_playwright

from comun_ofs import (
    CARPETA_BASE,
    LAUNCH_ARGS,
    ruta_sesion,
    leer_credenciales_ofs,
    abrir_sesion_ofs,
    exportar_todos_los_buckets,
    registrar_error,
)

# ── Configuracion ──────────────────────────────────────────────────────────

CARPETA_CAPTURAS = CARPETA_BASE / "capturas"
CARPETA_DESCARGAS = CARPETA_BASE / "descargas"
ARCHIVO_SESION = ruta_sesion("capturas")  # mismo usuario que tomar_capturas.py
DESTINATARIO = "mercedes.savarino@aurumbcs.com"
COPIA = "gustavo.perez@aurumbcs.com"
REMITENTE = "gustavo.perez@aurumbcs.com"


def leer_credenciales_correo():
    usuario = os.environ.get("ETADIRECT_USER_CAPTURAS")
    clave = os.environ.get("ETADIRECT_PASS_CAPTURAS")
    gmail_user = os.environ.get("GMAIL_USER", REMITENTE)
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_pass:
        print("Falta la variable de entorno GMAIL_APP_PASSWORD. Revisa el README.md.")
        sys.exit(1)

    return usuario, clave, gmail_user, gmail_pass


def buscar_capturas_de_hoy():
    fecha = datetime.now().strftime("%Y-%m-%d")
    capturas = sorted(CARPETA_CAPTURAS.glob(f"plantilla_{fecha}_*.png"))
    if not capturas:
        # No se corta: el correo puede salir solo con el Excel (util al
        # probar este script suelto sin haber corrido tomar_capturas).
        print(f"Aviso: no hay capturas de hoy ({fecha}) en {CARPETA_CAPTURAS}.")
    return capturas


def armar_excel_mantenimientos(usuario, clave):
    """
    Exporta el Excel de mantenimientos del dia recorriendo los buckets con
    el usuario de capturas. Devuelve la ruta del .xlsx armado, o None si
    no se pudo (el correo sale igual, solo con capturas).
    """
    if not usuario or not clave:
        print(
            "ETADIRECT_USER_CAPTURAS / ETADIRECT_PASS_CAPTURAS no configuradas -- "
            "el correo va sin el Excel de mantenimientos."
        )
        return None

    fecha = datetime.now().strftime("%Y-%m-%d")
    CARPETA_DESCARGAS.mkdir(exist_ok=True)
    ruta_final = CARPETA_DESCARGAS / f"mantenimientos_{fecha}.xlsx"

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

            exportar_todos_los_buckets(
                page, CARPETA_DESCARGAS / "buckets_mantenimientos", ruta_final
            )
            return ruta_final
        except Exception as e:
            registrar_error(
                "enviar_correo_matutino",
                f"fallo armando el Excel de mantenimientos por buckets: {e}",
            )
            try:
                page.screenshot(path=str(CARPETA_DESCARGAS / "error_debug.png"))
            except Exception:
                pass
            return None
        finally:
            browser.close()


def enviar_correo(gmail_user, gmail_pass, capturas, excel=None):
    fecha_legible = datetime.now().strftime("%d/%m/%Y")
    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = DESTINATARIO
    msg["Cc"] = COPIA
    msg["Subject"] = f"Plantilla de técnicos · {fecha_legible}"

    if excel:
        cuerpo = f"Adjunto la plantilla de técnicos y el Excel de mantenimientos del {fecha_legible}."
    else:
        cuerpo = (
            f"Adjunto la plantilla de técnicos del {fecha_legible}. "
            "El Excel de mantenimientos no va en este correo (falló la exportación)."
        )
    msg.attach(MIMEText(cuerpo, "plain"))

    for ruta in capturas:
        with open(ruta, "rb") as f:
            img = MIMEImage(f.read(), name=ruta.name)
        img["Content-Disposition"] = f'attachment; filename="{ruta.name}"'
        msg.attach(img)

    if excel:
        with open(excel, "rb") as f:
            adjunto_excel = MIMEApplication(f.read(), name=excel.name)
        adjunto_excel["Content-Disposition"] = f'attachment; filename="{excel.name}"'
        msg.attach(adjunto_excel)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, [DESTINATARIO, COPIA], msg.as_string())


def main():
    usuario, clave, gmail_user, gmail_pass = leer_credenciales_correo()
    capturas = buscar_capturas_de_hoy()
    ruta_excel = armar_excel_mantenimientos(usuario, clave)

    if not capturas and not ruta_excel:
        registrar_error("enviar_correo_matutino", "no hay ni capturas ni Excel -- no se manda correo vacio")
        sys.exit(1)

    try:
        enviar_correo(gmail_user, gmail_pass, capturas, ruta_excel)
    except Exception as e:
        registrar_error("enviar_correo_matutino", f"fallo al enviar el correo por SMTP: {e}")
        sys.exit(1)

    partes = []
    if capturas:
        partes.append(f"{len(capturas)} capturas")
    partes.append("Excel de mantenimientos" if ruta_excel else "SIN Excel (fallo la exportacion)")
    print(f"Listo: {' + '.join(partes)} enviado a {DESTINATARIO}")


if __name__ == "__main__":
    main()
