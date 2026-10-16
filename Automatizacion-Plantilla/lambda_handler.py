"""
Punto de entrada de AWS Lambda para la automatizacion OFS. Traduce el evento
de entrada (uno por regla de EventBridge Scheduler) en la tarea que hay que
correr, replicando el mismo dispatch que ya tenia
.github/workflows/ofs-automation.yml segun github.event.schedule.

Evento esperado (lo manda el "Input" de cada regla de EventBridge Scheduler):
  {"tarea": "mediodia"}  -> 14:00, ruta del dia siguiente
  {"tarea": "tarde"}     -> 17:30, ruta del dia siguiente
  {"tarea": "ov_prueba"} -> prueba de entrada a la app OV de inventario (manual, sin horario)
  {"tarea": "recuentos_semanal"} -> lunes 10:00, control de recuentos por jefe (ver ov_recuentos.py)
(El correo de la mañana con capturas a Mercedes se retiro el 2026-10-16.)

IMPORTANTE sobre reintentos (configurar en la consola, ver README): EventBridge
Scheduler invoca Lambda de forma asincrona, y por defecto Lambda reintenta
automaticamente una invocacion asincrona que falla. Un reintento de
"mediodia"/"tarde" volveria a pedir aprobacion en Authenticator y a subir el Excel.
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
    if tarea not in ("mediodia", "tarde", "listar_buckets", "ov_prueba", "recuentos_semanal"):
        raise ValueError(
            f"Evento invalido, falta 'tarea' (mediodia/tarde/listar_buckets/ov_prueba/recuentos_semanal): {event}"
        )

    if tarea == "listar_buckets":
        # Diagnostico de una sola vez -- ver listar_buckets.py.
        import listar_buckets

        _correr(listar_buckets.main, "listar_buckets")
    elif tarea == "ov_prueba":
        # Entrada a la app OV de inventario -- ver ov_prueba.py.
        import ov_prueba

        _correr(ov_prueba.main, "ov_prueba")
    elif tarea == "recuentos_semanal":
        # Descarga Ver Conteos de la app OV y prepara/envia el correo de cada jefe -- ver ov_recuentos.py.
        import ov_recuentos

        _correr(ov_recuentos.main, "ov_recuentos")
    else:
        # "mediodia" (14:00) y "tarde" (17:30) hacen lo mismo: descargar la ruta
        # del dia siguiente y subirla a confirmaciones-sms.
        import descargar_ruta_y_subir

        _correr(descargar_ruta_y_subir.main, "descargar_ruta_y_subir")

    return {"tarea": tarea, "status": "ok"}
