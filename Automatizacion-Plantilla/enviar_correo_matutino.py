"""
Correo matutino (7:30am): exporta el Excel de mantenimientos del dia
(usuario de mantenimientos, ETADIRECT_USER / ETADIRECT_PASS), junta las
capturas de pantalla que ya dejo guardadas tomar_capturas.py (con OTRO
usuario, corrido un poco antes), y envia todo por correo a Mercedes.

Este script NO toma capturas -- eso lo hace tomar_capturas.py por separado,
porque usa un usuario distinto de la consola. Programa tomar_capturas.py
unos minutos antes que este (ver README.md) para que las capturas de HOY ya
esten listas cuando este script las busque.

Credenciales: se leen SIEMPRE de variables de entorno, nunca estan escritas
en este archivo.

Variables de entorno requeridas:
  ETADIRECT_USER       Usuario de la consola de despacho (mantenimientos)
  ETADIRECT_PASS       Contraseña de la consola de despacho
  GMAIL_USER            gustavo.perez@aurumbcs.com
  GMAIL_APP_PASSWORD    Contraseña de aplicacion de Gmail (NO la contraseña normal)

Uso manual (para probar):
  python enviar_correo_matutino.py

Programacion diaria: ver README.md (Task Scheduler), a las 7:30am.
"""

import os
import sys
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from comun_ofs import (
    CARPETA_BASE,
    LAUNCH_ARGS,
    ruta_sesion,
    leer_credenciales_ofs,
    abrir_sesion_ofs,
    aplicar_filtro_aurum,
    exportar_excel,
    registrar_error,
)

# ── Configuracion ──────────────────────────────────────────────────────────

CARPETA_CAPTURAS = CARPETA_BASE / "capturas"
CARPETA_DESCARGAS = CARPETA_BASE / "descargas"
ARCHIVO_SESION = ruta_sesion("mantenimientos")
DESTINATARIO = "mercedes.savarino@aurumbcs.com"
COPIA = "gustavo.perez@aurumbcs.com"
REMITENTE = "gustavo.perez@aurumbcs.com"


def leer_credenciales_correo():
    usuario, clave = leer_credenciales_ofs()
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
        print(
            f"No hay capturas de hoy ({fecha}) en {CARPETA_CAPTURAS}. "
            "¿Corrio tomar_capturas.py antes que este script?"
        )
        sys.exit(1)
    return capturas


def enviar_correo(gmail_user, gmail_pass, capturas, excel):
    fecha_legible = datetime.now().strftime("%d/%m/%Y")
    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = DESTINATARIO
    msg["Cc"] = COPIA
    msg["Subject"] = f"Plantilla de técnicos · {fecha_legible}"
    msg.attach(MIMEText(
        f"Adjunto la plantilla de técnicos y el Excel de mantenimientos del {fecha_legible}.",
        "plain",
    ))

    for ruta in capturas:
        with open(ruta, "rb") as f:
            img = MIMEImage(f.read(), name=ruta.name)
        img["Content-Disposition"] = f'attachment; filename="{ruta.name}"'
        msg.attach(img)

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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)

        if ARCHIVO_SESION.exists():
            context = browser.new_context(storage_state=str(ARCHIVO_SESION))
        else:
            context = browser.new_context()

        page = context.new_page()

        try:
            abrir_sesion_ofs(context, page, usuario, clave, ARCHIVO_SESION)
            aplicar_filtro_aurum(page)

            CARPETA_DESCARGAS.mkdir(exist_ok=True)
            fecha = datetime.now().strftime("%Y-%m-%d")
            ruta_excel = exportar_excel(
                page, CARPETA_DESCARGAS / f"mantenimientos_{fecha}.xlsx"
            )
        except PlaywrightTimeoutError as e:
            registrar_error("enviar_correo_matutino", f"la pagina tardo demasiado o no encontro un elemento esperado: {e}")
            CARPETA_DESCARGAS.mkdir(exist_ok=True)
            page.screenshot(path=str(CARPETA_DESCARGAS / "error_debug.png"))
            sys.exit(1)
        finally:
            browser.close()

    try:
        enviar_correo(gmail_user, gmail_pass, capturas, ruta_excel)
    except Exception as e:
        registrar_error("enviar_correo_matutino", f"fallo al enviar el correo por SMTP: {e}")
        sys.exit(1)

    print(f"Listo: {len(capturas)} capturas y Excel de mantenimientos enviados a {DESTINATARIO}")


if __name__ == "__main__":
    main()
