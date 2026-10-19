/**
 * Apps Script para la hoja "Citas Confirmaciones SMS - Aurum" (pestaña "Citas").
 * Guarda esto en Extensiones > Apps Script de esa hoja y despliegalo como
 * Aplicacion web (ver README de confirmaciones-sms para los pasos).
 *
 * Endpoints (via query param ?action=... en GET, o body JSON con "action" en POST):
 *   - cargar      -> devuelve todas las citas guardadas
 *   - guardarTodo -> reemplaza todas las citas por las que llegan en el body
 *   - borrarTodo  -> limpia todas las citas (usado en la limpieza de medianoche)
 *   - registrarUso -> añade filas al registro de uso (pestaña "Uso"): quién entra,
 *                     envía SMS y marca Sí/No. Body: { eventos: [ {...}, ... ] }
 *   - leerUso      -> devuelve el registro de uso desde una fecha (?desde=AAAA-MM-DD)
 *   - leerResumen  -> devuelve el resumen diario desde una fecha (?desde=AAAA-MM-DD)
 *
 * Resumen diario (pestaña "Resumen diario"): cada dia de lunes a viernes, entre
 * las 23:00 y las 24:00, generarResumenDiario() guarda por cada tecnico con citas
 * cargadas si uso o no las confirmaciones ese dia. Se activa UNA vez ejecutando
 * instalarTriggerResumen() desde el editor.
 */

var COLUMNAS_USO = ['ts','fecha','mat','rol','accion','citaMat','citaFecha'];

var COLUMNAS_RESUMEN = ['fecha','mat','tecnico','citas','pendientes','enviadas','confirmadas',
                        'noConfirma','entro','accionesTecnico','accionesOtros','estado'];
var TZ = 'Europe/Madrid';

var COLUMNAS = ['id','tecnico','matricula','cliente','telefono','numMantenimiento',
                'timeslot','tipo','fecha','status','respuesta','horaRespuesta','sentAt'];

function doGet(e) {
  return manejarSolicitud(e);
}

function doPost(e) {
  return manejarSolicitud(e);
}

function manejarSolicitud(e) {
  var hoja = SpreadsheetApp.getActive().getSheetByName('Citas');
  var accion = (e.parameter.action || '').toString();

  if (!accion && e.postData) {
    try {
      var body = JSON.parse(e.postData.contents);
      accion = body.action || '';
    } catch (err) {
      // ignorar, se maneja abajo con el accion vacio
    }
  }

  if (accion === 'cargar') {
    return respuestaJSON({ ok: true, citas: leerCitas(hoja) });
  }

  if (accion === 'guardarTodo') {
    var body = JSON.parse(e.postData.contents);
    var citas = body.citas || [];
    escribirCitas(hoja, citas);
    return respuestaJSON({ ok: true, guardadas: citas.length });
  }

  if (accion === 'registrarUso') {
    var bodyUso = JSON.parse(e.postData.contents);
    var n = registrarUso(bodyUso.eventos || []);
    return respuestaJSON({ ok: true, guardados: n });
  }

  if (accion === 'leerUso') {
    var desde = String(e.parameter.desde || '');
    return respuestaJSON({ ok: true, eventos: leerUso(desde) });
  }

  if (accion === 'leerResumen') {
    return respuestaJSON({ ok: true, resumen: leerResumen(String(e.parameter.desde || '')) });
  }

  if (accion === 'borrarTodo') {
    escribirCitas(hoja, []);
    return respuestaJSON({ ok: true });
  }

  return respuestaJSON({ ok: false, error: 'Accion no reconocida: ' + accion });
}

