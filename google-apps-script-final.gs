// ════════════════════════════════════════════════════════
//  IDs de Google Sheets
// ════════════════════════════════════════════════════════
const SHEET_RM_ID           = '1mdwknpTrcTmDGMnTB-NZQEh0eI5VClo0fsBmk1BLzNM';
const SHEET_CUMPLIMIENTO_ID = '1UL3XSri6UVsWRfoU94pV1l9falmDmztMKupeE8U2WIw';
const SHEET_CSV_ID          = '1UWfgzyAlu6sK6VLKP0Qoqhs31UfRju1J-zqaR8yuUng';
const SHEET_DOCS_ID         = '1clqnU3UH0ld86UoL4uvwp_ciAcMwRxeAjqDkbH4QZLc';
const SHEET_CUADRANTE_ID    = '1HqOI_kN10tAnBmeTrPqAklEa4f-1-DWQ';
const SHEET_FLOTA_ID        = '1c990k4SDrPULhP0VQ8xbZunBg7Qo9nhHl2tTDYPxh2s';
const SHEET_MEDALIA_ID      = '1_EVdRTQPwpMjg9PiJzsbq2_-OgDqBwmZof-cCO1iwoA';
const SHEET_FICHAJE_ID      = '1vPjN71Ss7PPm_5sstr2NVQdOAwvK-Fm3n5aYO3WsrpM';
const REMITENTE             = 'gustavoa.perez@verisure.es';
const REMITENTE_DIRECTO     = 'no-replay.fieldservice@verisure.es'; // mismos datos, llegan directo sin reenvio manual
const TZ_FICHAJE            = 'Europe/Madrid';

function doGet(e) {
  const type = e && e.parameter && e.parameter.type ? e.parameter.type : 'csv';
  try {
    if (type === 'track') {
      const mat = String(e.parameter.mat || '').trim();
      if (mat) registrarAcceso(mat);
      return ContentService.createTextOutput('ok').setMimeType(ContentService.MimeType.TEXT);
    }
    if (type === 'usage')         return servirUsage();
    if (type === 'docs')          return servirDocs();
    if (type === 'auth')          return servirAuth();
    if (type === 'flota')         return servirFlota();
    if (type === 'medalia')       return servirMedalia();
    if (type === 'vacaciones')    return servirVacaciones();
    if (type === 'medalia-coord') return servirMedialiaCoordinadores();
    if (type === 'cumplimiento')  return servirCumplimiento();
    if (type === 'rm')            return servirRM();
    if (type === 'jerarquia')     return servirJerarquia();
    if (type === 'fichaje')       return servirFichaje(e);
    if (type === 'meses') return servirMeses();
    if (type === 'csv' && e.parameter.mes) return servirCSVMes(e.parameter.mes);
    return servirCSV();
  } catch(err) {
    return ContentService.createTextOutput('Error: ' + err.message)
      .setMimeType(ContentService.MimeType.TEXT);
  }
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const mat = String(body.mat || '').trim().toUpperCase();
    const nombre = String(body.nombre || '').trim();
    const accion = String(body.accion || '').trim();
    const lat = body.lat !== undefined && body.lat !== null ? Number(body.lat) : '';
    const lng = body.lng !== undefined && body.lng !== null ? Number(body.lng) : '';

    if (!mat || !accion) {
      return jsonOutput({ok:false, error:'Faltan parámetros (mat/accion)'});
    }

    if (accion === 'entrada') return jsonOutput(registrarEntrada(mat, nombre, lat, lng));
    if (accion === 'salida')  return jsonOutput(registrarSalida(mat, nombre, lat, lng));

    return jsonOutput({ok:false, error:'Acción desconocida: ' + accion});
  } catch(err) {
    return jsonOutput({ok:false, error: err.message});
  }
}

