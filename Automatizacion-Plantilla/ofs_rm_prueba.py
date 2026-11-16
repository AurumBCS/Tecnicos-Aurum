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
import os
import socket
import sys
import time
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


def _hay_internet():
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=4).close()
        return True
    except OSError:
        return False


def esperar_internet(max_min=45):
    """Mac con el internet del movil (tuneles, sin cobertura): espera a que vuelva. True si hubo corte y ya volvio."""
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or _hay_internet():
        return False
    print("[red] sin internet, esperando a que vuelva...", flush=True)
    inicio = time.time()
    while not _hay_internet():
        if time.time() - inicio > max_min * 60:
            print(f"[red] {max_min} min sin internet, sigo sin esperar mas", flush=True)
            return False
        time.sleep(15)
    print(f"[red] internet de vuelta tras {int(time.time() - inicio)} s", flush=True)
    return True


def _reanudar_si_corte(page):
    """Si el fallo fue por un corte de internet, espera a que vuelva y recarga la pagina (misma sesion)."""
    if not esperar_internet():
        return False
    try:
        page.reload(wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
    except Exception as e:
        print(f"[red] no se pudo recargar: {e}", flush=True)
    return True


# Sesion de Oracle caida a mitad de lectura (visto 2026-11-13: 288 fallos seguidos durante 1 h 20 min
# porque la consola dejo de mostrar el buscador): se vuelve a entrar en la misma pagina y se sigue.
FALLOS_PARA_REENTRAR = 3
MAX_REENTRADAS = 4
_fallos_seguidos = 0
_reentradas = 0


def _sesion_caida(page):
    """True si la pagina ya no es la consola: pantalla de entrada de Oracle o de Microsoft."""
    try:
        from comun_ofs import es_pagina_microsoft
        if es_pagina_microsoft(page):
            return True
        if page.get_by_text("Sign in with SSO").count() > 0:
            return True
        return page.locator(BOTON_BUSCADOR).count() == 0 and page.locator(CAMPO_BUSCADOR).count() == 0
    except Exception:
        return False


def _reentrar(page, motivo):
    """Vuelve a entrar en la consola con la misma pagina. True si se pudo."""
    global _fallos_seguidos, _reentradas
    if _reentradas >= MAX_REENTRADAS:
        return False
    _reentradas += 1
    _fallos_seguidos = 0
    print(f"[rm] sesion de Oracle caida ({motivo}): se vuelve a entrar ({_reentradas}/{MAX_REENTRADAS})", flush=True)
    try:
        import consola_sso
        correo, clave = consola_sso.leer_credenciales_sso()
        consola_sso.entrar_a_consola(page, correo, clave)
        print("[rm] de nuevo dentro de la consola", flush=True)
        return True
    except Exception as e:
        try:
            if page.locator(BOTON_BUSCADOR + ":visible, " + CAMPO_BUSCADOR + ":visible").count() > 0:
                print("[rm] dentro de Oracle (con el buscador, sin abrir Actividades): se sigue", flush=True)
                return True
        except Exception:
            pass
        print(f"[rm] no se pudo volver a entrar: {e.__class__.__name__}: {e}", flush=True)
        registrar_error("ofs_rm_prueba", f"no se pudo volver a entrar en la consola: {e}")
        return False


def _leer(page, numero, capturas, errores, reintento=True):
    """Ficha filtrada, "no visible" si no sale en la busqueda, o None si fallo."""
    global _fallos_seguidos
    try:
        ficha = _buscar_mantenimiento(page, numero, capturas)
        _fallos_seguidos = 0
        print(f"[rm] {numero}: ficha leida")
        return ficha
    except NoVisible:
        # Sin internet la busqueda tampoco encuentra nada: no confundirlo con "otra empresa"
        if reintento and _reanudar_si_corte(page):
            return _leer(page, numero, capturas, errores, reintento=False)
        if _sesion_caida(page):
            # Con la sesion caida nada sale en la busqueda: no es "otra empresa"
            if reintento and _reentrar(page, "pantalla de entrada"):
                return _leer(page, numero, capturas, errores, reintento=False)
            errores.append(f"{numero}: sesion de Oracle caida")
            return None
        print(f"[rm] {numero}: no sale en la busqueda (otra empresa)")
        return "no visible"
    except Exception as e:
        if reintento and _reanudar_si_corte(page):
            return _leer(page, numero, capturas, errores, reintento=False)
        _fallos_seguidos += 1
        if reintento:
            motivo = "pantalla de entrada" if _sesion_caida(page) else (
                f"{_fallos_seguidos} fallos seguidos" if _fallos_seguidos >= FALLOS_PARA_REENTRAR else "")
            if motivo and _reentrar(page, motivo):
                return _leer(page, numero, capturas, errores, reintento=False)
        errores.append(f"{numero}: {e}")
        registrar_error("ofs_rm_prueba", f"{numero}: {e}")
        return None


def _buscar_lote(paginas, numeros, capturas):
    """Una ficha por pestaña, todas a la vez: se lanza la busqueda en cada pestaña y despues se recogen,
    asi las esperas de Oracle se solapan. Devuelve una lista con la ficha (dict) o None por cada numero;
    lo que queda en None lo relee despues la pagina principal con _leer (que distingue "otra empresa",
    cortes de internet y sesion caida)."""
    n = len(numeros)
    vivo = [True] * n
    campos = [None] * n
    for i in range(n):
        try:
            pg = paginas[i]
            campo = pg.locator(CAMPO_BUSCADOR + ":visible").first
            if not campo.count():
                pg.locator(BOTON_BUSCADOR + ":visible").first.click(timeout=15000)
                campo = pg.locator(CAMPO_BUSCADOR + ":visible").first
            campo.wait_for(timeout=10000)
            campo.click()
            campo.fill("")
            campo.type(numeros[i], delay=60)
            campo.press("Enter")
            campos[i] = campo
        except Exception:
            vivo[i] = False
    for i in range(n):
        if not vivo[i]:
            continue
        try:
            r = paginas[i].locator(RESULTADO + ":visible", has_text=f"Mto:{numeros[i]}").first
            r.wait_for(timeout=20000)
            r.click()
        except Exception:
            vivo[i] = False
            try:
                campos[i].fill("")
                paginas[i].keyboard.press("Escape")
            except Exception:
                pass
    for i in range(n):
        if not vivo[i]:
            continue
        try:
            paginas[i].wait_for_function(
                "n => document.body.innerText.includes('DETALLES MANTENIMIENTO')"
                " && document.body.innerText.includes('Número de Mantenimiento\\n' + n)",
                arg=numeros[i], timeout=20000)
        except Exception:
            pass
    if any(vivo):
        paginas[0].wait_for_timeout(1000)
    fichas = [None] * n
    for i in range(n):
        if not vivo[i]:
            continue
        ficha = ficha_ofs.extraer_ficha(_texto(paginas[i]))
        if ficha and ficha.get("numero") == numeros[i]:
            fichas[i] = ficha
    return fichas


def _abrir_pestanas(page, cuantas):
    """Pestañas extra en el MISMO navegador y contexto (misma sesion de Oracle, como un usuario con varias
    pestañas). Con otro navegador y las cookies copiadas Oracle tira la sesion (probado 2026-11-16)."""
    import consola_sso
    extras = []
    for _ in range(cuantas):
        pg = None
        try:
            pg = page.context.new_page()
            if page.viewport_size:
                pg.set_viewport_size(page.viewport_size)
            pg.goto(consola_sso.URL_CONSOLA, wait_until="domcontentloaded")
            pg.wait_for_selector(BOTON_BUSCADOR + ":visible, " + CAMPO_BUSCADOR + ":visible", timeout=60000)
            pg.wait_for_timeout(3000)
            extras.append(pg)
        except Exception as e:
            print(f"[rm] no se pudo abrir otra pestaña ({e.__class__.__name__})", flush=True)
            try:
                pg and pg.close()
            except Exception:
                pass
            break
    return extras


def leer_varias(page, numeros, capturas, errores, cada=None, hilos=None):
    """Lee muchas fichas con varias pestañas a la vez en la misma sesion de Oracle.
    Devuelve {numero: ficha | "no visible" | None}. cada(resultados) se llama cada 10 fichas o mas
    (avance, guardado parcial). FICHAS_HILOS=1 lo deja como antes, de una en una (asi va en la Lambda)."""
    if hilos is None:
        hilos = int(os.environ.get("FICHAS_HILOS") or (1 if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else 3))
    pendientes = list(dict.fromkeys(numeros))
    resultados, extras, avisado, lotes_malos = {}, [], 0, 0
    if hilos > 1 and len(pendientes) >= 20:
        extras = _abrir_pestanas(page, hilos - 1)
        if extras:
            print(f"[rm] {len(pendientes)} fichas con {1 + len(extras)} pestañas en la misma sesion", flush=True)
    try:
        while pendientes:
            if extras:
                lote, pendientes = pendientes[:1 + len(extras)], pendientes[1 + len(extras):]
                try:
                    fichas = _buscar_lote([page] + extras, lote, capturas)
                except Exception:
                    fichas = [None] * len(lote)
                antes = _reentradas
                for numero, ficha in zip(lote, fichas):
                    if isinstance(ficha, dict):
                        print(f"[rm] {numero}: ficha leida")
                        resultados[numero] = ficha
                    else:
                        resultados[numero] = _leer(page, numero, capturas, errores)
                # Si casi nada sale en paralelo (o hubo que reentrar), se sigue de una en una
                lotes_malos = lotes_malos + 1 if sum(isinstance(f, dict) for f in fichas) <= len(lote) // 2 else 0
                if lotes_malos >= 3 or _reentradas != antes:
                    print("[rm] las pestañas extra no van bien: se sigue de una en una", flush=True)
                    for pg in extras:
                        try:
                            pg.close()
                        except Exception:
                            pass
                    extras = []
            else:
                numero = pendientes.pop(0)
                resultados[numero] = _leer(page, numero, capturas, errores)
            if cada and len(resultados) - avisado >= 10:
                avisado = len(resultados)
                cada(dict(resultados))
    finally:
        for pg in extras:
            try:
                pg.close()
            except Exception:
                pass
    return resultados


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
