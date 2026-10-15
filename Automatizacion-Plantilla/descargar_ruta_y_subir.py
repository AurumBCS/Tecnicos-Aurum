"""
Descarga diaria de la ruta (Excel de actividades) del dia siguiente desde
Oracle Field Service y la sube a la app Aurum (confirmaciones-sms) para
que salgan las citas a confirmar.

Entra en la consola nueva con la cuenta de Verisure (SSO de Microsoft +
aprobacion en Authenticator) y descarga el CSV de cada grupo Aurum -- ver
consola_sso.py. Se manda un correo a AVISO_EMAIL con el resultado.

Regla de fecha: SIEMPRE se descarga la ruta del dia SIGUIENTE a hoy, excepto
que ese dia siguiente caiga domingo, en cuyo caso se salta al lunes. La fecha
va directamente en la peticion de exportacion (no hace falta tocar las flechas).

Credenciales: se leen SIEMPRE de variables de entorno (ver README.md).

Variables de entorno:
  ETADIRECT_PASS  contraseña de Microsoft de la cuenta de Verisure (obligatoria)
  MS_EMAIL      (opcional) correo de Microsoft, por defecto gustavoa.perez@verisure.es
  GMAIL_USER / GMAIL_APP_PASSWORD   para los avisos por correo
  AVISO_EMAIL   (opcional) destino de los avisos, por defecto gustavo.perez@aurumbcs.com

Uso manual (para probar):
  python descargar_ruta_y_subir.py

Programacion diaria: ver README.md (EventBridge Scheduler).
"""

import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

from comun_ofs import (
    CARPETA_BASE,
    LAUNCH_ARGS,
    enviar_aviso,
    registrar_error,
)

# ── Configuracion ──────────────────────────────────────────────────────────

CARPETA_DESCARGAS = CARPETA_BASE / "descargas"
URL_SUBIDA = "https://tecnicos-aurum.onrender.com/upload"
MATRICULA_SUBIDA = "GD5381"  # uploader autorizado sin filtro (Gustavo Perez)


def calcular_fecha_objetivo():
    """Siempre el dia siguiente a hoy; si ese dia es domingo, salta al lunes."""
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()  # Lambda corre en UTC
    objetivo = hoy + timedelta(days=1)
    if objetivo.weekday() == 6:  # 6 = domingo
        objetivo += timedelta(days=1)
    return objetivo


def subir_excel(ruta_excel):
    with open(ruta_excel, "rb") as f:
        resp = requests.post(
            URL_SUBIDA,
            files={"excel": (ruta_excel.name, f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"matricula": MATRICULA_SUBIDA},
            timeout=60,
        )
    resp.raise_for_status()
    return resp


def main():
    """
    Consola nueva (cuenta de Verisure por SSO + Authenticator): entra, pide el
    CSV de cada grupo Aurum para el dia siguiente, los une en un .xlsx y lo
    sube. Ver consola_sso.py para el recorrido confirmado en vivo.
    """
    import consola_sso

    fecha_objetivo = calcular_fecha_objetivo()
    fecha_txt = fecha_objetivo.strftime("%d/%m/%Y")
    CARPETA_DESCARGAS.mkdir(exist_ok=True)
    ruta_excel = CARPETA_DESCARGAS / f"ruta_{fecha_objetivo.isoformat()}.xlsx"

    try:
        correo, clave = consola_sso.leer_credenciales_sso()
    except RuntimeError as e:
        registrar_error("descargar_ruta_y_subir", str(e))
        enviar_aviso("❌ Ruta NO descargada", str(e))
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        try:
            consola_sso.entrar_a_consola(page, correo, clave)
            csvs = consola_sso.descargar_csv_grupos(page, fecha_objetivo.isoformat())
            filas = consola_sso.unir_csv_en_xlsx(csvs, ruta_excel)
            print(f"[ruta] {len(csvs)} grupos, {filas} filas -> {ruta_excel}")
        except Exception as e:
            registrar_error("descargar_ruta_y_subir", f"la pagina tardo demasiado o algo fallo: {e}")
            captura = None
            try:
                captura = page.screenshot()
            except Exception:
                pass
            url = ""
            try:
                url = page.url
                print(f"[diagnostico] URL al momento del error: {url}")
                print(f"[diagnostico] Texto visible (primeros 1000 caracteres): {page.locator('body').inner_text()[:1000]!r}")
            except Exception as e_diag:
                print(f"[diagnostico] No se pudo leer URL/texto de la pagina: {e_diag}")
            enviar_aviso(
                "❌ Ruta NO descargada",
                f"Fallo la descarga de la ruta del {fecha_txt}.\n\nError: {e}\nPagina: {url}\n\n"
                "Adjunto una captura de la pantalla donde se trabo.",
                captura,
            )
            sys.exit(1)
        finally:
            browser.close()

    try:
        resp = subir_excel(ruta_excel)
    except Exception as e:
        registrar_error("descargar_ruta_y_subir", f"fallo al subir el excel al servidor de confirmaciones: {e}")
        enviar_aviso(
            "❌ Ruta descargada pero NO subida",
            f"Se descargo la ruta del {fecha_txt} pero fallo la subida a confirmaciones-sms.\n\nError: {e}",
            adjunto=ruta_excel,
        )
        sys.exit(1)

    resumen = ""
    try:
        d = resp.json()
        resumen = (f"{d.get('added', 0)} citas nuevas, {d.get('updated', 0)} reprogramadas, "
                   f"{d.get('count', '?')} en total en confirmaciones-sms.")
    except Exception:
        pass
    print(f"Listo: ruta del {fecha_objetivo.isoformat()} subida (matricula {MATRICULA_SUBIDA}). {resumen}")
    enviar_aviso(
        f"✅ Ruta del {fecha_txt} subida",
        f"La ruta del {fecha_txt} se descargo de {len(csvs)} grupos Aurum ({filas} filas) y se subio "
        f"a confirmaciones-sms.\n{resumen}\n\nAdjunto el Excel descargado.",
        adjunto=ruta_excel,
    )


if __name__ == "__main__":
    main()
