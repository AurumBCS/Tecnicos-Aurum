// ════════════════════════════════════════════════════════
//  IDs de Google Sheets
// ════════════════════════════════════════════════════════
const SHEET_RM_ID          = '1mdwknpTrcTmDGMnTB-NZQEh0eI5VClo0fsBmk1BLzNM';
const SHEET_CUMPLIMIENTO_ID = '1UL3XSri6UVsWRfoU94pV1l9falmDmztMKupeE8U2WIw';
const SHEET_CSV_ID          = '1UWfgzyAlu6sK6VLKP0Qoqhs31UfRju1J-zqaR8yuUng';
const SHEET_DOCS_ID         = '1clqnU3UH0ld86UoL4uvwp_ciAcMwRxeAjqDkbH4QZLc';
const SHEET_CUADRANTE_ID    = '1HqOI_kN10tAnBmeTrPqAklEa4f-1-DWQ';
const SHEET_FLOTA_ID        = '1c990k4SDrPULhP0VQ8xbZunBg7Qo9nhHl2tTDYPxh2s';
const SHEET_MEDALIA_ID      = '1_EVdRTQPwpMjg9PiJzsbq2_-OgDqBwmZof-cCO1iwoA';
const SHEET_VACACIONES_ID   = '2PACX-1vR9A0fhBk2ViKKewyKP8rJz364_MsEwi8CD_DEIjokUAeZiJzieR1k3KuZm6Kx9B68YrNTtalq8peFn';
const REMITENTE             = 'gustavoa.perez@verisure.es';

function doGet(e) {
  const type = e && e.parameter && e.parameter.type ? e.parameter.type : 'csv';
  try {
    if (type === 'docs') return servirDocs();
    if (type === 'auth') return servirAuth();
    if (type === 'flota') return servirFlota();
    if (type === 'medalia') return servirMedalia();
    if (type === 'vacaciones') return servirVacaciones();
    if (type === 'medalia-coord') return servirMedialiaCoordinadores();
    return servirCSV();
  } catch(err) {
    return ContentService.createTextOutput('Error: ' + err.message)
      .setMimeType(ContentService.MimeType.TEXT);
  }
}

