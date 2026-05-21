// ════════════════════════════════════════════════════════════════════════════
// GOOGLE APPS SCRIPT - AURUM BC SECURITY
// Endpoints para index.html via ?type=csv|auth|docs|flota|vacaciones|medalia|medalia-coord
// ════════════════════════════════════════════════════════════════════════════

// ─── CONFIG ───
const SHEET_CSV_ID = '1bMB6CXqhg2H77RVaW2k_A4KPEfNnPxHaJN5Oi-aHKJU'; // Main sheet con técnicos
const SHEET_DOCS_ID = '1K9pKvVjwFqGVNq6lOLEkQ4JCGxXe49eF_GbT0FuIDIk'; // Docs pending
const SHEET_FLOTA_ID = '1Q3CkL5m8nP9rSt2uVwXyZaBcDeFgHiJkLmNoPqRsT'; // Flota
const SHEET_VACACIONES_URL = 'https://docs.google.com/spreadsheets/d/1vWxYzAbCdEfGhIjKlMnOpQrStUvWxYzA/export?format=csv&gid=0';
const SHEET_MEDALIA_ID = '1aAbBcCdDeEfFgGhHiIjJkKkLlMmNnOoPpQqRrSsT'; // Medalia
const CUADRANTE_SHEET = 'CUADRANTE'; // Sheet name para auth

// ─── MAIN HANDLER ───
function doGet(e) {
  const type = e.parameter.type || 'csv';
  const cache = CacheService.getScriptCache();
  const cacheKey = `sheet_${type}`;

  try {
    switch(type) {
      case 'auth':
        return servirAuth();
      case 'csv':
        return servirCSV();
      case 'docs':
        return servirDocs();
      case 'flota':
        return servirFlota();
      case 'vacaciones':
        return servirVacaciones();
      case 'medalia':
        return servirMedalia();
      case 'medalia-coord':
        return servirMedialiaCoordinadores();
      default:
        return ContentService.createTextOutput('Unknown type').setMimeType(ContentService.MimeType.TEXT);
    }
  } catch(err) {
    return ContentService.createTextOutput('Error: ' + err.toString()).setMimeType(ContentService.MimeType.TEXT);
  }
}

// ─── AUTH: Matrícula → DNI mapping ───
function servirAuth() {
  const sheet = SpreadsheetApp.openById(SHEET_CSV_ID).getSheetByName(CUADRANTE_SHEET);
  if (!sheet) return ContentService.createTextOutput('{}').setMimeType(ContentService.MimeType.JSON);

  const data = sheet.getDataRange().getValues();
  const auth = {};

  // Suponiendo: Columna E = Matrícula, Columna I = DNI (ajusta si es diferente)
  for (let i = 1; i < data.length; i++) {
    const mat = String(data[i][4]).trim().toUpperCase(); // Columna E (índice 4)
    const dni = String(data[i][8]).trim(); // Columna I (índice 8)
    if (mat && dni) auth[mat] = dni;
  }

  return ContentService.createTextOutput(JSON.stringify(auth)).setMimeType(ContentService.MimeType.JSON);
}