function leerCitas(hoja) {
  var datos = hoja.getDataRange().getValues();
  var citas = [];
  for (var i = 1; i < datos.length; i++) {
    var fila = datos[i];
    if (fila[0] === '' || fila[0] === null || fila[0] === undefined) continue;
    var cita = {};
    for (var c = 0; c < COLUMNAS.length; c++) {
      var valor = fila[c];
      // Por si alguna celda quedo como fecha/numero real de Sheets en vez de
      // texto plano (defensivo, aunque escribirCitas ya fuerza texto plano).
      if (valor instanceof Date) {
        valor = Utilities.formatDate(valor, Session.getScriptTimeZone(), 'dd/MM/yyyy');
      }
      cita[COLUMNAS[c]] = String(valor);
    }
    cita.id = Number(cita.id);
    citas.push(cita);
  }
  return citas;
}

function escribirCitas(hoja, citas) {
  var filasActuales = hoja.getMaxRows();
  if (filasActuales > 1) {
    hoja.getRange(2, 1, filasActuales - 1, COLUMNAS.length).clearContent();
  }
  if (!citas || citas.length === 0) return;
  var rango = hoja.getRange(2, 1, citas.length, COLUMNAS.length);
  // Forzar formato de texto plano ANTES de escribir, para que Sheets no
  // convierta matricula/telefono en numeros ni la fecha en un objeto Date
  // (eso rompia el formato "31/07/2026" al leerlo de vuelta).
  rango.setNumberFormat('@');
  var datos = citas.map(function(c) {
    return COLUMNAS.map(function(col) { return (c[col] !== undefined && c[col] !== null) ? String(c[col]) : ''; });
  });
  rango.setValues(datos);
}

// ── Registro de uso ─────────────────────────────────────────────────────────
function hojaUso() {
  var ss = SpreadsheetApp.getActive();
  var hoja = ss.getSheetByName('Uso');
  if (!hoja) {
    hoja = ss.insertSheet('Uso');
    hoja.appendRow(COLUMNAS_USO);
    hoja.setFrozenRows(1);
    hoja.getRange('A:G').setNumberFormat('@'); // texto plano (fechas/matriculas tal cual)
  }
  return hoja;
}

function registrarUso(eventos) {
  if (!eventos || !eventos.length) return 0;
  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var hoja = hojaUso();
    var filas = eventos.map(function(ev) {
      return COLUMNAS_USO.map(function(col) { return ev[col] !== undefined && ev[col] !== null ? String(ev[col]) : ''; });
    });
    var rango = hoja.getRange(hoja.getLastRow() + 1, 1, filas.length, COLUMNAS_USO.length);
    rango.setNumberFormat('@');
    rango.setValues(filas);
    return filas.length;
  } finally {
    lock.releaseLock();
  }
}

function leerUso(desde) {
  var hoja = hojaUso();
  var datos = hoja.getDataRange().getValues();
  var out = [];
  for (var i = 1; i < datos.length; i++) {
    var ev = {};
    for (var c = 0; c < COLUMNAS_USO.length; c++) {
      var v = datos[i][c];
      if (v instanceof Date) v = Utilities.formatDate(v, Session.getScriptTimeZone(), c === 1 ? 'yyyy-MM-dd' : "yyyy-MM-dd'T'HH:mm:ss");
      ev[COLUMNAS_USO[c]] = String(v);
    }
    if (!ev.mat) continue;
    if (desde && ev.fecha < desde) continue;
    out.push(ev);
  }
  return out;
}

// ── Resumen diario: quién usó las confirmaciones ────────────────────────────
// estado: USO     -> el tecnico entro o movio alguna de sus citas
//         JE      -> el tecnico no entro, pero su jefe de equipo (u otro) movio sus citas
//         NO_USO  -> nadie toco sus citas ese dia
function hojaResumen() {
  var ss = SpreadsheetApp.getActive();
  var hoja = ss.getSheetByName('Resumen diario');
  if (!hoja) {
    hoja = ss.insertSheet('Resumen diario');
    hoja.appendRow(COLUMNAS_RESUMEN);
    hoja.setFrozenRows(1);
    hoja.getRange('A:L').setNumberFormat('@');
  }
  return hoja;
}