// ════════════════════════════════════════════════════════
//  SERVIR CSV (datos principales)
// ════════════════════════════════════════════════════════
function servirCSV() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('csv_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);

  const ss = SpreadsheetApp.openById(SHEET_CSV_ID);
  const sheet = ss.getSheets()[0];
  const data = sheet.getDataRange().getValues();
  const display = sheet.getDataRange().getDisplayValues();

  const csv = display.map(row =>
    row.map(cell => {
      const s = String(cell === null || cell === undefined ? '' : cell);
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? '"' + s.replace(/"/g, '""') + '"' : s;
    }).join(',')
  ).join('\n');

  cache.put('csv_data', csv, 3600);
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

// ════════════════════════════════════════════════════════
//  SERVIR DOCS (JSON)
// ════════════════════════════════════════════════════════
function servirDocs() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('docs_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.JSON);

  try {
    const ss = SpreadsheetApp.openById(SHEET_DOCS_ID);
    const sheet = ss.getSheets()[0];
    const data = sheet.getDataRange().getDisplayValues();

    const result = [];
    data.slice(1).forEach(row => {
      const nMant  = String(row[1]||'').trim();
      const fecha  = String(row[2]||'').trim();
      const mat    = String(row[3]||'').trim();
      const tipo   = String(row[4]||'').trim();
      const origen = String(row[6]||'').trim();

      if(mat && nMant) {
        result.push({mat, nMant, fecha, tipo, origen});
      }
    });

    const json = JSON.stringify(result);
    cache.put('docs_data', json, 21600);
    Logger.log('✓ Docs: ' + result.length + ' pendientes');
    return ContentService.createTextOutput(json).setMimeType(ContentService.MimeType.JSON);

  } catch(e) {
    Logger.log('✗ Error docs: ' + e.toString());
    return ContentService.createTextOutput('[]').setMimeType(ContentService.MimeType.JSON);
  }
}

// ════════════════════════════════════════════════════════
//  SERVIR AUTH (JSON)
// ════════════════════════════════════════════════════════
function servirAuth() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('auth_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.JSON);

  try {
    const ss = SpreadsheetApp.openById('1HqOI_kN10tAnBmeTrPqAklEa4f-1-DWQ');
    const sheet = ss.getSheetByName('CUADRANTE');
    const data = sheet.getDataRange().getValues();

    const auth = {};
    data.slice(1).forEach(row => {
      const matricula = String(row[4]||'').trim().toUpperCase();
      const dni = String(row[8]||'').trim().toUpperCase();
      if(matricula && dni) {
        auth[matricula] = dni;
      }
    });

    const json = JSON.stringify(auth);
    cache.put('auth_data', json, 21600);
    Logger.log('✓ AUTH: ' + Object.keys(auth).length + ' matrículas cargadas');
    return ContentService.createTextOutput(json).setMimeType(ContentService.MimeType.JSON);

  } catch(e) {
    Logger.log('✗ Error AUTH: ' + e.message);
    return ContentService.createTextOutput('{}').setMimeType(ContentService.MimeType.JSON);
  }
}

// ════════════════════════════════════════════════════════
//  SERVIR FLOTA (CSV)
// ════════════════════════════════════════════════════════
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
    if(mat && coche && mat!=='TCO' && !mat.includes('DEVUELTO') && !mat.includes('TALLER') && !mat.includes('PERSONAL')){
      rows.push([mat, coche]);
    }
  });

  const csv = rows.map(r => r.map(c => '"' + String(c||'').replace(/"/g, '""') + '"').join(',')).join('\n');
  cache.put('flota_data', csv, 21600);
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

// ════════════════════════════════════════════════════════
//  SERVIR MEDALIA (CSV)
// ════════════════════════════════════════════════════════
function servirMedalia() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('medalia_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);

  const ss = SpreadsheetApp.openById(SHEET_MEDALIA_ID);
  const sheet = ss.getSheets()[0];
  const data = sheet.getDataRange().getDisplayValues();

  const nombrePorMatricula = obtenerNombresTecnicos();

  const rows = [['matricula', 'nombre', 'tipoCFL', 'territorial', 'zona', 'nota', 'comentario']];
  data.slice(1).forEach(row => {
    const tipoCFL = String(row[0]||'').trim();
    const matricula = String(row[4]||'').trim();
    const territorial = String(row[5]||'').trim();
    const nota = row[16];
    const comentario = String(row[17]||'').trim();

    if(matricula && nota) {
      const nombre = nombrePorMatricula[matricula] || 'Desconocido';
      const zona = mapearTerritorioAZona(territorial);
      rows.push([matricula, nombre, tipoCFL, territorial, zona, nota, comentario]);
    }
  });

  const csv = rows.map(r => r.map(c => '"' + String(c||'').replace(/"/g, '""') + '"').join(',')).join('\n');
  cache.put('medalia_data', csv, 21600);
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

// ════════════════════════════════════════════════════════
//  SERVIR VACACIONES (JSON)
// ════════════════════════════════════════════════════════
function servirVacaciones() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('vacaciones_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.JSON);

  try {
    const url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vR9A0fhBk2ViKKewyKP8rJz364_MsEwi8CD_DEIjokUAeZiJzieR1k3KuZm6Kx9B68YrNTtalq8peFn/pub?output=csv';
    const csv = UrlFetchApp.fetch(url).getContentText('UTF-8');
    const lines = csv.trim().split('\n');

    if(lines.length < 3) return ContentService.createTextOutput('{}').setMimeType(ContentService.MimeType.JSON);

    const headers = lines[1].split(',').map(h => h.trim());
    const matriculaIdx = 1;
    const consumidosIdx = headers.findIndex(h => h === 'Consumidos');
    const disponiblesIdx = headers.findIndex(h => h === 'Disponibles');

    Logger.log('Índices: mat=' + matriculaIdx + ', consumidos=' + consumidosIdx + ', disponibles=' + disponiblesIdx);

    const result = {};

    for(let i = 2; i < lines.length; i++){
      const cells = lines[i].split(',').map(c => c.trim());
      const mat = (cells[matriculaIdx] || '').toUpperCase();

      if(!mat) continue;

      const consumido = parseInt(cells[consumidosIdx]) || 0;
      const disponible = parseInt(cells[disponiblesIdx]) || 0;

      result[mat] = { consumido, disponible };
    }

    const json = JSON.stringify(result);
    cache.put('vacaciones_data', json, 3600);
    Logger.log('✓ Vacaciones: ' + Object.keys(result).length + ' técnicos');
    return ContentService.createTextOutput(json).setMimeType(ContentService.MimeType.JSON);

  } catch(e) {
    Logger.log('✗ Error: ' + e.toString());
    return ContentService.createTextOutput('{}').setMimeType(ContentService.MimeType.JSON);
  }
}

// ════════════════════════════════════════════════════════
//  OBTENER NOMBRES DE TÉCNICOS
// ════════════════════════════════════════════════════════
function obtenerNombresTecnicos() {
  const ss = SpreadsheetApp.openById(SHEET_CUADRANTE_ID);
  const sheet = ss.getSheets()[0];
  const data = sheet.getDataRange().getValues();

  const nombres = {};
  data.slice(1).forEach(row => {
    const mat = String(row[4]||'').trim();
    const nombre = String(row[0]||'').trim();
    if(mat && nombre) nombres[mat] = nombre;
  });

  return nombres;
}

// ════════════════════════════════════════════════════════
//  MAPEAR TERRITORIAL A ZONA
// ════════════════════════════════════════════════════════
function mapearTerritorioAZona(territorial) {
  if(territorial.includes('3304') || territorial.includes('3305')) return 'Zona 4-5';
  if(territorial.includes('3306') || territorial.includes('3307')) return 'Zona 6-7';
  return 'Otra';
}

// ════════════════════════════════════════════════════════
//  PROCESADOR DE CORREOS
// ════════════════════════════════════════════════════════
function procesarCorreosAurum() {
  const query = `from:${REMITENTE} is:unread has:attachment`;
  const threads = GmailApp.search(query);
  if (threads.length === 0) { Logger.log('Sin correos nuevos.'); return; }
  threads.forEach(thread => {
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

        if (esRM)           actualizarSheet(SHEET_RM_ID, attachment, 'RM');
        else if (esCumplimiento) actualizarSheet(SHEET_CUMPLIMIENTO_ID, attachment, 'Cumplimiento');
        else if (esMedalia) actualizarSheet(SHEET_MEDALIA_ID, attachment, 'Medalia');
        else if (esCSV)     actualizarSheet(SHEET_CSV_ID, attachment, 'CSV');
      });
      message.markRead();
    });
  });
}

// ════════════════════════════════════════════════════════
//  FUNCIÓN PARA ACTUALIZAR SHEETS
// ════════════════════════════════════════════════════════
function actualizarSheet(sheetId, attachment, tipo) {
  try {
    const ss = SpreadsheetApp.openById(sheetId);
    const sheet = ss.getSheets()[0];
    let datos = [];

    const nombre = attachment.getName().toLowerCase();

    if (nombre.endsWith('.csv')) {
      Logger.log(`Procesando CSV para ${tipo}...`);
      datos = Utilities.parseCsv(attachment.getDataAsString('UTF-8'));
    } else if (nombre.endsWith('.xlsx') || nombre.endsWith('.xls')) {
      Logger.log(`Procesando Excel para ${tipo}...`);

      const blob = attachment.copyBlob();
      const tempFile = DriveApp.createFile(blob);
      const tempFileId = tempFile.getId();

      try {
        Utilities.sleep(1000);

        const accessToken = ScriptApp.getOAuthToken();
        const exportUrl = `https://docs.google.com/spreadsheets/d/${tempFileId}/export?format=csv`;

        const fetchOptions = {
          method: 'get',
          headers: { Authorization: 'Bearer ' + accessToken },
          muteHttpExceptions: true
        };

        const response = UrlFetchApp.fetch(exportUrl, fetchOptions);
        const csvContent = response.getContentText('UTF-8');

        if (csvContent && csvContent.length > 0) {
          Logger.log(`✓ Exportado a CSV`);
          datos = Utilities.parseCsv(csvContent);
        } else {
          Logger.log(`⚠ Respuesta vacía`);
          return;
        }

      } catch(e) {
        Logger.log(`✗ Error exportando Excel: ${e.message}`);
        return;
      } finally {
        try { tempFile.setTrashed(true); } catch(e) {}
      }
    }

    if (!datos || !datos.length) {
      Logger.log(`⚠ Sin datos en ${tipo}`);
      return;
    }

    sheet.clearContents();
    sheet.getRange(1, 1, datos.length, datos[0].length).setValues(datos);
    Logger.log(`✓ ${tipo} actualizado: ${datos.length} filas, ${datos[0].length} columnas`);

  } catch(e) {
    Logger.log(`✗ Error ${tipo}: ${e.message}`);
  }
}

function limpiarCache() {
  CacheService.getScriptCache().removeAll(['csv_data','docs_data','auth_data','flota_data','medalia_data','vacaciones_data']);
  Logger.log('Caché limpiado');
}

function onEdit(e) {
  CacheService.getScriptCache().removeAll(['csv_data','docs_data','auth_data','flota_data','medalia_data','vacaciones_data']);
}

function configurarTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('procesarCorreosAurum').timeBased().everyHours(1).create();
  Logger.log('✓ Trigger configurado');
}

// ════════════════════════════════════════════════════════
//  SERVIR MEDALIA PROMEDIOS POR TERRITORIO (PARA COORDINADORES)
// ════════════════════════════════════════════════════════
function servirMedialiaCoordinadores() {
  const cache = CacheService.getScriptCache();
  const cached = cache.get('medalia_coordinadores_data');
  if(cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.JSON);

  try {
    const url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTIbmLaEbAJoZj7d_lJqtIV-gbx2kTiumryL-Q7fpvkxvCs3PBaMiDCHTYpWHU-SQ1loy9eAT0G1X9n/pub?output=csv';
    const csv = UrlFetchApp.fetch(url).getContentText('UTF-8');
    const lines = csv.trim().split('\n');

    if(lines.length < 2) return ContentService.createTextOutput('{}').setMimeType(ContentService.MimeType.JSON);

    const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
    const tipoIdx = headers.findIndex(h => h.includes('tipo'));
    const territorialIdx = headers.findIndex(h => h.includes('territorial'));
    const satisfaccionIdx = headers.findIndex(h => h.includes('satisfacción') || h.includes('satisfaccion'));

    Logger.log('Headers: tipo=' + tipoIdx + ', territorial=' + territorialIdx + ', satisfaccion=' + satisfaccionIdx);

    const grupos = {
      '3304-3305': { notas: [], count: 0, sum: 0 },
      '3306-3307': { notas: [], count: 0, sum: 0 }
    };

    for(let i = 1; i < lines.length; i++){
      const cells = lines[i].split(',').map(c => c.trim());
      const tipo = (cells[tipoIdx] || '').toLowerCase();
      const territorial = (cells[territorialIdx] || '').trim();
      const satisfaccion = parseInt(cells[satisfaccionIdx]) || 0;

      if(!tipo.includes('interacción') && !tipo.includes('interaccion')) continue;

      let grupo = null;
      if(territorial.includes('3304') || territorial.includes('3305')) {
        grupo = '3304-3305';
      } else if(territorial.includes('3306') || territorial.includes('3307')) {
        grupo = '3306-3307';
      }

      if(grupo && satisfaccion > 0) {
        grupos[grupo].notas.push(satisfaccion);
        grupos[grupo].sum += satisfaccion;
        grupos[grupo].count++;
      }
    }

    const result = {};
    Object.keys(grupos).forEach(g => {
      if(grupos[g].count > 0) {
        result[g] = {
          promedio: (grupos[g].sum / grupos[g].count).toFixed(2),
          cantidad: grupos[g].count,
          territorio: g
        };
      }
    });

    const json = JSON.stringify(result);
    cache.put('medalia_coordinadores_data', json, 3600);
    Logger.log('✓ Medalia coordinadores: ' + Object.keys(result).length + ' grupos');
    return ContentService.createTextOutput(json).setMimeType(ContentService.MimeType.JSON);

  } catch(e) {
    Logger.log('✗ Error medalia: ' + e.toString());
    return ContentService.createTextOutput('{}').setMimeType(ContentService.MimeType.JSON);
  }
}
