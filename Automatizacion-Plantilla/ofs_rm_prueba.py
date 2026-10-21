"""
Prueba (manual, sin horario): buscar en la consola de Oracle Field Service
unos pocos mantenimientos repetidos (RM), abrir su ficha y mandar por correo
lo util para entender por que se repitio: tipo, observaciones del tecnico,
codificaciones, zonas e historico (ver ficha_ofs.py). Los datos del cliente
NO se guardan; solo hay capturas si algun paso falla.

Recorrido (indicado por Gustavo, 2026-10-19): "Buscar en actividades" arriba
a la derecha -> numero + Enter -> clic en el resultado -> Detalles de actividad.

Se trabaja por PAREJAS del Excel de RM: mantenimiento original (columna E) +
mantenimiento posterior (columna M) + motivo de la vuelta (Motivo Post).
  - El ORIGINAL siempre lo hizo un tecnico de Aurum -> siempre se ve.
  - El POSTERIOR solo aparece en nuestra sesion si lo hizo alguien de Aurum
    (a veces el mismo tecnico). Si lo hizo otra empresa no sale en la busqueda:
    no es un error, y la causa hay que sacarla solo del original (lo que hizo,
    codificaciones, zonas) comparado con el Motivo Post del Excel.
  - El "Histórico de Mantenimientos" de la ficha original solo trae visitas
    ANTERIORES, no la posterior.

Evento:
  {"tarea": "ofs_rm_prueba"}
  {"tarea": "ofs_rm_prueba", "parejas": [["141454924", "141603588", "Camara ARLO"]]}

Por defecto, dos parejas de agosto del Excel "RM Septiembre" (tecnico 361439):
  141454924 Camara ARLO -> 141603588 Camara ARLO
  136293991 Pilas bajas -> 141402035 Pilas bajas
"""

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

import ficha_ofs
from comun_ofs import CARPETA_BASE, LAUNCH_ARGS, enviar_aviso, registrar_error

PAREJAS_DEFECTO = [
    ("141454924", "141603588", "Camara ARLO"),
    ("136293991", "141402035", "Pilas bajas"),
]


class NoVisible(Exception):
    """El mantenimiento no sale en la busqueda (lo hizo otra empresa)."""

# Recorrido confirmado en vivo (2026-10-19, ventana de 1600 px; si es estrecha
# la barra se convierte en una lupa):
#   1. Arriba a la derecha, input.global-search-bar-input-button ("Buscar en
#      actividades o inventarios") es solo un BOTON con forma de campo: al
#      pulsarlo se abre y enfoca el campo real input.search-bar-input[type=search].
#   2. Numero + Enter -> panel de resultados a la derecha; cada resultado es un
#      div.global-search-found-item[role=link] cuyo texto lleva "Mto:<numero>".
#   3. Clic en el -> "Detalles de actividad" (DETALLES MANTENIMIENTO).
#   La barra sigue arriba en la ficha: se puede buscar el siguiente sin volver.
#   OJO: a la izquierda de la Consola de despacho hay otro input[type=search]
#   (filtro de tecnicos) -- no es el bueno.
BOTON_BUSCADOR = "input.global-search-bar-input-button"
CAMPO_BUSCADOR = "input.search-bar-input[type=search]"
RESULTADO = ".global-search-found-item"


def _texto(page):
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception as e:
        return f"(no se pudo leer el texto: {e})"


def _captura(page, capturas, nombre):
    try:
        capturas.append((nombre, page.screenshot(full_page=True)))
    except Exception as e:
        print(f"[rm] sin captura {nombre}: {e}")