function fechaCitaISO_(f) {
  var m = /^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/.exec(String(f || '').trim());
  if (!m) return '';
  var anio = m[3].length === 2 ? '20' + m[3] : m[3];
  return anio + '-' + ('0' + m[2]).slice(-2) + '-' + ('0' + m[1]).slice(-2);
}

function generarResumenDiario() {
  var ahora = new Date();
  var hoy = Utilities.formatDate(ahora, TZ, 'yyyy-MM-dd');
  var diaSemana = Number(Utilities.formatDate(ahora, TZ, 'u')); // 1 = lunes ... 7 = domingo
  if (diaSemana >= 6) return 'fin de semana: no se genera';

  // Citas cargadas para dias posteriores a hoy (las que se confirmaban hoy)
  var citas = leerCitas(SpreadsheetApp.getActive().getSheetByName('Citas')).filter(function(c) {
    var f = fechaCitaISO_(c.fecha);
    return c.matricula && (!f || f > hoy);
  });
  var porTec = {};
  citas.forEach(function(c) {
    var m = String(c.matricula).toUpperCase();
    var r = porTec[m] || (porTec[m] = { tecnico: c.tecnico, citas: 0, pendientes: 0, enviadas: 0, confirmadas: 0, noConfirma: 0 });
    r.citas++;
    if (c.status === 'pendiente') r.pendientes++;
    else if (c.status === 'enviado') r.enviadas++;
    else if (c.status === 'confirmado') r.confirmadas++;
    else if (c.status === 'no_confirmado') r.noConfirma++;
  });

  // Actividad de hoy
  var eventos = leerUso(hoy).filter(function(ev) { return ev.fecha === hoy; });
  var filas = Object.keys(porTec).sort().map(function(m) {
    var r = porTec[m];
    var entro = eventos.some(function(ev) { return ev.mat === m && ev.accion === 'entrada'; });
    var propias = eventos.filter(function(ev) { return ev.mat === m && ev.accion !== 'entrada'; }).length;
    var otros = eventos.filter(function(ev) { return ev.citaMat === m && ev.mat !== m && ev.accion !== 'entrada'; }).length;
    var estado = (entro || propias) ? 'USO' : (otros ? 'JE' : 'NO_USO');
    return [hoy, m, r.tecnico, r.citas, r.pendientes, r.enviadas, r.confirmadas, r.noConfirma,
            entro ? 'SI' : 'NO', propias, otros, estado].map(String);
  });

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var hoja = hojaResumen();
    // Si se vuelve a generar el mismo dia, reemplazar las filas de ese dia
    var datos = hoja.getDataRange().getValues();
    for (var i = datos.length - 1; i >= 1; i--) {
      if (String(datos[i][0]) === hoy) hoja.deleteRow(i + 1);
    }
    if (filas.length) {
      var rango = hoja.getRange(hoja.getLastRow() + 1, 1, filas.length, COLUMNAS_RESUMEN.length);
      rango.setNumberFormat('@');
      rango.setValues(filas);
    }
  } finally {
    lock.releaseLock();
  }
  return filas.length + ' tecnicos guardados para ' + hoy;
}

function leerResumen(desde) {
  var hoja = hojaResumen();
  var datos = hoja.getDataRange().getValues();
  var out = [];
  for (var i = 1; i < datos.length; i++) {
    var r = {};
    for (var c = 0; c < COLUMNAS_RESUMEN.length; c++) r[COLUMNAS_RESUMEN[c]] = String(datos[i][c]);
    if (!r.mat) continue;
    if (desde && r.fecha < desde) continue;
    out.push(r);
  }
  return out;
}

// Ejecutar UNA vez desde el editor (Ejecutar > instalarTriggerResumen) y aceptar permisos.
function instalarTriggerResumen() {
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === 'generarResumenDiario') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('generarResumenDiario').timeBased().everyDays(1).atHour(23).inTimezone(TZ).create();
  return 'Activado: resumen diario de lunes a viernes entre las 23:00 y las 24:00';
}

function respuestaJSON(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
