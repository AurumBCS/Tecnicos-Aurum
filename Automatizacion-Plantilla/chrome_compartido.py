"""
Chrome de Oracle de las tareas del Mac (16/11/2026; invisible desde el 17/11): una sola sesion de Oracle
para todas las tareas, que se conserva entre una y otra. Gustavo usa Oracle en su Chrome normal (otra sesion).

Oracle solo deja 3 sesiones por usuario y tira la sesion si se copia a otro navegador (por eso la "sesion
guardada" fallaba casi siempre). En vez de abrir un navegador propio en cada tarea, las tareas del Mac se
conectan a un Chrome sin ventana (headless), con perfil aparte (~/.aurum-chrome-oracle), que se queda
abierto entre tareas, y abren sus pestañas en el: la misma sesion para todas. No se ve nada en pantalla.

Se activa con ORACLE_CHROME=1 (lo pone tarde_mac.sh). Sin la variable, o en la Lambda, o si Chrome no
arranca, todo sigue como antes (navegador propio sin ventana). Para volver atras: quitar esa linea.

El puerto de control solo escucha en este Mac (127.0.0.1).
"""

import os
import socket
import subprocess
import time
from pathlib import Path

from comun_ofs import LAUNCH_ARGS

PUERTO = int(os.environ.get("ORACLE_CHROME_PUERTO", "9333"))
PERFIL = Path.home() / ".aurum-chrome-oracle"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
URL_INICIO = "https://securitasdirect.fs.ocs.oraclecloud.com/"
VISTA = {"width": 1600, "height": 1000}


def activo():
    return os.environ.get("ORACLE_CHROME") == "1" and not os.environ.get("AWS_LAMBDA_FUNCTION_NAME")


def _escucha():
    try:
        socket.create_connection(("127.0.0.1", PUERTO), timeout=2).close()
        return True
    except OSError:
        return False


def _es_invisible():
    """True si el Chrome de Oracle que esta abierto es el invisible (headless). El User-Agent del modo
    headless nuevo ya no lo dice, asi que se mira la linea de comandos del proceso."""
    try:
        out = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return True   # si no se puede saber, no se toca
    return any(f"--user-data-dir={PERFIL}" in l and "--headless" in l for l in out.splitlines())


def _cerrar_visible():
    """Cierra el Chrome de Oracle con ventana (el de la prueba del 16/11) para abrirlo invisible.
    Solo el que usa el perfil de las tareas: el Chrome normal de Gustavo no se toca."""
    import signal
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return False
    for l in out.splitlines():
        pid, _, cmd = l.strip().partition(" ")
        if f"--user-data-dir={PERFIL}" in cmd and "--headless" not in cmd and "--type=" not in cmd:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
    for _ in range(20):
        if not _escucha():
            time.sleep(2)
            return True
        time.sleep(1)
    return False


def arrancar():
    """Abre el Chrome de Oracle de las tareas si no esta abierto. True si queda escuchando.
    Desde el 17/11/2026 es INVISIBLE (sin ventana): Gustavo no quiere ver las tareas y usa Oracle en su
    Chrome normal, con su propia sesion. Las tareas comparten entre ellas esta sesion (una sola)."""
    if _escucha() and not _es_invisible():
        print("[chrome] se cierra el Chrome de Oracle con ventana para abrirlo invisible", flush=True)
        _cerrar_visible()
    if _escucha():
        return True
    if not os.path.exists(CHROME):
        return False
    PERFIL.mkdir(mode=0o700, exist_ok=True)
    subprocess.Popen(
        [CHROME, "--headless=new", f"--user-data-dir={PERFIL}", f"--remote-debugging-port={PUERTO}",
         "--remote-debugging-address=127.0.0.1",
         "--no-first-run", "--no-default-browser-check", "--window-size=1600,1000",
         # las pestañas de las tareas trabajan aunque la ventana este tapada o minimizada
         "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows",
         "--disable-renderer-backgrounding", URL_INICIO],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        if _escucha():
            time.sleep(2)
            return True
        time.sleep(1)
    return False


class _Contexto:
    """Hace de contexto nuevo, pero sus pestañas se abren en el contexto del Chrome compartido."""

    def __init__(self, nav):
        self._nav = nav
        self._real = nav._ctx
        self._mias = []

    def new_page(self):
        page = self._real.new_page()
        page.set_viewport_size(VISTA)
        self._mias.append(page)
        self._nav._paginas.append(page)
        return page

    def storage_state(self, **_):
        # La sesion vive en el perfil de Chrome: no se copia a ningun fichero
        return {}

    def close(self):
        for pg in self._mias:
            try:
                pg.close()
            except Exception:
                pass
        self._mias = []

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


class _Navegador:
    """Lo minimo que usan las tareas de un Browser de Playwright: new_context() y close()."""

    compartido = True

    def __init__(self, browser):
        self._b = browser
        self._ctx = browser.contexts[0]
        self._paginas = []
        # Pestañas muertas de Oracle ("The application could not load") que hayan quedado de otra ejecucion
        for pg in list(self._ctx.pages):
            try:
                if pg.title().startswith("The application could not load"):
                    pg.close()
            except Exception:
                pass

    def new_context(self, **_):
        return _Contexto(self)

    def close(self):
        # Oracle recuerda la ultima pantalla: se deja en Actividades (los tecnicos) y no en la ultima ficha
        # leida, que es lo que se encontraba Gustavo al abrir Oracle (16/11/2026)
        for pg in self._paginas:
            try:
                if not pg.is_closed():
                    import consola_sso
                    if consola_sso.volver_a_actividades(pg):
                        pg.wait_for_timeout(1500)
                        break
            except Exception:
                pass
        # Solo se cierran las pestañas de la tarea; el Chrome y las pestañas de Gustavo se quedan
        for pg in self._paginas:
            try:
                pg.close()
            except Exception:
                pass
        self._paginas = []
        try:
            self._b.close()   # en una conexion por CDP solo desconecta
        except Exception:
            pass


def lanzar(p):
    """Navegador para una tarea de Oracle: el Chrome compartido si esta activo, o uno propio como antes."""
    if activo():
        try:
            if arrancar():
                nav = _Navegador(p.chromium.connect_over_cdp(f"http://127.0.0.1:{PUERTO}"))
                print("[chrome] tarea en el Chrome compartido de Oracle (misma sesion)", flush=True)
                return nav
            print("[chrome] el Chrome compartido no arranco: navegador propio", flush=True)
        except Exception as e:
            print(f"[chrome] sin Chrome compartido ({e.__class__.__name__}: {e}): navegador propio", flush=True)
    return p.chromium.launch(headless=True, args=LAUNCH_ARGS)