def _buscar_mantenimiento(page, numero, capturas):
    """Busca el numero en "Buscar en actividades", abre el resultado y devuelve
    la ficha ya filtrada (ficha_ofs.extraer_ficha). Las capturas solo se guardan
    si algo falla (la pantalla trae datos del cliente)."""
    # Si una busqueda anterior no encontro nada, el panel de busqueda se queda
    # abierto y tapa el boton (visto 2026-10-22): se usa el campo directamente.
    campo = page.locator(CAMPO_BUSCADOR + ":visible").first
    if not campo.count():
        page.locator(BOTON_BUSCADOR + ":visible").first.click(timeout=15000)
        campo = page.locator(CAMPO_BUSCADOR + ":visible").first
    campo.wait_for(timeout=10000)
    campo.click()
    campo.fill("")
    campo.type(numero, delay=60)
    campo.press("Enter")

    # Resultado con "Mto:<numero>" en el panel de la derecha -> clic
    resultado = page.locator(RESULTADO + ":visible", has_text=f"Mto:{numero}").first
    try:
        resultado.wait_for(timeout=20000)
    except Exception:
        # Cerrar el panel de busqueda para que no tape el boton en la siguiente
        try:
            campo.fill("")
            page.keyboard.press("Escape")
        except Exception:
            pass
        raise NoVisible(numero)
    resultado.click()
    try:
        page.wait_for_function(
            "n => document.body.innerText.includes('DETALLES MANTENIMIENTO')"
            " && document.body.innerText.includes('Número de Mantenimiento\\n' + n)",
            arg=numero, timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(1000)

    ficha = ficha_ofs.extraer_ficha(_texto(page))
    if not ficha or ficha.get("numero") != numero:
        _captura(page, capturas, f"{numero}_sin_ficha")
        raise RuntimeError("no se abrio la ficha del mantenimiento")

    return ficha


def _leer(page, numero, capturas, errores):
    """Ficha filtrada, "no visible" si no sale en la busqueda, o None si fallo."""
    try:
        ficha = _buscar_mantenimiento(page, numero, capturas)
        print(f"[rm] {numero}: ficha leida")
        return ficha
    except NoVisible:
        print(f"[rm] {numero}: no sale en la busqueda (otra empresa)")
        return "no visible"
    except Exception as e:
        errores.append(f"{numero}: {e}")
        registrar_error("ofs_rm_prueba", f"{numero}: {e}")
        return None


def main(parejas=None):
    import consola_sso

    parejas = [tuple(str(x).strip() for x in p) + ("",) * (3 - len(p)) for p in (parejas or PAREJAS_DEFECTO)]
    print(f"[rm] parejas a revisar: {parejas}")
    correo, clave = consola_sso.leer_credenciales_sso()

    capturas, resultados, errores = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        try:
            consola_sso.entrar_a_consola(page, correo, clave)
            for original, posterior, motivo_post in parejas:
                r = {"original": original, "posterior": posterior, "motivo_post": motivo_post,
                     "ficha_original": _leer(page, original, capturas, errores)}
                r["ficha_posterior"] = _leer(page, posterior, capturas, errores) if posterior else None
                resultados.append(r)
        except Exception as e:
            errores.append(f"entrada a la consola: {e}")
            registrar_error("ofs_rm_prueba", f"entrada a la consola: {e}")
            _captura(page, capturas, "error_entrada")
        finally:
            browser.close()

    # Solo se guardan los datos filtrados (sin datos del cliente): resultado.json + resumen.txt
    ahora = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d_%H%M")
    carpeta = CARPETA_BASE / f"rm_prueba_{ahora}"
    carpeta.mkdir(exist_ok=True)
    for nombre, png in capturas:
        (carpeta / f"{nombre}.png").write_bytes(png)
    ruta_json = carpeta / "resultado.json"
    ruta_json.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")

    leidos = sum(isinstance(r["ficha_original"], dict) for r in resultados)
    cuerpo = [f"Prueba de lectura de RMs en Oracle: {leidos} de {len(parejas)} originales leidos.", ""]
    for r in resultados:
        cuerpo.append(f"===== RM {r['original']} -> {r['posterior'] or '?'} · volvieron por: {r['motivo_post'] or '?'} =====")
        fo, fp = r["ficha_original"], r["ficha_posterior"]
        cuerpo.append("ORIGINAL:\n" + (ficha_ofs.resumen_legible(fo) if isinstance(fo, dict)
                                       else "(no sale en la busqueda)" if fo == "no visible" else "(fallo, ver errores)"))
        if isinstance(fp, dict):
            cuerpo.append("POSTERIOR:\n" + ficha_ofs.resumen_legible(fp))
        elif fp == "no visible":
            cuerpo.append("POSTERIOR: no sale en nuestra sesion (lo hizo otra empresa) -- solo se cuenta con el original.")
        cuerpo.append("")
    if errores:
        cuerpo += ["Errores (con captura adjunta):"] + errores
    texto = "\n".join(cuerpo)
    (carpeta / "resumen.txt").write_text(texto, encoding="utf-8")
    print(f"[rm] resultado guardado en {carpeta}")

    asunto = ("⚠️" if errores else "✅") + f" Prueba RM en Oracle ({leidos}/{len(parejas)})"
    enviar_aviso(asunto, texto, adjunto=ruta_json, capturas=capturas)
    if not leidos:
        sys.exit(1)


if __name__ == "__main__":
    # python ofs_rm_prueba.py ORIGINAL POSTERIOR ["Motivo post"]  (sin argumentos: parejas por defecto)
    main([sys.argv[1:]] if len(sys.argv) > 1 else None)
