/**
 * Apps Script para la hoja "Citas Confirmaciones SMS - Aurum" (pestaña "Citas").
 * Guarda esto en Extensiones > Apps Script de esa hoja y despliegalo como
 * Aplicacion web (ver README de confirmaciones-sms para los pasos).
 *
 * Endpoints (via query param ?action=... en GET, o body JSON con "action" en POST):
 *   - cargar      -> devuelve todas las citas guardadas
 *   - guardarTodo -> reemplaza todas las citas por las que llegan en el body
 *   - borrarTodo  -> limpia todas las citas (usado en la limpieza de medianoche)
 */

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

function respuestaJSON(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
