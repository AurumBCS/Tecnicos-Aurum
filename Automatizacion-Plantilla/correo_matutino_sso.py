"""
Correo de la mañana a Mercedes con la consola NUEVA (cuenta de Verisure por
SSO + aprobacion en Microsoft Authenticator). Un solo inicio de sesion para:
  1. Capturas de cada equipo favorito (estrella), menos "AURUM", con la fecha
     de HOY.
  2. El Excel de mantenimientos de HOY (CSV de cada grupo Aurum unidos).
  3. Envio del correo (mismo formato y destinatarios que enviar_correo_matutino).

Ver consola_sso.py para el recorrido confirmado en vivo. Tarea de Lambda:
{"tarea": "manana_sso"}.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

import consola_sso
from comun_ofs import CARPETA_BASE, LAUNCH_ARGS, enviar_aviso, registrar_error
from enviar_correo_matutino import DESTINATARIO, enviar_correo

CARPETA_CAPTURAS = CARPETA_BASE / "capturas"
CARPETA_DESCARGAS = CARPETA_BASE / "descargas"


def main():
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pass:
        registrar_error("correo_matutino_sso", "faltan GMAIL_USER / GMAIL_APP_PASSWORD")
        sys.exit(1)
    try:
        correo, clave = consola_sso.leer_credenciales_sso()
    except RuntimeError as e:
        registrar_error("correo_matutino_sso", str(e))
        enviar_aviso("❌ Correo de la mañana NO enviado", str(e))
        sys.exit(1)

    CARPETA_DESCARGAS.mkdir(parents=True, exist_ok=True)
    ruta_excel = CARPETA_DESCARGAS / f"mantenimientos_{hoy.isoformat()}.xlsx"
    capturas, excel = [], None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        try:
            consola_sso.entrar_a_consola(page, correo, clave)
            capturas = consola_sso.capturar_favoritos(page, CARPETA_CAPTURAS, f"plantilla_{hoy.isoformat()}")
            try:
                csvs = consola_sso.descargar_csv_grupos(page, hoy.isoformat())
                consola_sso.unir_csv_en_xlsx(csvs, ruta_excel)
                excel = ruta_excel
            except Exception as e:
                registrar_error("correo_matutino_sso", f"fallo el Excel de mantenimientos: {e}")
        except Exception as e:
            registrar_error("correo_matutino_sso", f"fallo la consola: {e}")
            captura = None
            try:
                captura = page.screenshot()
            except Exception:
                pass
            enviar_aviso(
                "❌ Correo de la mañana NO enviado",
                f"Fallo la entrada a la consola o las capturas.\n\nError: {e}\nPagina: {page.url}",
                captura,
            )
            sys.exit(1)
        finally:
            browser.close()

    if not capturas and not excel:
        registrar_error("correo_matutino_sso", "no hay ni capturas ni Excel -- no se manda correo vacio")
        enviar_aviso("❌ Correo de la mañana NO enviado", "No se obtuvo ninguna captura ni el Excel.")
        sys.exit(1)

    try:
        enviar_correo(gmail_user, gmail_pass, capturas, excel)
    except Exception as e:
        registrar_error("correo_matutino_sso", f"fallo al enviar el correo por SMTP: {e}")
        sys.exit(1)
    print(f"Listo: {len(capturas)} capturas + {'Excel' if excel else 'SIN Excel'} enviado a {DESTINATARIO}")


if __name__ == "__main__":
    main()