function jsonOutput(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function registrarAcceso(mat) {
  try {
    const ss = SpreadsheetApp.openById(SHEET_CSV_ID);
    let sheet = ss.getSheetByName('AccesosApp');
    if (!sheet) {
      sheet = ss.insertSheet('AccesosApp');
      sheet.appendRow(['Timestamp', 'Matricula', 'FechaHora']);
    }
    const ahora = new Date();
    sheet.appendRow([
      ahora.toISOString(),
      mat.toUpperCase().trim(),
      Utilities.formatDate(ahora, 'Europe/Madrid', 'dd/MM/yyyy HH:mm')
    ]);
  } catch(e) { Logger.log('Error acceso: ' + e); }
}

function servirUsage() {
  try {
    const ss = SpreadsheetApp.openById(SHEET_CSV_ID);
    const sheet = ss.getSheetByName('AccesosApp');
    if (!sheet) return ContentService.createTextOutput('Matricula,Total,UltimoAcceso\n').setMimeType(ContentService.MimeType.TEXT);
    const data = sheet.getDataRange().getValues();
    const counts = {}, last = {};
    for (let i = 1; i < data.length; i++) {
      const mat = String(data[i][1]||'').toUpperCase().trim();
      if (!mat) continue;
      counts[mat] = (counts[mat]||0) + 1;
      last[mat] = String(data[i][2]||'');
    }
    let csv = 'Matricula,Total,UltimoAcceso\n';
    Object.keys(counts).sort((a,b)=>counts[b]-counts[a]).forEach(m => {
      csv += m + ',' + counts[m] + ',' + last[m] + '\n';
    });
    return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
  } catch(e) {
    return ContentService.createTextOutput('Matricula,Total,UltimoAcceso\n').setMimeType(ContentService.MimeType.TEXT);
  }
}

function servirCSV() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('csv_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);
  const ss = SpreadsheetApp.openById(SHEET_CSV_ID);
  const sheet = ss.getSheets()[0];
  const display = sheet.getDataRange().getDisplayValues();
  const csv = display.map(row =>
    row.map(cell => {
      const s = String(cell === null || cell === undefined ? '' : cell);
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? '"' + s.replace(/"/g, '""') + '"' : s;
    }).join(',')
  ).join('\n');
  cache.put('csv_data', csv, 300);
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

function servirDocs() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('docs_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);
  const ss = SpreadsheetApp.openById(SHEET_DOCS_ID);
  const sheet = ss.getSheets()[0];
  const data = sheet.getDataRange().getDisplayValues();
  const rows = [['mat', 'nMant', 'fecha', 'tipo', 'origen']];
  data.slice(1).forEach(row => {
    const nMant  = String(row[1]||'').trim();
    const fecha  = String(row[2]||'').trim();
    const mat    = String(row[3]||'').trim();
    const tipo   = String(row[4]||'').trim();
    const origen = String(row[6]||'').trim();
    if(mat && nMant) rows.push([mat, nMant, fecha, tipo, origen]);
  });
  const csv = rows.map(r => r.map(c => '"' + String(c||'').replace(/"/g, '""') + '"').join(',')).join('\n');
  cache.put('docs_data', csv, 300);
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

function parseCSV(csvText) {
  const lines = csvText.trim().split('\n');
  const result = [];
  for(let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const cells = [];
    let currentCell = '';
    let insideQuotes = false;
    for(let j = 0; j < line.length; j++) {
      const char = line[j];
      const nextChar = line[j + 1];
      if(char === '"') {
        if(insideQuotes && nextChar === '"') { currentCell += '"'; j++; }
        else { insideQuotes = !insideQuotes; }
      } else if(char === ',' && !insideQuotes) {
        cells.push(currentCell.trim()); currentCell = '';
      } else { currentCell += char; }
    }
    cells.push(currentCell.trim());
    result.push(cells);
  }
  return result;
}

function servirAuth() {
  try {
    const url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vSvU7Aah_5VokujbrbolwqCAZLRxrDQqrAZiNpgvNZMXeD-KCPLmJqRjIlPGmswlg/pub?output=csv';
    const csv = UrlFetchApp.fetch(url).getContentText('UTF-8');
    const data = Utilities.parseCsv(csv);
    const rows = [['Matricula', 'DNI']];
    data.slice(1).forEach(row => {
      const matricula = (row[4] || '').trim().toUpperCase();
      const dni = (row[7] || '').trim().toUpperCase();
      if(matricula && dni && matricula !== '****') rows.push([matricula, dni]);
    });
    const resultado = rows.map(r => r.map(c => '"' + String(c||'').replace(/"/g, '""') + '"').join(',')).join('\n');
    Logger.log('✓ AUTH: ' + (rows.length - 1) + ' matrículas cargadas');
    return ContentService.createTextOutput(resultado).setMimeType(ContentService.MimeType.TEXT);
  } catch(e) {
    Logger.log('✗ Error AUTH: ' + e.message);
    return ContentService.createTextOutput('Matricula,DNI').setMimeType(ContentService.MimeType.TEXT);
  }
}

function servirFlota() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('flota_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);
  const ss = SpreadsheetApp.openById(SHEET_FLOTA_ID);
  const sheet = ss.getSheetByName('INVENTARIO') || ss.getSheets()[0];
  const data = sheet.getDataRange().getDisplayValues();
  const rows = [['mat', 'coche']];
  data.slice(1).forEach(row => {
    const mat   = String(row[2]||'').trim().toUpperCase();
    const coche = String(row[3]||'').trim().toUpperCase();
    if(mat && coche && mat!=='TCO' && !mat.includes('DEVUELTO') && !mat.includes('TALLER') && !mat.includes('PERSONAL'))
      rows.push([mat, coche]);
  });
  const csv = rows.map(r => r.map(c => '"' + String(c||'').replace(/"/g, '""') + '"').join(',')).join('\n');
  cache.put('flota_data', csv, 300);
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

// ════════════════════════════════════════════════════════
//  SERVIR MEDALIA COORDINADORES (CSV)
//
//  Fuente: hoja publicada aparte (no la de emails), con columnas reales
//  MATRICULA, TERRITORIAL, ORIGEN, Fecha encuesta, N_Encuestas,
//  Suma_Nota_Global, Muestra -- confirmado leyendo el CSV en vivo. La
//  version anterior de esta funcion buscaba una columna "tipo" que no
//  existe en esta hoja (siempre vacia -> ninguna fila pasaba el filtro
//  "interaccion") y leia el puntaje de una columna P fija que tampoco
//  existe aqui -- por eso el endpoint devolvia el CSV vacio siempre.
//
//  En vez de exigir el mes calendario actual (que no tiene encuestas
//  todavia los primeros dias de cada mes), se usa el ULTIMO mes que
//  realmente tenga datos en la hoja, para que la app siempre muestre lo
//  mas reciente disponible en vez de quedar vacia a principio de mes.
// ════════════════════════════════════════════════════════
function servirMedialiaCoordinadores() {
  try {
    var url  = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTIbmLaEbAJoZj7d_lJqtIV-gbx2kTiumryL-Q7fpvkxvCs3PBaMiDCHTYpWHU-SQ1loy9eAT0G1X9n/pub?output=csv';
    var csv  = UrlFetchApp.fetch(url).getContentText('UTF-8');
    var data = Utilities.parseCsv(csv);
    if (data.length < 2) return ContentService.createTextOutput('mat,promedio,cantidad').setMimeType(ContentService.MimeType.TEXT);

    var headers   = data[0].map(function(h){ return String(h).trim().toLowerCase(); });
    var matIdx    = headers.findIndex(function(h){ return h.includes('matricula') || h.includes('matrícula'); });
    var origenIdx = headers.findIndex(function(h){ return h.includes('origen'); });
    var fechaIdx  = headers.findIndex(function(h){ return h.includes('fecha'); });
    var nIdx      = headers.findIndex(function(h){ return h.includes('n_encuestas'); });
    var sumaIdx   = headers.findIndex(function(h){ return h.includes('suma'); });

    // Primera pasada: parsear filas validas y detectar cual es el ultimo
    // mes (clave "AAAA-MM") que tiene al menos una encuesta real.
    var filas = [];
    var mejorClave = '';
    for (var i = 1; i < data.length; i++) {
      var row    = data[i];
      var mat    = String(row[matIdx]    || '').trim().toUpperCase();
      var origen = String(row[origenIdx] || '').trim().toUpperCase();
      var fecha  = String(row[fechaIdx]  || '').trim();
      var n      = parseInt(row[nIdx], 10);
      var suma   = parseFloat(String(row[sumaIdx] || '').replace(',', '.'));
      if (!mat || (origenIdx >= 0 && origen !== 'AURUM')) continue;
      if (!fecha || !n || isNaN(suma)) continue; // fila placeholder sin encuestas ese dia
      var partes = fecha.split('/');
      if (partes.length !== 3) continue;
      var mes  = parseInt(partes[1], 10);
      var anio = parseInt(partes[2], 10);
      if (!mes || !anio) continue;
      var clave = anio + '-' + (mes < 10 ? '0' + mes : mes);
      if (clave > mejorClave) mejorClave = clave;
      filas.push({ mat: mat, n: n, suma: suma, clave: clave });
    }

    var byMat = {};
    filas.forEach(function(f){
      if (f.clave !== mejorClave) return;
      if (!byMat[f.mat]) byMat[f.mat] = { sum: 0, count: 0 };
      byMat[f.mat].sum   += f.suma;
      byMat[f.mat].count += f.n;
    });

    var rows = [['mat', 'promedio', 'cantidad']];
    Object.keys(byMat).forEach(function(m){
      var d = byMat[m];
      rows.push([m, (d.sum / d.count).toFixed(2), d.count]);
    });
    var resultado = rows.map(function(r){
      return r.map(function(c){ return '"' + String(c||'').replace(/"/g,'""') + '"'; }).join(',');
    }).join('\n');
    return ContentService.createTextOutput(resultado).setMimeType(ContentService.MimeType.TEXT);
  } catch(e) {
    Logger.log('Error medalia: ' + e.message);
    return ContentService.createTextOutput('mat,promedio,cantidad').setMimeType(ContentService.MimeType.TEXT);
  }
}

function servirVacaciones() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('vacaciones_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);
  try {
    const url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vR9A0fhBk2ViKKewyKP8rJz364_MsEwi8CD_DEIjokUAeZiJzieR1k3KuZm6Kx9B68YrNTtalq8peFn/pub?output=csv';
    const csvText = UrlFetchApp.fetch(url).getContentText('UTF-8');
    const lines = csvText.trim().split('\n');
    if(lines.length < 3) return ContentService.createTextOutput('mat,consumido,disponible,ap_total').setMimeType(ContentService.MimeType.TEXT);
    const strip = s => String(s||'').trim().replace(/^"|"$/g,'');
    const monthRow = lines[0].split(',').map(strip);
    const headers  = lines[1].split(',').map(strip);
    const consumidosIdx  = headers.findIndex(h => /consumid/i.test(h));
    const disponiblesIdx = headers.findIndex(h => /disponib/i.test(h));
    if(consumidosIdx < 0 || disponiblesIdx < 0) throw new Error('Columnas no encontradas');
    const apTotalIdx = disponiblesIdx + 1;
    const meses = [];
    for(let c = 5; c < consumidosIdx; c += 2){
      const raw = monthRow[c] || '';
      const key = raw.replace(/[^a-z0-9]/gi,'').toLowerCase();
      if(key) meses.push({ key, vacCol: c, apCol: c+1 });
    }
    const headerParts = ['mat','consumido','disponible','ap_total'];
    meses.forEach(m => headerParts.push(m.key+'_vac', m.key+'_ap'));
    const rows = [headerParts];
    for(let i = 2; i < lines.length; i++){
      const cells = lines[i].split(',').map(strip);
      const mat = (cells[1]||'').toUpperCase();
      if(!mat) continue;
      const row = [mat, parseInt(cells[consumidosIdx])||0, parseInt(cells[disponiblesIdx])||0,
        apTotalIdx < cells.length ? (parseInt(cells[apTotalIdx])||0) : 0];
      meses.forEach(m => { row.push(parseInt(cells[m.vacCol])||0); row.push(parseInt(cells[m.apCol])||0); });
      rows.push(row);
    }
    const resultado = rows.map(r => r.map(c => '"' + String(c||'').replace(/"/g,'""') + '"').join(',')).join('\n');
    try { cache.put('vacaciones_data', resultado, 300); } catch(e){}
    Logger.log('✓ Vacaciones: ' + (rows.length-1) + ' técnicos, ' + meses.length + ' meses');
    return ContentService.createTextOutput(resultado).setMimeType(ContentService.MimeType.TEXT);
  } catch(e) {
    Logger.log('✗ Error vacaciones: ' + e.toString());
    return ContentService.createTextOutput('mat,consumido,disponible,ap_total').setMimeType(ContentService.MimeType.TEXT);
  }
}

function servirJerarquia() {
  try {
    const url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vSvU7Aah_5VokujbrbolwqCAZLRxrDQqrAZiNpgvNZMXeD-KCPLmJqRjIlPGmswlg/pub?output=csv';
    const csv = UrlFetchApp.fetch(url).getContentText('UTF-8');
    const data = Utilities.parseCsv(csv);
    const rows = [['JE','Matricula','Zona','CuentaJE','CuentaEmpresa']];
    data.slice(1).forEach(row => {
      const zona      = (row[2]  || '').trim();
      const je        = (row[3]  || '').trim().toUpperCase();
      const mat       = (row[4]  || '').trim().toUpperCase();
      const cuentaJE  = (row[21] || '').trim();
      const cuentaEmp = (row[22] || '').trim();
      if(je && mat && mat !== '****' && je !== 'CM9651') rows.push([je, mat, zona, cuentaJE, cuentaEmp]);
    });
    const resultado = rows.map(r => r.map(c=>'"'+String(c||'').replace(/"/g,'""')+'"').join(',')).join('\n');
    return ContentService.createTextOutput(resultado).setMimeType(ContentService.MimeType.TEXT);
  } catch(e) {
    return ContentService.createTextOutput('JE,Matricula,Zona,CuentaJE,CuentaEmpresa').setMimeType(ContentService.MimeType.TEXT);
  }
}

function obtenerNombresTecnicos() {
  const ss    = SpreadsheetApp.openById(SHEET_CUADRANTE_ID);
  const sheet = ss.getSheets()[0];
  const data  = sheet.getDataRange().getValues();
  const nombres = {};
  data.slice(1).forEach(row => {
    const mat    = String(row[4]||'').trim();
    const nombre = String(row[0]||'').trim();
    if(mat && nombre) nombres[mat] = nombre;
  });
  return nombres;
}

function mapearTerritorioAZona(territorial) {
  if(territorial.includes('3304') || territorial.includes('3305')) return 'Zona 4-5';
  if(territorial.includes('3306') || territorial.includes('3307')) return 'Zona 6-7';
  return 'Otra';
}

function onEdit(e) { limpiarCache(); }

function limpiarCache() {
  CacheService.getScriptCache().removeAll([
    'csv_data','docs_data','auth_data','flota_data',
    'medalia_data','vacaciones_data','cumplimiento_data',
    'rm_data','medalia_coordinadores_data'
  ]);
  Logger.log('Caché limpiado');
}

function configurarTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('procesarCorreosAurum').timeBased().everyHours(1).create();
  Logger.log('✓ Trigger configurado');
}

const CORREOS_LABEL_PROCESADO = 'Procesado-Aurum';

function procesarCorreosAurum() {
  // El RM puede llegar de remitentes distintos a los dos conocidos (REMITENTE/
  // REMITENTE_DIRECTO) -- en vez de mantener una lista de remitentes, se busca
  // tambien por el asunto, que siempre es "Repeated Maintenance Aurum <mes>"
  // sin importar quien lo envie. La clasificacion por asunto (esRM, mas abajo)
  // ya funcionaba bien; lo que faltaba era que la busqueda de Gmail ni
  // siquiera traia esos correos si el remitente no coincidia.
  const query = `(from:${REMITENTE} OR from:${REMITENTE_DIRECTO} OR subject:"Repeated Maintenance Aurum") is:unread has:attachment`;
  const threads = GmailApp.search(query);
  if (threads.length === 0) { Logger.log('Sin correos nuevos.'); return; }
  const label = getOrCreateLabel_(CORREOS_LABEL_PROCESADO);
  threads.forEach(thread => {
    let algoProcesado = false;
    thread.getMessages().forEach(message => {
      if (!message.isUnread()) return;
      const asunto = message.getSubject().toLowerCase();
      message.getAttachments().forEach(attachment => {
        const nombre = attachment.getName().toLowerCase();
        if (!nombre.endsWith('.xlsx') && !nombre.endsWith('.xls') && !nombre.endsWith('.csv')) return;
        const esRM           = asunto.includes('repeated maintenance') || nombre.startsWith('tabla');
        const esCumplimiento = asunto.includes('cumplimiento') || nombre.includes('cumplimiento');
        const esMedalia      = asunto.includes('notas globales') || asunto.includes('medalia') || nombre.includes('detalle encuestas');
        const esCSV          = (nombre.endsWith('.csv') || asunto.includes('resumen')) && !esRM && !esCumplimiento && !esMedalia;
        if (esRM)                { actualizarSheet(SHEET_RM_ID, attachment, 'RM'); algoProcesado = true; }
        else if (esCumplimiento) { actualizarSheet(SHEET_CUMPLIMIENTO_ID, attachment, 'Cumplimiento'); algoProcesado = true; }
        else if (esMedalia)      { actualizarSheet(SHEET_MEDALIA_ID, attachment, 'Medalia'); algoProcesado = true; }
        else if (esCSV)          { actualizarSheet(SHEET_CSV_ID, attachment, 'CSV'); algoProcesado = true; }
      });
      message.markRead();
    });
    // Etiqueta visible en Gmail (aparte de "leido") para poder confirmar a
    // simple vista que el script SI encontro y proceso este correo, y no
    // que alguien simplemente lo abrio manualmente.
    if (algoProcesado) thread.addLabel(label);
  });
}

function actualizarSheet(sheetId, attachment, tipo) {
  try {
    const ss    = SpreadsheetApp.openById(sheetId);
    const sheet = ss.getSheets()[0];
    let datos   = [];
    const nombre = attachment.getName().toLowerCase();
    if (nombre.endsWith('.csv')) {
      Logger.log(`Procesando CSV para ${tipo}...`);
      datos = Utilities.parseCsv(attachment.getDataAsString('UTF-8'));
    } else if (nombre.endsWith('.xlsx') || nombre.endsWith('.xls')) {
      Logger.log(`Procesando Excel para ${tipo}...`);
      const blob       = attachment.copyBlob();
      const tempFile   = DriveApp.createFile(blob);
      const tempFileId = tempFile.getId();
      try {
        Utilities.sleep(1000);
        const accessToken = ScriptApp.getOAuthToken();
        const exportUrl   = `https://docs.google.com/spreadsheets/d/${tempFileId}/export?format=csv`;
        const response    = UrlFetchApp.fetch(exportUrl, {
          method: 'get',
          headers: { Authorization: 'Bearer ' + accessToken },
          muteHttpExceptions: true
        });
        const csvContent = response.getContentText('UTF-8');
        if (csvContent && csvContent.length > 0) {
          Logger.log(`✓ Exportado a CSV`);
          datos = Utilities.parseCsv(csvContent);
        } else { Logger.log(`⚠ Respuesta vacía`); return; }
      } catch(e) {
        Logger.log(`✗ Error exportando Excel: ${e.message}`); return;
      } finally {
        try { tempFile.setTrashed(true); } catch(e) {}
      }
    }
    if (!datos || !datos.length) { Logger.log(`⚠ Sin datos en ${tipo}`); return; }
    sheet.clearContents();
    sheet.getRange(1, 1, datos.length, datos[0].length).setValues(datos);
    limpiarCache();
    Logger.log(`✓ ${tipo} actualizado: ${datos.length} filas`);
  } catch(e) {
    Logger.log(`✗ Error ${tipo}: ${e.message}`);
  }
}

function fixMojibake_(str) {
  if (!str) return str;
  if (str.indexOf('Ã') === -1 && str.indexOf('Â') === -1) return str;
  try {
    return decodeURIComponent(escape(str));
  } catch(e) {
    return str;
  }
}

function servirCumplimiento() {
  try {
    const cached = CacheService.getScriptCache().get('cumplimiento_data');
    if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);
  } catch(e) {}
  let resultado = 'mat,territorial,averia,cumplido,razon,nmant\n';
  try {
    const ss    = SpreadsheetApp.openById(SHEET_CUMPLIMIENTO_ID);
    const sheet = ss.getSheetByName('Cumplimiento_Aurum') || ss.getSheets()[0];
    const data  = sheet.getDataRange().getDisplayValues();
    if(data && data.length >= 2) {
      const hdr = data[0].map(h => String(h||'').trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,''));
      const idx = n => { const i = hdr.indexOf(n); return i >= 0 ? i : null; };
      const iMat      = idx('mat')         ?? idx('matricula') ?? idx('tecnico') ?? 3;
      const iTerrit   = idx('territorial') ?? 4;
      const iAveria   = idx('averia')      ?? idx('av/noav')   ?? 7;
      const iCumplido = idx('cumplido')    ?? 8;
      const iRazon    = idx('razon')       ?? 9;
      const iMant     = idx('code maintenance ibs') ?? idx('mantenimiento') ?? 2;
      Logger.log('CUM cols -> mat:'+iMat+' cumplido:'+iCumplido+' mant:'+iMant+' filas:'+(data.length-1));
      const rows = [['mat','territorial','averia','cumplido','razon','nmant']];
      for(let i = 1; i < data.length; i++) {
        const row = data[i];
        const mat = String(row[iMat] ?? '').trim().toUpperCase();
        if(!mat) continue;
        rows.push([
          mat,
          fixMojibake_(String(row[iTerrit]??'').trim()),
          fixMojibake_(String(row[iAveria]??'').trim()),
          String(row[iCumplido]??'').trim(),
          fixMojibake_(String(row[iRazon]??'').trim()),
          String(row[iMant]??'').trim()
        ]);
      }
      resultado = rows.map(r => r.map(c => '"'+String(c||'').replace(/"/g,'""')+'"').join(',')).join('\n');
      Logger.log('Cumplimiento OK: '+(rows.length-1)+' registros');
      if(resultado.length < 95000) {
        try { CacheService.getScriptCache().put('cumplimiento_data', resultado, 300); } catch(e) {}
      }
    }
  } catch(e) { Logger.log('Error Cumplimiento: ' + e.toString()); }
  return ContentService.createTextOutput(resultado).setMimeType(ContentService.MimeType.TEXT);
}

function servirRM() {
  try {
    const cached = CacheService.getScriptCache().get('rm_data');
    if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);
  } catch(e) {}
  let resultado = 'nMant,motivo,tecnico,territorial,repetido,motivo_post,averia,nMantPost\n';
  try {
    const ss    = SpreadsheetApp.openById(SHEET_RM_ID);
    const sheet = ss.getSheetByName('Hoja 1') || ss.getSheets()[0];
    const data  = sheet.getDataRange().getDisplayValues();
    if(data && data.length >= 2) {
      const hdr = data[0].map(h => String(h||'').trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,''));
      const idx = n => { const i = hdr.indexOf(n); return i >= 0 ? i : null; };
      const iNMant      = idx('mantenimiento') ?? idx('nmant')       ?? 4;
      const iMotivo     = idx('motivo')        ?? 6;
      const iTecnico    = idx('tecnico')        ?? 7;
      const iTerrit     = idx('territorial')    ?? 8;
      const iRepetido   = idx('repetido')       ?? 11;
      const iNMantPost  = idx('mantenimiento post') ?? idx('nmant_post') ?? 12;
      const iMotivoPost = idx('motivo post')    ?? idx('motivo_post') ?? 14;
      const iAveria     = idx('av/noav')         ?? idx('averia')     ?? 5;
      Logger.log('RM cols -> nMant:'+iNMant+' nMantPost:'+iNMantPost+' tecnico:'+iTecnico+' filas:'+(data.length-1));
      const rows = [['nMant','motivo','tecnico','territorial','repetido','motivo_post','averia','nMantPost']];
      for(let i = 1; i < data.length; i++) {
        const row     = data[i];
        const nMant   = String(row[iNMant]   ?? '').trim();
        const tecnico = String(row[iTecnico] ?? '').trim().toUpperCase();
        if(!nMant || !tecnico) continue;
        rows.push([nMant, String(row[iMotivo]??'').trim(), tecnico, String(row[iTerrit]??'').trim(),
          String(row[iRepetido]??'').trim(), String(row[iMotivoPost]??'').trim(), String(row[iAveria]??'').trim(),
          String(row[iNMantPost]??'').trim()]);
      }
      resultado = rows.map(r => r.map(c => '"'+String(c||'').replace(/"/g,'""')+'"').join(',')).join('\n');
      Logger.log('RM OK: '+(rows.length-1)+' registros');
      if(resultado.length < 95000) {
        try { CacheService.getScriptCache().put('rm_data', resultado, 300); } catch(e) {}
      }
    }
  } catch(e) { Logger.log('Error RM: ' + e.toString()); }
  return ContentService.createTextOutput(resultado).setMimeType(ContentService.MimeType.TEXT);
}
function debugAuth() {
  var url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vSvU7Aah_5VokujbrbolwqCAZLRxrDQqrAZiNpgvNZMXeD-KCPLmJqRjIlPGmswlg/pub?output=csv';
  var csv = UrlFetchApp.fetch(url).getContentText('UTF-8');
  var data = parseCSV(csv);
  for (var i = 1; i < data.length; i++) {
    var matricula = (data[i][4] || '').toString().trim().toUpperCase();
    var dni = (data[i][8] || '').toString().trim().toUpperCase();
    if (!matricula || !dni || matricula === '****')
      Logger.log('Fila ' + (i+1) + ': mat=[' + data[i][4] + '] dni=[' + data[i][8] + ']');
  }
  Logger.log('Total filas procesadas: ' + (data.length - 1));
}

function debugMedalia() {
  var sheetId = '1_EVdRTQPwpMjg9PiJzsbq2_-OgDqBwmZof-cCO1iwoA';
  var sheet = SpreadsheetApp.openById(sheetId).getSheets()[0];
  var data = sheet.getDataRange().getValues();
  Logger.log('Total filas: ' + data.length);
  Logger.log('Col A[0]: ' + data[0][0]);
  Logger.log('Col E[0]: ' + data[0][4]);
  Logger.log('Col Q[0]: ' + data[0][16]);
  var vistos = {};
  for (var i = 1; i < data.length; i++) {
    var tipo = String(data[i][0] || '').trim();
    if (tipo && !vistos[tipo]) {
      vistos[tipo] = true;
      Logger.log('Tipo: [' + tipo + '] | E: [' + data[i][4] + '] | Q: [' + data[i][16] + ']');
    }
    if (Object.keys(vistos).length >= 8) break;
  }
}
// ══════════════════════════════════════════════
//  AUTOMATIZACION: Mtos_Finalizados_Aurum
//  Gmail -> Drive (revisa cada hora, sobrescribe siempre el mismo archivo)
// ══════════════════════════════════════════════

var MTOS_REMITENTE = 'gustavoa.perez@verisure.es';
var MTOS_NOMBRE_ADJUNTO = 'Mtos_Finalizados_Aurum';
var MTOS_CARPETA_NOMBRE = 'Mtos Finalizados Aurum';
var MTOS_LABEL_PROCESADO = 'Procesado-MtosFinalizados';

function procesarMtosFinalizados() {
  var label = getOrCreateLabel_(MTOS_LABEL_PROCESADO);
  var carpeta = getOrCreateCarpeta_(MTOS_CARPETA_NOMBRE);

  var query = '(from:' + MTOS_REMITENTE + ' OR from:' + REMITENTE_DIRECTO + ') has:attachment -label:' + MTOS_LABEL_PROCESADO;
  var threads = GmailApp.search(query, 0, 20);

  if (threads.length === 0) {
    Logger.log('Sin correos nuevos de ' + MTOS_REMITENTE + ' ni ' + REMITENTE_DIRECTO);
    return;
  }

  threads.forEach(function(thread) {
    var messages = thread.getMessages();
    var encontrado = false;

    messages.forEach(function(message) {
      var attachments = message.getAttachments();
      attachments.forEach(function(attachment) {
        var nombreArchivo = attachment.getName();
        if (nombreArchivo.indexOf(MTOS_NOMBRE_ADJUNTO) === 0) {
          guardarEnDrive_(attachment, carpeta);
          encontrado = true;
        }
      });
    });

    if (encontrado) {
      thread.addLabel(label);
      Logger.log('Procesado y etiquetado: ' + thread.getFirstMessageSubject());
    }
  });
}

function guardarEnDrive_(attachment, carpeta) {
  var nombreFinal = MTOS_NOMBRE_ADJUNTO + '.xlsx';

  var existentes = carpeta.getFilesByName(nombreFinal);
  while (existentes.hasNext()) {
    existentes.next().setTrashed(true);
  }

  carpeta.createFile(attachment.copyBlob().setName(nombreFinal));
  Logger.log('Archivo guardado en Drive: ' + nombreFinal);
}

function getOrCreateCarpeta_(nombre) {
  var carpetas = DriveApp.getFoldersByName(nombre);
  if (carpetas.hasNext()) return carpetas.next();
  return DriveApp.createFolder(nombre);
}

function getOrCreateLabel_(nombre) {
  var label = GmailApp.getUserLabelByName(nombre);
  if (!label) label = GmailApp.createLabel(nombre);
  return label;
}
function instalarTriggerMtosFinalizados() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === 'procesarMtosFinalizados') {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  ScriptApp.newTrigger('procesarMtosFinalizados')
    .timeBased()
    .everyHours(1)
    .create();
  Logger.log('Trigger instalado: procesarMtosFinalizados cada hora');
}
function servirMeses() {
  try {
    const ss = SpreadsheetApp.openById(SHEET_CSV_ID);
    const nombresValidos = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
    const meses = ss.getSheets()
      .map(s => s.getName())
      .filter(n => nombresValidos.indexOf(n) !== -1);
    return ContentService.createTextOutput(meses.join(',')).setMimeType(ContentService.MimeType.TEXT);
  } catch(e) {
    return ContentService.createTextOutput('').setMimeType(ContentService.MimeType.TEXT);
  }
}

function servirCSVMes(mes) {
  try {
    const ss = SpreadsheetApp.openById(SHEET_CSV_ID);
    const sheet = ss.getSheetByName(mes);
    if (!sheet) return ContentService.createTextOutput('').setMimeType(ContentService.MimeType.TEXT);
    const display = sheet.getDataRange().getDisplayValues();
    const csv = display.map(row =>
      row.map(cell => {
        const s = String(cell === null || cell === undefined ? '' : cell);
        return s.includes(',') || s.includes('"') || s.includes('\n')
          ? '"' + s.replace(/"/g, '""') + '"' : s;
      }).join(',')
    ).join('\n');
    return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
  } catch(e) {
    return ContentService.createTextOutput('').setMimeType(ContentService.MimeType.TEXT);
  }
}

// ════════════════════════════════════════════════════════
//  FICHAJE — registro horario legal (RD-ley 8/2019)
// ════════════════════════════════════════════════════════

// Cabecera fija de la hoja "Registro"
const FICHAJE_COLS = ['fecha','mat','nombre','horaEntrada','horaComida','horaSalida','tipoCierre','timestampEntrada','timestampSalida','latEntrada','lngEntrada','latSalida','lngSalida'];

function fechaHoyFichaje() {
  return Utilities.formatDate(new Date(), TZ_FICHAJE, 'yyyy-MM-dd');
}

function horaActualFichaje() {
  return Utilities.formatDate(new Date(), TZ_FICHAJE, 'HH:mm');
}

function getHojaFichaje(nombreHoja) {
  if (!SHEET_FICHAJE_ID) throw new Error('SHEET_FICHAJE_ID no configurado. Ejecuta crearHojaFichaje() primero.');
  const ss = SpreadsheetApp.openById(SHEET_FICHAJE_ID);
  return ss.getSheetByName(nombreHoja);
}

// Google Sheets convierte automáticamente "2026-07-27" y "09:24" a Date/Time internos
// al escribirlos con appendRow/setValue. getValues() entonces devuelve un objeto Date,
// no el texto original. Estas funciones normalizan cualquiera de los dos casos.
function normalizarFecha(val) {
  if (val instanceof Date) return Utilities.formatDate(val, TZ_FICHAJE, 'yyyy-MM-dd');
  return String(val||'').trim();
}
function normalizarHora(val) {
  if (val instanceof Date) return Utilities.formatDate(val, TZ_FICHAJE, 'HH:mm');
  return String(val||'').trim();
}

// Crea (una sola vez) el spreadsheet "Fichajes Aurum" con las hojas Registro y Faltantes.
// Ejecutar manualmente desde el editor de Apps Script; el ID resultante se pega en SHEET_FICHAJE_ID.
function crearHojaFichaje() {
  const ss = SpreadsheetApp.create('Fichajes Aurum');

  const registro = ss.getSheets()[0];
  registro.setName('Registro');
  registro.appendRow(FICHAJE_COLS);
  registro.setFrozenRows(1);
  // Forzar texto plano en fecha/horas para que Sheets no las autoconvierta a Date/Time
  registro.getRange('A:A').setNumberFormat('@');
  registro.getRange('D:D').setNumberFormat('@');
  registro.getRange('F:F').setNumberFormat('@');

  const faltantes = ss.insertSheet('Faltantes');
  faltantes.appendRow(['fecha','mat','nombre']);
  faltantes.setFrozenRows(1);

  Logger.log('✓ Hoja creada. Copia este ID en SHEET_FICHAJE_ID: ' + ss.getId());
  return ss.getId();
}

// Repara la hoja YA CREADA (creada antes de este fix): fuerza texto plano en fecha/horas
// y limpia las filas de prueba TEST999. Ejecutar UNA VEZ, después de actualizar el código.
function repararFormatoHojaFichaje() {
  const sheet = getHojaFichaje('Registro');
  const numFilas = sheet.getLastRow();
  if (numFilas >= 2) {
    ['A','D','F'].forEach(col => {
      const rango = sheet.getRange(col + '2:' + col + numFilas);
      const textos = rango.getDisplayValues();
      rango.setNumberFormat('@');
      rango.setValues(textos);
    });
  }
  sheet.getRange('A:A').setNumberFormat('@');
  sheet.getRange('D:D').setNumberFormat('@');
  sheet.getRange('F:F').setNumberFormat('@');

  // Limpiar filas de prueba
  const data = sheet.getDataRange().getValues();
  let eliminadas = 0;
  for (let i = data.length - 1; i >= 1; i--) {
    if (String(data[i][1]).trim().toUpperCase() === 'TEST999') {
      sheet.deleteRow(i + 1);
      eliminadas++;
    }
  }
  Logger.log('✓ Formato reparado (' + (numFilas-1) + ' filas) · ' + eliminadas + ' filas de prueba eliminadas');
}

// Añade las columnas de geolocalización (latEntrada, lngEntrada, latSalida, lngSalida) a
// una hoja "Registro" creada ANTES de este cambio. Ejecutar una sola vez.
function migrarColumnasGeolocalizacion() {
  const sheet = getHojaFichaje('Registro');
  const colsActuales = sheet.getLastColumn();
  if (colsActuales >= FICHAJE_COLS.length) {
    Logger.log('✓ La hoja ya tiene las ' + FICHAJE_COLS.length + ' columnas, no hace falta migrar.');
    return;
  }
  const nuevasCabeceras = FICHAJE_COLS.slice(colsActuales);
  sheet.getRange(1, colsActuales + 1, 1, nuevasCabeceras.length).setValues([nuevasCabeceras]);
  Logger.log('✓ Columnas añadidas: ' + nuevasCabeceras.join(', '));
}

// Configura el trigger diario de cierre automático + faltantes (ejecutar una vez).
function configurarTriggerFichaje() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'procesoFichajeNocturno')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('procesoFichajeNocturno').timeBased().everyDays(1).atHour(22).create();
  Logger.log('✓ Trigger de fichaje configurado (22:00 diario)');
}

// Ejecutado por el trigger de las 22:00: cierra jornadas abiertas y genera el listado de faltantes.
function procesoFichajeNocturno() {
  cerrarJornadasPendientes();
  generarFaltantesDiario();
}

// ── SERVIR (GET) ──────────────────────────────────────────
function servirFichaje(e) {
  try {
    const fecha = (e.parameter.fecha || fechaHoyFichaje()).trim();
    const sheet = getHojaFichaje('Registro');
    const data = sheet.getDataRange().getDisplayValues();

    const rows = [FICHAJE_COLS];
    data.slice(1).forEach(row => {
      if (String(row[0]||'').trim() === fecha) rows.push(row);
    });

    const csv = rows.map(r => r.map(c => '"' + String(c===null||c===undefined?'':c).replace(/"/g,'""') + '"').join(',')).join('\n');
    return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);

  } catch(err) {
    Logger.log('✗ Error servirFichaje: ' + err.message);
    return ContentService.createTextOutput(FICHAJE_COLS.join(',')).setMimeType(ContentService.MimeType.TEXT);
  }
}

// ── POST: fichar entrada ──────────────────────────────────
function registrarEntrada(mat, nombre, lat, lng) {
  // LockService: dos pulsaciones casi simultáneas (doble clic/doble toque) podían pasar
  // ambas la comprobación de "ya existe" antes de que la primera terminara de guardarse,
  // creando dos filas para la misma persona el mismo día. El lock serializa el acceso.
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = getHojaFichaje('Registro');
    const fecha = fechaHoyFichaje();
    const data = sheet.getDataRange().getValues();

    // Idempotente: si ya existe fila (abierta o cerrada) para hoy, no duplica.
    for (let i = 1; i < data.length; i++) {
      if (normalizarFecha(data[i][0]) === fecha && String(data[i][1]).trim().toUpperCase() === mat) {
        return {ok:true, ya_existia:true, entrada:normalizarHora(data[i][3]), comida:data[i][4], salida:normalizarHora(data[i][5]), tipoCierre:data[i][6]};
      }
    }

    const horaEntrada = horaActualFichaje();
    const horaComida = '14:00 - 15:00';
    const ahoraISO = new Date().toISOString();

    // appendRow() no siempre respeta el formato de texto de la columna (a diferencia de
    // setValue en celdas individuales) — se fuerza el formato de la fila explícitamente
    // para que Sheets no reconvierta la fecha/hora a un tipo Date/Time interno.
    const fila = sheet.getLastRow() + 1;
    const rango = sheet.getRange(fila, 1, 1, FICHAJE_COLS.length);
    rango.setNumberFormat('@');
    rango.setValues([[fecha, mat, nombre, horaEntrada, horaComida, '', '', ahoraISO, '', lat||'', lng||'', '', '']]);
    Logger.log('✓ Entrada registrada: ' + mat + ' ' + horaEntrada);

    return {ok:true, entrada:horaEntrada, comida:horaComida, salida:'', tipoCierre:''};
  } finally {
    lock.releaseLock();
  }
}

// ── POST: finalizar jornada (salida real, cierre manual) ──
function registrarSalida(mat, nombre, lat, lng) {
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = getHojaFichaje('Registro');
    const fecha = fechaHoyFichaje();
    const data = sheet.getDataRange().getValues();

    for (let i = 1; i < data.length; i++) {
      if (normalizarFecha(data[i][0]) === fecha && String(data[i][1]).trim().toUpperCase() === mat) {
        if (normalizarHora(data[i][5])) {
          // Ya estaba cerrada (manual o automática) — no se sobreescribe.
          return {ok:true, ya_cerrada:true, entrada:normalizarHora(data[i][3]), comida:data[i][4], salida:normalizarHora(data[i][5]), tipoCierre:data[i][6]};
        }
        const horaSalida = horaActualFichaje();
        const fila = i + 1; // 1-indexed en la hoja
        sheet.getRange(fila, 6).setValue(horaSalida);      // horaSalida
        sheet.getRange(fila, 7).setValue('manual');         // tipoCierre
        sheet.getRange(fila, 9).setValue(new Date().toISOString()); // timestampSalida
        if (lat) sheet.getRange(fila, 12).setValue(lat);    // latSalida
        if (lng) sheet.getRange(fila, 13).setValue(lng);    // lngSalida
        Logger.log('✓ Salida manual registrada: ' + mat + ' ' + horaSalida);
        return {ok:true, entrada:normalizarHora(data[i][3]), comida:data[i][4], salida:horaSalida, tipoCierre:'manual'};
      }
    }

    return {ok:false, error:'No hay fichaje de entrada hoy para ' + mat};
  } finally {
    lock.releaseLock();
  }
}

// Elimina filas duplicadas (misma fecha+matrícula). Conserva la fila cerrada si alguna
// de las duplicadas lo está; si ninguna lo está, conserva la primera. Ejecutar cuando
// se detecte un duplicado (p.ej. por doble clic antes de este fix).
function eliminarFichajesDuplicados() {
  const sheet = getHojaFichaje('Registro');
  const data = sheet.getDataRange().getValues();
  const vistos = {};
  const aBorrar = [];

  for (let i = 1; i < data.length; i++) {
    const fecha = normalizarFecha(data[i][0]);
    const mat = String(data[i][1]).trim().toUpperCase();
    if (!fecha || !mat) continue;
    const key = fecha + '|' + mat;
    const tieneSalida = !!normalizarHora(data[i][5]);

    if (!vistos[key]) {
      vistos[key] = {idx: i, tieneSalida: tieneSalida};
    } else if (!vistos[key].tieneSalida && tieneSalida) {
      aBorrar.push(vistos[key].idx);
      vistos[key] = {idx: i, tieneSalida: tieneSalida};
    } else {
      aBorrar.push(i);
    }
  }

  aBorrar.sort((a,b)=>b-a).forEach(idx => sheet.deleteRow(idx+1));
  Logger.log('✓ Filas duplicadas eliminadas: ' + aBorrar.length);
}

// ── Trigger 22:00: cierra automáticamente las jornadas sin finalizar ──
function cerrarJornadasPendientes() {
  const sheet = getHojaFichaje('Registro');
  const fecha = fechaHoyFichaje();
  const data = sheet.getDataRange().getValues();
  let cerradas = 0;

  for (let i = 1; i < data.length; i++) {
    const filaFecha = normalizarFecha(data[i][0]);
    const horaEntrada = normalizarHora(data[i][3]);
    const horaSalida = normalizarHora(data[i][5]);
    if (filaFecha === fecha && horaEntrada && !horaSalida) {
      const [h, m] = horaEntrada.split(':').map(Number);
      const totalMin = (h * 60 + m + 9 * 60) % (24 * 60); // +9h, con wrap por si fichó entrada muy tarde
      const horaSalidaCalc = Utilities.formatString('%02d:%02d', Math.floor(totalMin / 60), totalMin % 60);

      const fila = i + 1;
      sheet.getRange(fila, 6).setValue(horaSalidaCalc);
      sheet.getRange(fila, 7).setValue('automatico');
      sheet.getRange(fila, 9).setValue(new Date().toISOString());
      cerradas++;
    }
  }
  Logger.log('✓ Jornadas cerradas automáticamente: ' + cerradas);
}

// ── Trigger 22:00: técnicos activos sin ningún fichaje hoy ──
function generarFaltantesDiario() {
  const fecha = fechaHoyFichaje();
  const registro = getHojaFichaje('Registro');
  const faltantes = getHojaFichaje('Faltantes');

  const dataRegistro = registro.getDataRange().getValues();
  const ficharon = new Set();
  dataRegistro.slice(1).forEach(row => {
    if (normalizarFecha(row[0]) === fecha) ficharon.add(String(row[1]).trim().toUpperCase());
  });

  const nombrePorMatricula = obtenerNombresTecnicos();
  let faltaron = 0;

  Object.keys(nombrePorMatricula).forEach(mat => {
    if (!ficharon.has(mat)) {
      faltantes.appendRow([fecha, mat, nombrePorMatricula[mat]]);
      faltaron++;
    }
  });

  Logger.log('✓ Faltantes del ' + fecha + ': ' + faltaron);
}
