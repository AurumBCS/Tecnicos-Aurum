#!/usr/bin/env python3
"""Actividades con las que salen los técnicos a las 8:00 y cuántas se terminan.

Cruza por número de mantenimiento los dos correos diarios de Verisure:
"Mantenimientos agendados a la apertura del día ..." y "... al cierre del día ...".
Los adjuntos se bajan a una carpeta temporal y se borran al terminar. Solo guarda
totales por día, equipo y técnico, ningún dato de clientes ni número de mantenimiento.

Desde el 26/11/2026 lo lanza la Lambda en las pasadas de agenda_vivo de antes de las 12:00, hasta que
haya llegado el correo de la apertura de hoy (Verisure manda los dos a las 7:58) y el cruce se haya subido.
Antes lo lanzaba tarde_mac.sh tras la tarea de las 8:00 del Mac. A mano (Mac):
    python3 agenda_cruce.py [fecha IMAP desde, por defecto 01-Sep-2026] [--sin-subir]
En la Lambda no compara con la lista de Oracle ni sube la de hoy: eso lo hace agenda_vivo.
Al terminar sube un registro por día y técnico a la app (Apps Script, type=agenda).
Además, si ya está la agenda de hoy, sube su lista (técnico, número, tipo, timeslot y orden,
sin datos del cliente) para el apartado "Cumplimiento de hoy" de la vista del JE (type=agenda-hoy).

Escribe en agenda-apertura-cierre (Mac) o en /tmp/agenda (Lambda):
    por_dia_jde.csv   un día y un equipo por fila (el total del día es la suma)
    por_tecnico.csv   todo el periodo por técnico
    razones.csv       razones de suspensión por equipo
    por_dia_tecnico.csv   un día y un técnico por fila, con las suspensiones por "cliente no está"
    razones_tecnico.csv   razones de suspensión por día y técnico
"""
import collections, csv, datetime, email, imaplib, io, json, os, pathlib, re, subprocess, sys, tempfile, urllib.parse, urllib.request

import openpyxl
from zoneinfo import ZoneInfo

ZONA = ZoneInfo('Europe/Madrid')

EN_LAMBDA = bool(os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))
_MAC = pathlib.Path('/Users/gustavoperez/Control Fichajes Tecnicos/agenda-apertura-cierre')
AQUI = pathlib.Path(os.environ.get('AGENDA_DIR') or ('/tmp/agenda' if EN_LAMBDA else (_MAC if _MAC.exists() else pathlib.Path(__file__).resolve().parent)))
INDEX = pathlib.Path(__file__).resolve().parent.parent / 'index.html'
EXEC = 'https://script.google.com/macros/s/AKfycbxotyAfeX08YR-Sx4QuYCt41SOwmfVX5ltxq4n0L2-XVJoahUkdlo4_EY8-SCDfVgR7/exec'
REMITE = 'no-replay.fieldservice@verisure.es'
# RECUENTOS_KEY del Apps Script; tarde_mac.sh la exporta, y si no se lee de aquí sin enseñarla
CLAVE_FICHERO = pathlib.Path('/Users/gustavoperez/Correo Recuentos/recuentos_clave.txt')
CAMPOS = ['salen', 'hecha_mismo', 'hecha_otro', 'suspendido', 'cancelado', 'no_aparece', 'otra_contrata', 'sin_estado']
PRIORIDAD = {'Completado': 3, 'Suspendido': 2, 'Cancelado': 1}
CLIENTE_NO_ESTA = 'Titular, cliente no está'
# Días que se dejan para que una actividad vuelva a salir antes de darla por "otra contrata"
MARGEN_DIAS = 7


def clave(servicio):
    # En la Lambda vienen en variables de entorno; en el Mac, del Llavero
    var = {'aurum-gmail-user': 'GMAIL_USER', 'aurum-gmail-pass': 'GMAIL_APP_PASSWORD'}.get(servicio)
    if var and os.environ.get(var, '').strip():
        return os.environ[var].strip()
    return subprocess.check_output(['security', 'find-generic-password', '-s', servicio, '-w'], text=True).strip()


