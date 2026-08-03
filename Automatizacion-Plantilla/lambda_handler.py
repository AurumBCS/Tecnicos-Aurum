"""
Punto de entrada de AWS Lambda para la automatizacion OFS. Traduce el evento
de entrada (uno por regla de EventBridge Scheduler) en la tarea que hay que
correr, replicando el mismo dispatch que ya tenia
.github/workflows/ofs-automation.yml segun github.event.schedule.

Evento esperado (lo manda el "Input" de cada regla de EventBridge Scheduler):
  {"tarea": "manana"}    -> equivalente al cron de las 6:03am
  {"tarea": "mediodia"}  -> equivalente al cron de la 1:58pm
  {"tarea": "tarde"}     -> equivalente al cron de las 5:53pm

"manana" corre tomar_capturas.main() y enviar_correo_matutino.main() EN EL
MISMO proceso/invocacion (no en dos Lambdas separadas): enviar_correo_matutino
necesita leer de disco las capturas que dejo tomar_capturas, y /tmp solo esta
garantizado compartido dentro de una misma invocacion -- si Lambda arranca un
contenedor nuevo (cold start) para una segunda invocacion, /tmp puede llegar
vacio. Juntarlas aqui evita depender de que el mismo contenedor se reutilice.

IMPORTANTE sobre reintentos (configurar en la consola, ver README): EventBridge
Scheduler invoca Lambda de forma asincrona, y por defecto Lambda reintenta
automaticamente una invocacion asincrona que falla. Un reintento de "manana"
volveria a enviar el correo a Mercedes, y uno de "mediodia"/"tarde" volveria a
subir el Excel a confirmaciones-sms -- ninguna de las dos cosas es idempotente.
Por eso cada "schedule" en EventBridge Scheduler debe tener su target con
"Retry policy" -> "Maximum retry attempts" = 0.
"""


def _correr(fn, nombre):
    """
    Los scripts (pensados originalmente para correr como procesos CLI en
    GitHub Actions) usan sys.exit(1) en sus rutas de error. Eso lanza
    SystemExit, que si no se atrapa aqui se propaga tal cual -- Lambda igual
    marca la invocacion como fallida, pero conviene relanzarlo como una
    excepcion con mensaje claro para que se lea bien en CloudWatch Logs.
    """
    try:
        fn()
    except SystemExit as e:
        if e.code not in (0, None):
            raise RuntimeError(
                f"{nombre} termino con error (sys.exit({e.code})); revisar el mensaje anterior en el log"
            ) from e


def handler(event, context):
    tarea = (event or {}).get("tarea")
    if tarea not in ("manana", "mediodia", "tarde"):
        raise ValueError(f"Evento invalido, falta 'tarea' (manana/mediodia/tarde): {event}")

    if tarea == "manana":
        import tomar_capturas
        import enviar_correo_matutino

        _correr(tomar_capturas.main, "tomar_capturas")
        _correr(enviar_correo_matutino.main, "enviar_correo_matutino")
    else:
        import descargar_ruta_y_subir

        _correr(descargar_ruta_y_subir.main, "descargar_ruta_y_subir")

    return {"tarea": tarea, "status": "ok"}
