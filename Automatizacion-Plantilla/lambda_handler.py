"""
Punto de entrada de AWS Lambda para la automatizacion OFS. Traduce el evento
de entrada (uno por regla de EventBridge Scheduler) en la tarea que hay que
correr, replicando el mismo dispatch que ya tenia
.github/workflows/ofs-automation.yml segun github.event.schedule.

Evento esperado (lo manda el "Input" de cada regla de EventBridge Scheduler):
  {"tarea": "mediodia"}  -> 14:00, ruta del dia siguiente
  {"tarea": "tarde"}     -> 17:30, ruta del dia siguiente; martes y jueves, ademas, analisis de las RM
                            nuevas del mes con la misma sesion (ver rm_analizar.tras_ruta)
  {"tarea": "ov_prueba"} -> prueba de entrada a la app OV de inventario (manual, sin horario)
  {"tarea": "recuentos_semanal"} -> martes 10:00, control de recuentos por jefe (ver ov_recuentos.py)
  {"tarea": "recuentos_semanal", "respaldo": true} -> martes 12:00, solo si el de las 10:00 no salio
  {"tarea": "devoluciones_diario"} -> L-V 11:00, control de devoluciones por jefe (ver ov_devoluciones.py)
  {"tarea": "devoluciones_diario", "respaldo": true} -> L-V 13:00, solo si el de las 11:00 no salio
  {"tarea": "traspasos_diario"} -> L-V 8:00, aviso de traspasos InterWorker sin completar (ver ov_traspasos.py)
  {"tarea": "traspasos_diario", "respaldo": true} -> L-V 9:30, solo si el de las 8:00 no salio
  {"tarea": "ofs_rm_prueba"} -> prueba (manual): buscar mantenimientos repetidos en Oracle (ver ofs_rm_prueba.py)
  {"tarea": "rm_analizar", "mes": "Septiembre"} -> analiza las RM del mes para el dashboard de la app y se
                                  relanza sola hasta acabar (ver rm_analizar.py)
  {"tarea": "upselling_envio"} -> SIN horario: envia al Microsoft Form los lotes de Upselling aprobados en
                                  la app (ver forms_upselling.py). Lo arranca la URL de funcion (ver _desde_url).
(El correo de la mañana con capturas a Mercedes se retiro el 2026-10-16.)

URL de funcion (Function URL, auth NONE): solo la usa el Apps Script de la app cuando Anna pulsa
"Enviar al Form" en Upselling. Solo acepta {"tarea": "upselling_envio", "token": UPS_TOKEN}; cualquier
otra cosa -> 403. Responde enseguida y se arranca a si misma de forma asincrona para enviar.

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


def _desde_url(event, context):
    """Llamada por la URL de funcion (boton "Enviar al Form" de la app): comprobar la clave y arrancar
    upselling_envio de forma asincrona, para contestar al Apps Script sin esperar al envio."""
    import base64
    import hmac
    import json
    import os

    cuerpo = event.get("body") or ""
    if event.get("isBase64Encoded"):
        cuerpo = base64.b64decode(cuerpo).decode()
    try:
        datos = json.loads(cuerpo or "{}")
    except ValueError:
        datos = {}
    clave = os.environ.get("UPS_TOKEN", "")
    if datos.get("tarea") != "upselling_envio" or not clave or not hmac.compare_digest(str(datos.get("token", "")), clave):
        return {"statusCode": 403, "body": "sin permiso"}
    import boto3

    boto3.client("lambda").invoke(FunctionName=context.function_name, InvocationType="Event",
                                  Payload=json.dumps({"tarea": "upselling_envio"}).encode())
    return {"statusCode": 202, "body": "envio arrancado"}


def handler(event, context):
    if isinstance(event, dict) and "requestContext" in event:
        return _desde_url(event, context)
    tarea = (event or {}).get("tarea")
    if tarea not in ("mediodia", "tarde", "listar_buckets", "ov_prueba", "recuentos_semanal", "devoluciones_diario", "traspasos_diario", "ofs_rm_prueba", "rm_analizar", "upselling_envio"):
        raise ValueError(
            f"Evento invalido, falta 'tarea' (mediodia/tarde/listar_buckets/ov_prueba/recuentos_semanal/devoluciones_diario/traspasos_diario/ofs_rm_prueba/rm_analizar/upselling_envio): {event}"
        )

    if (event or {}).get("respaldo"):
        # Respaldos retirados (30/10/2026): si falla la tarea, Gustavo avisa a Claude y se lanza desde el Mac.
        # Las reglas de EventBridge siguen llamando, pero no se hace nada.
        print(f"[lambda] respaldo de {tarea} desactivado: no se hace nada")
        return {"ok": True, "respaldo": "desactivado"}

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

        _correr(lambda: ov_recuentos.main(respaldo=bool(event.get("respaldo"))), "ov_recuentos")
    elif tarea == "devoluciones_diario":
        # Descarga las devoluciones al almacen de la app OV y prepara/envia el correo de cada jefe.
        import ov_devoluciones

        _correr(lambda: ov_devoluciones.main(respaldo=bool(event.get("respaldo"))), "ov_devoluciones")
    elif tarea == "traspasos_diario":
        # Avisa de los traspasos InterWorker de dias anteriores sin aceptar (tecnicos + jefes).
        import ov_traspasos

        _correr(lambda: ov_traspasos.main(respaldo=bool(event.get("respaldo"))), "ov_traspasos")
    elif tarea == "ofs_rm_prueba":
        # Busca unos mantenimientos repetidos en Oracle y manda capturas/observaciones/historial.
        import ofs_rm_prueba

        _correr(lambda: ofs_rm_prueba.main(event.get("parejas")), "ofs_rm_prueba")
    elif tarea == "rm_analizar":
        # Analiza las RM del mes (ficha de Oracle + reglas) y guarda el resultado en la app.
        import rm_analizar

        return rm_analizar.main(event, context)
    elif tarea == "upselling_envio":
        # Envia al Microsoft Form UPSELLING el lote aprobado en la app, fila a fila.
        import forms_upselling

        _correr(lambda: forms_upselling.main(context), "forms_upselling")
    else:
        # "mediodia" (14:00) y "tarde" (17:30) hacen lo mismo: descargar la ruta
        # del dia siguiente y subirla a confirmaciones-sms. La tarde de martes y
        # jueves (dias del Excel de RM) aprovecha la misma sesion de Oracle para
        # analizar las RM nuevas del mes, si ya llego el correo.
        from datetime import datetime
        from zoneinfo import ZoneInfo

        import descargar_ruta_y_subir

        despues = None
        if tarea == "tarde" and datetime.now(ZoneInfo("Europe/Madrid")).weekday() in (1, 3):
            import rm_analizar

            despues = rm_analizar.tras_ruta(context)
        _correr(lambda: descargar_ruta_y_subir.main(despues), "descargar_ruta_y_subir")

    return {"tarea": tarea, "status": "ok"}