def app_token():
    return os.environ.get('RECUENTOS_APP_TOKEN', '').strip() or \
        re.search(r'APP_TOKEN = "([^"]+)"', INDEX.read_text(encoding='utf-8')).group(1)


def subido_hoy():
    """True si el cruce ya se subió hoy a la app (para no repetirlo en cada pasada de agenda_vivo)."""
    url = os.environ.get('RECUENTOS_SCRIPT_URL', EXEC).strip() + '?' + urllib.parse.urlencode({'token': app_token(), 'type': 'agenda'})
    with urllib.request.urlopen(url, timeout=120) as r:
        act = str(json.loads(r.read().decode()).get('actualizado') or '')
    return act.startswith(datetime.datetime.now(ZONA).strftime('%Y-%m-%d'))


def bajar_adjuntos(destino, desde):
    imap = imaplib.IMAP4_SSL('imap.gmail.com')
    imap.login(clave('aurum-gmail-user'), clave('aurum-gmail-pass'))
    imap.select('INBOX', readonly=True)
    _, ids = imap.search(None, f'(FROM "{REMITE}" SINCE {desde} SUBJECT "agendados")')
    for i in ids[0].split():
        _, r = imap.fetch(i, '(BODY.PEEK[])')
        for parte in email.message_from_bytes(r[0][1]).walk():
            nombre = parte.get_filename()
            if nombre and re.fullmatch(r'Agenda \d{8} - \d+ (AM|PM)[+-]\d+ - AURUM\.xlsx', nombre):
                (destino / nombre).write_bytes(parte.get_payload(decode=True))
    imap.logout()


def leer(fichero):
    hoja = openpyxl.load_workbook(fichero, read_only=True, data_only=True).worksheets[0]
    filas = list(hoja.iter_rows(values_only=True))
    cab = [str(c) for c in filas[0]]
    col = cab.index('Número de Mantenimiento')
    return [dict(zip(cab, f)) for f in filas[1:] if len(f) > col and f[col]]


def matricula(tecnico):
    m = re.search(r'-\s*([A-Z]{0,2}\d{4,})\s*-', str(tecnico))
    return m[1] if m else '?'


def numero(fila):
    return str(fila['Número de Mantenimiento'])


def clasificar(fila, cierre):
    """Qué fue de una actividad de la apertura. Si hay varias filas al cierre, manda la mejor."""
    filas = cierre.get(numero(fila))
    if not filas:
        return 'no_aparece', None
    mejor = max(filas, key=lambda x: PRIORIDAD.get(x['Estado TOA'], 0))
    estado = mejor['Estado TOA']
    if estado == 'Completado':
        return ('hecha_mismo' if matricula(mejor['Técnico']) == matricula(fila['Técnico']) else 'hecha_otro'), mejor
    if estado in ('Suspendido', 'Cancelado'):
        return estado.lower(), mejor
    return 'sin_estado', mejor


def porcentaje(c, sin_otra_contrata=False):
    base = c['salen'] - (c['otra_contrata'] if sin_otra_contrata else 0)
    return round(100 * (c['hecha_mismo'] + c['hecha_otro']) / base, 1) if base else ''


def fecha(dia):
    return f'{dia[:4]}-{dia[4:6]}-{dia[6:]}'