// ─── CSV: Main technician data ───
function servirCSV() {
  const sheet = SpreadsheetApp.openById(SHEET_CSV_ID).getSheets()[0];
  const range = sheet.getDataRange();
  const values = range.getValues();

  let csv = '';
  for (let i = 0; i < values.length; i++) {
    const row = values[i].map(v => {
      const str = String(v || '');
      if (str.includes(',') || str.includes('"') || str.includes('\n')) {
        return '"' + str.replace(/"/g, '""') + '"';
      }
      return str;
    }).join(',');
    csv += row + '\n';
  }

  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

// ─── DOCS: Pending documentation ───
function servirDocs() {
  const cache = CacheService.getScriptCache();
  const cacheKey = 'docs_data';
  let cached = cache.get(cacheKey);
  if (cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.JSON);

  const sheet = SpreadsheetApp.openById(SHEET_DOCS_ID).getSheets()[0];
  const data = sheet.getDataRange().getValues();

  const docs = [];
  for (let i = 1; i < data.length; i++) {
    const mat = String(data[i][0] || '').trim();
    if (mat) {
      docs.push({
        mat: mat,
        nMant: String(data[i][1] || '').trim(),
        fecha: String(data[i][2] || '').trim(),
        tipo: String(data[i][3] || '').trim(),
        origen: String(data[i][4] || '').trim()
      });
    }
  }

  const json = JSON.stringify(docs);
  cache.put(cacheKey, json, 3600); // 1 hour
  return ContentService.createTextOutput(json).setMimeType(ContentService.MimeType.JSON);
}

// ─── FLOTA: Vehicle assignments ───
function servirFlota() {
  const cache = CacheService.getScriptCache();
  const cacheKey = 'flota_data';
  let cached = cache.get(cacheKey);
  if (cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);

  const sheet = SpreadsheetApp.openById(SHEET_FLOTA_ID).getSheets()[0];
  const data = sheet.getDataRange().getValues();

  let csv = 'mat,coche\n';
  for (let i = 1; i < data.length; i++) {
    const mat = String(data[i][0] || '').trim();
    const coche = String(data[i][1] || '').trim();
    const estado = String(data[i][2] || '').trim().toUpperCase();

    // Excluir DEVUELTO, TALLER, PERSONAL
    if (mat && coche && !['DEVUELTO', 'TALLER', 'PERSONAL'].includes(estado)) {
      csv += `${mat},${coche}\n`;
    }
  }

  cache.put(cacheKey, csv, 3600); // 1 hour
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

// ─── VACACIONES: Vacation tracking ───
function servirVacaciones() {
  const cache = CacheService.getScriptCache();
  const cacheKey = 'vacaciones_data';
  let cached = cache.get(cacheKey);
  if (cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.JSON);

  try {
    // Fetch from published sheet
    const response = UrlFetchApp.fetch(SHEET_VACACIONES_URL, {muteHttpExceptions: true});
    const csvText = response.getContentText();

    // Parse and reformat as JSON object
    const lines = csvText.split('\n');
    const vacaciones = {};

    for (let i = 1; i < lines.length; i++) {
      if (!lines[i].trim()) continue;
      const cells = parseCSVLine(lines[i]);
      if (cells.length >= 3) {
        const mat = cells[0].trim().toUpperCase();
        if (mat) {
          vacaciones[mat] = {
            consumido: cells[1].trim(),
            disponible: cells[2].trim()
          };
        }
      }
    }

    const json = JSON.stringify(vacaciones);
    cache.put(cacheKey, json, 3600);
    return ContentService.createTextOutput(json).setMimeType(ContentService.MimeType.JSON);
  } catch(err) {
    return ContentService.createTextOutput('{}').setMimeType(ContentService.MimeType.JSON);
  }
}

// ─── MEDALIA: Satisfaction metrics ───
function servirMedalia() {
  const cache = CacheService.getScriptCache();
  const cacheKey = 'medalia_data';
  let cached = cache.get(cacheKey);
  if (cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);

  const sheet = SpreadsheetApp.openById(SHEET_MEDALIA_ID).getSheets()[0];
  const data = sheet.getDataRange().getValues();

  let csv = 'mat,promedio\n';
  for (let i = 1; i < data.length; i++) {
    const mat = String(data[i][0] || '').trim();
    const promedio = String(data[i][1] || '').trim();
    if (mat) csv += `${mat},${promedio}\n`;
  }

  cache.put(cacheKey, csv, 3600);
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

// ─── MEDALIA COORDINADORES: Regional averages ───
function servirMedialiaCoordinadores() {
  const cache = CacheService.getScriptCache();
  const cacheKey = 'medalia_coord_data';
  let cached = cache.get(cacheKey);
  if (cached) return ContentService.createTextOutput(cached).setMimeType(ContentService.MimeType.TEXT);

  const sheet = SpreadsheetApp.openById(SHEET_MEDALIA_ID).getSheets()[1] || SpreadsheetApp.openById(SHEET_MEDALIA_ID).getSheets()[0];
  const data = sheet.getDataRange().getValues();

  let csv = 'territorio,promedio\n';
  for (let i = 1; i < data.length; i++) {
    const territorio = String(data[i][0] || '').trim();
    const promedio = String(data[i][1] || '').trim();
    if (territorio) csv += `${territorio},${promedio}\n`;
  }

  cache.put(cacheKey, csv, 3600);
  return ContentService.createTextOutput(csv).setMimeType(ContentService.MimeType.TEXT);
}

// ─── HELPERS ───
function parseCSVLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    const nextChar = line[i + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      result.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  result.push(current);
  return result;
}

// ─── CACHE MANAGEMENT ───
function onEdit(e) {
  const cache = CacheService.getScriptCache();
  cache.removeAll(['docs_data', 'flota_data', 'vacaciones_data', 'medalia_data', 'medalia_coord_data']);
}

// ─── EMAIL PROCESSING (Optional) ───
function procesarCorreosAurum() {
  // Placeholder para procesamiento de correos si es necesario
  // Implementar según necesidades
}