def main(argv=None, solo_con_hoy=False):
    """solo_con_hoy (Lambda): si aún no ha llegado la apertura de hoy, no sube nada y devuelve False,
    para que lo intente la pasada siguiente. Devuelve True si ha hecho el cruce."""
    argv = sys.argv[1:] if argv is None else argv
    desde = next((a for a in argv if not a.startswith('--')), '01-Sep-2026')
    AQUI.mkdir(parents=True, exist_ok=True)
    url = os.environ.get('RECUENTOS_SCRIPT_URL', EXEC).strip() + '?' + urllib.parse.urlencode({'token': app_token(), 'type': 'recuentos'})
    gente = {x['Matricula']: x for x in csv.DictReader(io.StringIO(urllib.request.urlopen(url, timeout=180).read().decode()))}
    jde = lambda mat: gente[mat]['JDE'] if mat in gente else '?'
    nombre = lambda mat: f"{gente[mat]['Nombre(S)']} {gente[mat]['Apellidos(S)']}".strip() if mat in gente else ''

    por_dia_jde = collections.defaultdict(collections.Counter)
    por_dia_tec = collections.defaultdict(collections.Counter)
    por_tec = collections.defaultdict(collections.Counter)
    razones = collections.defaultdict(collections.Counter)
    razones_dia = collections.Counter()
    razones_tec = collections.Counter()
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = pathlib.Path(tmp)
        bajar_adjuntos(carpeta, desde)
        apertura, cierre_f = {}, {}
        for f in carpeta.glob('*.xlsx'):
            m = re.match(r'Agenda (\d{8}) - \d+ (AM|PM)', f.name)
            (apertura if m[2] == 'AM' else cierre_f)[m[1]] = f
        tablas = {('A', k): leer(f) for k, f in apertura.items()}
        tablas.update({('C', k): leer(f) for k, f in cierre_f.items()})
    hoy = datetime.datetime.now(ZONA).strftime('%Y%m%d')
    # Al salir del "with" los adjuntos ya están borrados
    if solo_con_hoy and ('A', hoy) not in tablas:
        print('[agenda] aún no ha llegado el correo de la apertura de hoy: se intenta en la pasada siguiente')
        return False

    ultimo = max(k for _, k in tablas)
    # Días en los que sale cada número, para saber si vuelve a Aurum más adelante
    sale_en = collections.defaultdict(set)
    for (_, k), filas in tablas.items():
        for fila in filas:
            sale_en[numero(fila)].add(k)
    dias = sorted(set(apertura) & set(cierre_f))
    for dia in dias:
        cierre = collections.defaultdict(list)
        for fila in tablas[('C', dia)]:
            cierre[numero(fila)].append(fila)
        salen = tablas[('A', dia)]
        nums = {numero(f) for f in salen}
        for fila in salen:
            cat, final = clasificar(fila, cierre)
            # Verisure pasa actividades a otras contratas durante el día (Gustavo, 05/11/2026).
            # Si no vuelve a salir en ningún Excel de Aurum, se cuenta como "otra contrata" y no
            # pesa en el porcentaje. Es aproximado: en los últimos días aún no ha dado tiempo a que vuelva.
            if cat == 'no_aparece' and not any(k > dia for k in sale_en[numero(fila)]):
                cat = 'otra_contrata'
            mat = matricula(fila['Técnico'])
            for c in (por_dia_jde[(dia, jde(mat))], por_dia_tec[(dia, mat)], por_tec[mat]):
                c[cat] += 1
                c['salen'] += 1
            if cat == 'suspendido':
                razon = str(final['Razones de Suspensión'] or 'Sin razón')
                razones[jde(mat)][razon] += 1
                razones_dia[(dia, jde(mat), razon)] += 1
                razones_tec[(dia, mat, razon)] += 1
        # Añadidas durante el día y completadas al cierre, por el técnico del cierre
        for n, v in cierre.items():
            mat = matricula(v[0]['Técnico'])
            for c in (por_dia_jde[(dia, jde(mat))], por_dia_tec[(dia, mat)]):
                if n not in nums:
                    c['anadidas'] += 1
                if any(x['Estado TOA'] == 'Completado' for x in v):
                    c['completadas_cierre'] += 1

    limite = (datetime.datetime.strptime(ultimo, '%Y%m%d') - datetime.timedelta(days=MARGEN_DIAS)).strftime('%Y%m%d')
    with open(AQUI / 'por_dia_jde.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['dia', 'jde', 'jefe', 'provincia', 'provisional'] + CAMPOS + ['anadidas', 'completadas_cierre'])
        for (dia, j), c in sorted(por_dia_jde.items()):
            w.writerow([fecha(dia), j, nombre(j), gente.get(j, {}).get('Provincia', ''), int(dia > limite)]
                       + [c[k] for k in CAMPOS] + [c['anadidas'], c['completadas_cierre']])
    with open(AQUI / 'por_tecnico.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['matricula', 'tecnico', 'jde', 'jefe', 'baja'] + CAMPOS + ['pct_terminadas', 'pct_sin_otra_contrata'])
        for mat, c in sorted(por_tec.items(), key=lambda kv: (jde(kv[0]), kv[0])):
            w.writerow([mat, nombre(mat), jde(mat), nombre(jde(mat)), gente.get(mat, {}).get('F Baja', '')]
                       + [c[k] for k in CAMPOS] + [porcentaje(c), porcentaje(c, True)])
    # Por técnico y día, con las suspensiones por "cliente no está" aparte (para medir las confirmaciones SMS)
    with open(AQUI / 'por_dia_tecnico.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['dia', 'matricula', 'jde', 'provisional'] + CAMPOS + ['susp_cliente_no_esta', 'anadidas', 'completadas_cierre'])
        for (dia, mat), c in sorted(por_dia_tec.items()):
            w.writerow([fecha(dia), mat, jde(mat), int(dia > limite)] + [c[k] for k in CAMPOS]
                       + [razones_tec[(dia, mat, CLIENTE_NO_ESTA)], c['anadidas'], c['completadas_cierre']])
    with open(AQUI / 'razones_tecnico.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['dia', 'matricula', 'razon', 'suspendidas'])
        for (dia, mat, r), n in sorted(razones_tec.items()):
            w.writerow([fecha(dia), mat, r, n])
    with open(AQUI / 'razones.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['jde', 'jefe', 'razon', 'suspendidas'])
        for j, cont in sorted(razones.items()):
            for r, n in cont.most_common():
                w.writerow([j, nombre(j), r, n])

    total = sum(por_dia_jde.values(), collections.Counter())
    print('Días cruzados:', len(dias), dias[0], dias[-1], '· último correo', ultimo)
    print('Total:', {k: total[k] for k in CAMPOS}, '% terminadas', porcentaje(total), 'sin otra contrata', porcentaje(total, True))

    # Subida a la app (pestaña "Agenda 8:00"): un registro por día y técnico, para verlo por meses
    filas = [dict({'dia': fecha(dia), 'mat': mat, 'tecnico': nombre(mat), 'jde': jde(mat), 'jefe': nombre(jde(mat)),
                   'provincia': gente.get(jde(mat), {}).get('Provincia', ''), 'provisional': int(dia > limite)},
                  **{k: c[k] for k in CAMPOS + ['anadidas', 'completadas_cierre']})
             for (dia, mat), c in sorted(por_dia_tec.items())]
    razones_filas = [{'dia': fecha(d), 'jde': j, 'razon': r, 'suspendidas': n} for (d, j, r), n in sorted(razones_dia.items())]
    if '--sin-subir' not in argv:
        subir(filas, razones_filas)
    if EN_LAMBDA:
        return True

    # Cumplimiento de hoy (vista del JE): lo que sale a las 8:00 es lo que cuenta en el KPI
    # "Cumplimiento de hoy" de la app: la lista la sube mac_tarde.py desde Oracle a las 8:00 (desde el 12/11) y
    # deja una copia en oracle_8/. Aquí se compara con el Excel de Verisure de las 8:00 (también los días
    # anteriores sin comparar, por si el correo llegó tarde). Solo si no hay copia de Oracle se sube la de Verisure.
    for (tipo, dia), filas_v in sorted(tablas.items()):
        if tipo == 'A' and dia >= '20261112':
            comparar_oracle(dia, filas_v)
    if ('A', hoy) in tablas and not (FOTOS / f'{fecha(hoy)}.json').exists():
        lista = [{'mat': matricula(f['Técnico']), 'tecnico': nombre(matricula(f['Técnico'])),
                  'jde': jde(matricula(f['Técnico'])), 'n': numero(f), 'tipo': f.get('Tipo de Actividad') or '',
                  'ts': f.get('Timeslot') or f.get('Ventana de Servicio') or '', 'orden': f.get('Orden en la Agenda') or ''}
                 for f in tablas[('A', hoy)]]
        print(f'[agenda] hoy: no está la lista de Oracle; se sube la de Verisure ({len(lista)} mantenimientos)')
        if '--sin-subir' not in argv:
            try:
                subir_hoy(fecha(hoy), lista)
            except Exception as e:
                print(f'[agenda] no se pudo subir la agenda de hoy: {e}')
    elif ('A', hoy) not in tablas:
        print('[agenda] aún no está la agenda de las 8:00 de hoy (la lista de la app sale de Oracle)')
    return True


FOTOS = AQUI / 'oracle_8'


def comparar_oracle(dia, filas_v):
    """Compara la lista de Oracle de las 8:00 con el Excel de Verisure; deja el resultado en oracle_8/dia.txt."""
    foto, res = FOTOS / f'{fecha(dia)}.json', FOTOS / f'{fecha(dia)}.txt'
    if not foto.exists() or res.exists():
        return
    o = {x['n']: x for x in json.loads(foto.read_text(encoding='utf-8'))}
    v = {numero(f): f for f in filas_v}
    comunes = set(o) & set(v)
    ts = lambda x: re.sub(r'\s', '', str(x or ''))
    otro_tec = [n for n in comunes if matricula(v[n]['Técnico']) != o[n]['mat']]
    otro_ts = [n for n in comunes if ts(v[n].get('Timeslot') or v[n].get('Ventana de Servicio')) != ts(o[n]['ts'])]
    otro_ord = [n for n in comunes if str(v[n].get('Orden en la Agenda') or '') != str(o[n]['orden'])]
    lineas = [f'{fecha(dia)}: Verisure {len(v)} · Oracle {len(o)} · en los dos {len(comunes)}',
              f'solo en Verisure {len(set(v) - set(o))} · solo en Oracle {len(set(o) - set(v))}',
              f'otro técnico {len(otro_tec)} · otro timeslot {len(otro_ts)} · otro orden {len(otro_ord)}']
    lineas += [f'  solo Verisure: {n} {matricula(v[n]["Técnico"])} {v[n].get("Tipo de Actividad")}' for n in sorted(set(v) - set(o))[:20]]
    lineas += [f'  solo Oracle: {n} {o[n]["mat"]} {o[n]["tipo"]}' for n in sorted(set(o) - set(v))[:20]]
    res.write_text('\n'.join(lineas) + '\n', encoding='utf-8')
    print('[agenda] comparación con Oracle: ' + ' | '.join(lineas[:3]))


def subir(filas, razones_filas):
    url = os.environ.get('RECUENTOS_SCRIPT_URL', EXEC).strip() + '?type=agenda'
    key = os.environ.get('RECUENTOS_KEY', '').strip() or CLAVE_FICHERO.read_text().strip()
    datos = json.dumps({'key': key, 'filas': filas, 'razones': razones_filas}).encode()
    req = urllib.request.Request(url, data=datos, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as r:
        res = json.loads(r.read().decode())
    if not res.get('ok'):
        raise RuntimeError('El Apps Script no guardó la agenda: ' + str(res.get('error')))
    print(f"[agenda] subidas {res.get('guardadas')} filas a la app ({res.get('actualizado')})")


def subir_hoy(dia, lista):
    url = os.environ.get('RECUENTOS_SCRIPT_URL', EXEC).strip() + '?type=agenda-hoy'
    key = os.environ.get('RECUENTOS_KEY', '').strip() or CLAVE_FICHERO.read_text().strip()
    datos = json.dumps({'key': key, 'dia': dia, 'filas': lista}).encode()
    req = urllib.request.Request(url, data=datos, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as r:
        res = json.loads(r.read().decode())
    if not res.get('ok'):
        raise RuntimeError('El Apps Script no guardó la agenda de hoy: ' + str(res.get('error')))
    print(f"[agenda] hoy: subidas {res.get('guardadas')} filas ({res.get('actualizado')})")


if __name__ == '__main__':
    main()
