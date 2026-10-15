const express = require('express');
const { Client, LocalAuth } = require('whatsapp-web.js');
let _puppeteerExec;
try { _puppeteerExec = require('puppeteer').executablePath(); } catch(e) {}
const XLSX = require('xlsx');
const multer = require('multer');
const { WebSocketServer } = require('ws');
const http = require('http');
const https = require('https');
const qrcode = require('qrcode');
const fs = require('fs');
const path = require('path');

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

app.use(express.static('public'));
app.use(express.json());

// ── Jerarquía JE → Técnicos (cargada dinámicamente desde Google Sheets) ──────
let JERARQUIA = {};
let JE_NAMES  = { 'JR9426': 'Coordinador Regional' };
let TEC_NAMES = {}; // matrícula de técnico → nombre (del cuadrante)

// Matrículas autorizadas para hacer la carga CENTRAL del Excel (todos los técnicos, sin filtrar).
// Si la matrícula escrita en el campo normal de carga coincide con una de estas,
// se sube todo sin filtrar. Cualquier otra matrícula sigue el comportamiento normal
// (JE ve su equipo, técnico ve solo lo suyo).
const UPLOADERS_PERMITIDOS = ['262876', 'CM9651', 'GD5381', 'EQ5303', '273379'];

function fetchCSV(url, redirects = 0) {
  return new Promise((resolve, reject) => {
    if (redirects > 5) return reject(new Error('Demasiadas redirecciones'));
    const mod = url.startsWith('https') ? https : http;
    mod.get(url, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        resolve(fetchCSV(res.headers.location, redirects + 1));
        return;
      }
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

// Parte una línea CSV respetando comillas ("a","b, c",d)
function parseLineaCSV(line) {
  const out = []; let cur = ''; let q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') { if (q && line[i + 1] === '"') { cur += '"'; i++; } else q = !q; }
    else if (ch === ',' && !q) { out.push(cur.trim()); cur = ''; }
    else cur += ch;
  }
  out.push(cur.trim());
  return out;
}

// La jerarquía se pide al mismo Apps Script que usa el portal (?type=jerarquia),
// que lee el Cuadrante ACTUAL directamente. Antes se leía un CSV "publicado en la
// web" de una copia vieja del cuadrante, desactualizada (JEs con técnicos que ya
// no son suyos). Columnas: JE, Matricula, Zona, CuentaJE, CuentaEmpresa, Nombre, ...
async function cargarJerarquia() {
  try {
    const raw = await fetchCSV(JERARQUIA_URL);
    const lines = raw.trim().split('\n');
    const hdr = parseLineaCSV(lines[0] || '').map(h => h.toLowerCase());
    const iJE = hdr.indexOf('je'), iMat = hdr.indexOf('matricula'), iNombre = hdr.indexOf('nombre');
    if (iJE < 0 || iMat < 0) throw new Error('Respuesta inesperada: ' + (lines[0] || '').slice(0, 80));
    const jer = {};
    const nombres = {};
    lines.slice(1).forEach(line => {
      const cols = parseLineaCSV(line);
      const je  = String(cols[iJE]  || '').toUpperCase();
      const mat = String(cols[iMat] || '').toUpperCase();
      if (!je || !mat) return;
      if (iNombre >= 0 && cols[iNombre]) nombres[mat] = cols[iNombre];
      // El JE cuenta dentro de su propio equipo (también ve y confirma sus propias citas)
      if (!jer[je]) jer[je] = [je];
      if (!jer[je].includes(mat)) jer[je].push(mat);
    });
    if (!Object.keys(jer).length) throw new Error('Jerarquía vacía');
    JERARQUIA = jer;
    JE_NAMES  = { ...nombres, 'JR9426': 'Coordinador Regional' };
    TEC_NAMES = nombres;
    const total = Object.values(jer).reduce((s, v) => s + v.length, 0);
    console.log(`  Jerarquía cargada: ${Object.keys(jer).length} JEs · ${total} técnicos`);
  } catch(e) {
    console.error('  [Jerarquía] Error al cargar:', e.message, '— usando datos anteriores');
  }
}

// ── Cuadrante de autenticación (matrícula → DNI) — el mismo que usa el portal ─
// El Apps Script exige un token compartido en cada petición (ver APP_TOKEN
// en google-apps-script-final.gs e Index.html) — sin él devuelve "no autorizado".
const APP_TOKEN = '74ffa953c19c831f33d06b8b0d5e38ab1ee707ed881c3426';
const AUTH_URL = 'https://script.google.com/macros/s/AKfycbxotyAfeX08YR-Sx4QuYCt41SOwmfVX5ltxq4n0L2-XVJoahUkdlo4_EY8-SCDfVgR7/exec?type=auth&token=' + APP_TOKEN;
const JERARQUIA_URL = AUTH_URL.replace('type=auth', 'type=jerarquia');
let AUTH_DATA = {};

async function cargarAuth() {
  try {
    const raw = await fetchCSV(AUTH_URL);
    const lines = raw.trim().split('\n').slice(1); // saltar cabecera "Matricula","DNI"
    const data = {};
    lines.forEach(line => {
      const m = line.match(/^"([^"]*)","([^"]*)"/);
      if (!m) return;
      const matricula = m[1].trim().toUpperCase();
      const dni       = m[2].trim().toUpperCase();
      if (matricula && dni) data[matricula] = dni;
    });
    AUTH_DATA = data;
    console.log(`  Cuadrante de autenticación cargado: ${Object.keys(data).length} matrículas`);
  } catch(e) {
    console.error('  [Auth] Error al cargar:', e.message, '— usando datos anteriores');
  }
}

function verificarDNI(matricula, dni) {
  const mat = String(matricula || '').trim().toUpperCase();
  const d   = String(dni || '').trim().toUpperCase();
  if (!mat || !d) return false;
  return AUTH_DATA[mat] === d;
}

// Calcula la fecha de mañana en el mismo formato dd/mm/aa que usan las citas
function fechaManana() {
  const hoy = new Date();
  hoy.setDate(hoy.getDate() + 1);
  const dd = String(hoy.getDate()).padStart(2, '0');
  const mm = String(hoy.getMonth() + 1).padStart(2, '0');
  const yy = String(hoy.getFullYear()).slice(-2);
  return `${dd}/${mm}/${yy}`;
}

// ── Persistencia de sesión ────────────────────────────────────────────────────
// El archivo local (sesion.json) sirve de cache rapida dentro de una misma
// instancia, pero NO sobrevive a un despliegue nuevo en Render (contenedor
// desde cero). Por eso las citas TAMBIEN se guardan en una Hoja de Google
// (fuente de verdad durable) via el Apps Script de CITAS_SHEET_URL.
const SESSION_FILE = path.join(__dirname, 'sesion.json');
const CITAS_SHEET_URL = 'https://script.google.com/macros/s/AKfycby06tIG3D_JuqhEt6Bqp283Xgbmg151AuzR4Uj2oIOVWN4XFmhDLR6UYLZtWqrIE8e9/exec';

function postAppsScript(url, bodyObj) {
  return new Promise((resolve, reject) => {
    const data   = JSON.stringify(bodyObj);
    const parsed = new URL(url);
    const opciones = {
      hostname: parsed.hostname,
      path: parsed.pathname + parsed.search,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) }
    };
    const req = https.request(opciones, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => resolve(body));
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function guardarCitasEnSheet() {
  try {
    await postAppsScript(CITAS_SHEET_URL, { action: 'guardarTodo', citas: appointments });
  } catch (e) {
    console.error('[Sheet] Error al guardar citas:', e.message);
  }
}

async function cargarCitasDesdeSheet() {
  try {
    const raw  = await fetchCSV(CITAS_SHEET_URL + '?action=cargar');
    const data = JSON.parse(raw);
    if (data.ok && data.citas.length > 0) {
      appointments = data.citas.map(normalizarCita);
      console.log(`  Citas restauradas desde Google Sheets: ${appointments.length}`);
    }
  } catch (e) {
    console.error('[Sheet] Error al cargar citas:', e.message, '— se intenta respaldo local');
  }
}

function guardarSesion() {
  try {
    fs.writeFileSync(SESSION_FILE, JSON.stringify({ appointments, currentJE, dailyStats }, null, 2));
  } catch (e) {
    console.error('[Sesión] Error al guardar:', e.message);
  }
  guardarCitasEnSheet(); // fire-and-forget, no bloquea al que llamo guardarSesion()
}

function cargarSesion() {
  try {
    if (!fs.existsSync(SESSION_FILE)) return;
    const data = JSON.parse(fs.readFileSync(SESSION_FILE, 'utf8'));
    if (data.appointments?.length > 0) {
      appointments = data.appointments.map(normalizarCita);
      currentJE    = data.currentJE || null;
      console.log(`  Sesión restaurada: ${appointments.length} citas cargadas.`);
    }
    // Restaurar contador diario solo si es del mismo día (si no, empieza en 0)
    if (data.dailyStats && data.dailyStats.date === hoyStr()) {
      dailyStats = data.dailyStats;
      console.log(`  Mensajes enviados hoy: ${dailyStats.count}/${DAILY_LIMIT}`);
    }
  } catch (e) {
    console.error('[Sesión] Error al cargar:', e.message);
  }
}

async function iniciarPersistencia() {
  await cargarCitasDesdeSheet();
  if (appointments.length === 0) {
    cargarSesion(); // respaldo local si el Sheet no tenia nada o fallo la carga
  }
  // Si alguna cita se completo al cargar (matricula sacada de "Técnico"),
  // guardar ya la version corregida en la hoja.
  if (appointments.some(a => a.matricula)) guardarSesion();
}

let appointments  = [];
let waStatus      = 'initializing';
let sendingActive = false;
let lastQR        = null;
let currentJE     = null;

// WhatsApp queda DESACTIVADO por defecto — arranca un Chrome completo (~300-400 MB),
// demasiado para un plan gratuito en la nube. Las páginas de SMS (tecnico.html, je.html)
// no lo necesitan. Para activarlo, define la variable de entorno WHATSAPP_ENABLED=true.
const WHATSAPP_ENABLED = process.env.WHATSAPP_ENABLED === 'true';

// ── Broadcast WebSocket ───────────────────────────────────────────────────────
function broadcast(data) {
  wss.clients.forEach(ws => {
    if (ws.readyState === 1) ws.send(JSON.stringify(data));
  });
}

// ── Buscar Chrome instalado en el sistema ────────────────────────────────────
function findChrome() {
  if (process.env.PUPPETEER_EXECUTABLE_PATH && fs.existsSync(process.env.PUPPETEER_EXECUTABLE_PATH))
    return process.env.PUPPETEER_EXECUTABLE_PATH;
  if (_puppeteerExec && fs.existsSync(_puppeteerExec)) return _puppeteerExec;
  const macPaths = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ];
  for (const p of macPaths) { if (fs.existsSync(p)) return p; }
  const winPaths = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  ];
  for (const p of winPaths) { if (fs.existsSync(p)) return p; }
  return null;
}

// ── WhatsApp Client ───────────────────────────────────────────────────────────
// Se crea una instancia NUEVA cada vez que se reinicia (destroy + reinit no funciona
// en la misma instancia de whatsapp-web.js — produce "Execution context was destroyed")
let client = null;

function crearClienteWA() {
  const chromePath = findChrome();
  const isMac = process.platform === 'darwin';

  console.log('  Chrome:', chromePath || '⚠️  No encontrado — puede fallar');

  client = new Client({
    authStrategy: new LocalAuth({ clientId: 'confirmaciones-aurum' }),
    puppeteer: {
      headless: true,
      ...(chromePath ? { executablePath: chromePath } : {}),
      args: isMac
        ? ['--no-sandbox', '--disable-gpu', '--disable-software-rasterizer']
        : ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    }
  });

  client.on('auth_failure', msg => {
    console.error('  [WA] Error de autenticacion:', msg);
    waStatus = 'disconnected';
    broadcast({ type: 'wa_status', status: 'disconnected' });
  });

  client.on('loading_screen', (percent, message) => {
    console.log(`  [WA] Cargando: ${percent}% - ${message}`);
  });

  client.on('qr', async (qr) => {
    waStatus = 'qr';
    lastQR = await qrcode.toDataURL(qr);
    broadcast({ type: 'qr', qr: lastQR });
    broadcast({ type: 'wa_status', status: 'qr' });
  });

  client.on('authenticated', () => {
    broadcast({ type: 'wa_status', status: 'authenticated' });
  });

  client.on('ready', () => {
    waStatus = 'connected';
    const info = client.info;
    broadcast({ type: 'wa_status', status: 'connected', name: info?.pushname || '', number: info?.wid?.user || '' });
    console.log('  WhatsApp conectado como:', info?.pushname);
  });

  client.on('disconnected', (reason) => {
    waStatus = 'disconnected';
    broadcast({ type: 'wa_status', status: 'disconnected' });
    console.log('  WhatsApp desconectado:', reason);
    // Crear instancia nueva tras desconexión
    setTimeout(() => crearClienteWA(), 5000);
  });

  client.on('message', async (msg) => {
    if (msg.fromMe) return;
    if (msg.from.endsWith('@g.us')) return;

    let fromNumber = normalizePhone(msg.from.replace(/@.*/, ''));
    try {
      const chat = await msg.getChat();
      if (chat && chat.id && chat.id._serialized) {
        const chatNum = normalizePhone(chat.id._serialized.replace(/@.*/, ''));
        if (chatNum && chatNum.length >= 9) fromNumber = chatNum;
      }
    } catch(e) {}

    const text = msg.body.trim().toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '');

    const apt = appointments.find(a => {
      if (!(a.status === 'enviado' || a.status === 'pendiente')) return false;
      if (a.chatId && a.chatId === fromNumber) return true;
      const stored = normalizePhone(a.telefono);
      return stored === fromNumber
          || fromNumber.endsWith(stored)
          || stored.endsWith(fromNumber);
    });
    if (!apt) return;

    if (apt.sentAt && msg.timestamp && (msg.timestamp * 1000) < apt.sentAt) {
      console.log(`[MSG] Ignorado (anterior al envío): ${fromNumber} "${msg.body}"`);
      return;
    }

    const YES_PATTERNS = [
      /\bsi\b/, /\bsí\b/, /\byes\b/, /\bok\b/, /\bclaro\b/, /\bvale\b/,
      /\bconfirmo\b/, /\bconfirma\b/, /\bconfirmado\b/, /\bperfecto\b/,
      /\bde acuerdo\b/, /\bestaré\b/, /\bestare\b/, /\bpor supuesto\b/,
      /\bafirmativo\b/, /\bcorrecto\b/, /\bbueno\b/, /\bgenial\b/
    ];
    const NO_PATTERNS = [
      /\bno puedo\b/, /\bno podre\b/, /\bno podré\b/, /\bno estaré\b/, /\bno estare\b/,
      /\bimposible\b/, /\bcancelar\b/, /\bcancelad\b/, /\bno confirmo\b/
    ];

    const firstWord = text.split(/[\s,!?.]+/)[0];
    const hasYes = firstWord === 'si' || firstWord === 'yes' || firstWord === 'ok'
      || YES_PATTERNS.some(p => p.test(text));
    const hasNo  = firstWord === 'no'
      || NO_PATTERNS.some(p => p.test(text));

    if (hasNo && !hasYes) {
      apt.status = 'no_confirmado';
    } else if (hasYes) {
      apt.status = 'confirmado';
    } else {
      apt.status = 'otra_respuesta';
    }
    apt.respuesta = msg.body;
    apt.horaRespuesta = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

    broadcast({ type: 'update', appointments });
    guardarSesion();
    console.log(`  Respuesta de ${apt.cliente}: "${msg.body}" → ${apt.status}`);

    // Mensaje de seguimiento automático según respuesta
    if (apt.status === 'confirmado' || apt.status === 'no_confirmado') {
      try {
        const waNum = toWANumber(apt.telefono);
        if (waNum) {
          const followUp = apt.status === 'confirmado'
            ? `¡Muchas gracias por su confirmación! ✅\n\nNos vemos el *${apt.fecha}* en el tramo *${apt.timeslot}h*. Que tenga un buen día. 😊`
            : `Entendido, gracias por avisarnos.\n\nRecibirá una llamada de nuestra central durante el día de hoy para reagendar su visita en otro momento.\n\nDisculpe las molestias. 🙏`;
          await new Promise(r => setTimeout(r, 2000 + Math.random() * 2000));
          await client.sendMessage(waNum, followUp);
          console.log(`  Seguimiento enviado a ${apt.cliente} (${apt.status})`);
        }
      } catch(e) {
        console.error(`  Error enviando seguimiento a ${apt.cliente}:`, e.message);
      }
    }
  });

  client.initialize();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function normalizePhone(phone) {
  return String(phone || '').replace(/\D/g, '').replace(/^34/, '');
}

function toWANumber(phone) {
  const clean = normalizePhone(phone);
  if (!clean || clean.length < 9) return null;
  return `34${clean}@c.us`;
}

// Nombre a mostrar del técnico de una cita. El Excel que se sube no siempre
// trae la columna "Técnico" (p. ej. la exportación por buckets) — en ese caso
// se usa el nombre del cuadrante por matrícula, y si tampoco está, la matrícula.
function nombreTecnicoCita(a) {
  const mat = String(a.matricula || '').trim().toUpperCase();
  // La consola nueva pone solo la matrícula en "Técnico" → se busca el nombre
  if (a.tecnico && String(a.tecnico).trim().toUpperCase() !== mat) return a.tecnico;
  return TEC_NAMES[mat] ? `${TEC_NAMES[mat]} (${mat})` : mat;
}

// La columna "Técnico" viene de varias formas segun de donde salga el Excel:
//   "E-MD-297373-Nombre"            (consola vieja)
//   "💰E-V-362606-Nombre Apellidos"  (consola nueva, exportado a mano; con emoji)
//   "297373"                        (consola nueva, exportacion automatica)
// La matricula es el 3er bloque "LETRAS-LETRAS-<MATRICULA>-" o el valor entero
// si es solo la matricula.
const RE_TECNICO = /([A-Z]+)-([A-Z]+)-([A-Z]?\d{4,7})-\s*(.*)$/;

function extractTechName(tecnico) {
  const t = String(tecnico || '').trim();
  const m = RE_TECNICO.exec(t);
  return m ? m[4].trim() : t;
}

function matriculaDeTecnico(tecnico) {
  const t = String(tecnico || '').trim();
  const m = RE_TECNICO.exec(t);
  if (m) return m[3].toUpperCase();
  return /^[A-Z]?\d{4,7}$/i.test(t) ? t.toUpperCase() : '';
}

// Completa la matricula de una cita que no la trae (el Excel de la consola
// nueva no tiene columna "Matrícula") y deja en "tecnico" solo el nombre.
function normalizarCita(a) {
  if (!a.matricula) a.matricula = matriculaDeTecnico(a.tecnico);
  if (a.tecnico && RE_TECNICO.test(String(a.tecnico))) a.tecnico = extractTechName(a.tecnico);
  return a;
}

function formatFecha(val) {
  if (typeof val === 'number') {
    const d = XLSX.SSF.parse_date_code(val);
    const dd = String(d.d).padStart(2, '0');
    const mm = String(d.m).padStart(2, '0');
    const yy = String(d.y).slice(-2);
    return `${dd}/${mm}/${yy}`;
  }
  return String(val || '').trim();
}

// ── Upload Excel ──────────────────────────────────────────────────────────────
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 20 * 1024 * 1024 } });

app.post('/upload', upload.single('excel'), (req, res) => {
  try {
    const matricula = String(req.body.matricula || '').trim().toUpperCase();

    if (!matricula) {
      return res.json({ ok: false, error: 'Escribe tu matrícula para continuar.' });
    }

    // Determinar qué citas mostrar según la matrícula que ha iniciado sesión:
    //  - Si está en UPLOADERS_PERMITIDOS → carga completa, todos los técnicos sin filtrar
    //  - Si es un JEFE DE EQUIPO (está en JERARQUIA) → las de todos sus técnicos
    //  - Si es un TÉCNICO → solo sus propias citas (su matrícula)
    let matriculasPermitidas = null;
    let esJE = false;
    if (UPLOADERS_PERMITIDOS.includes(matricula)) {
      matriculasPermitidas = null; // sin filtro — carga completa autorizada
    } else if (JERARQUIA[matricula]) {
      matriculasPermitidas = JERARQUIA[matricula].map(id => id.toUpperCase());
      esJE = true;
    } else {
      matriculasPermitidas = [matricula]; // modo técnico: solo lo suyo
    }

    currentJE = matricula
      ? { matricula, nombre: JE_NAMES[matricula] || matricula, esJE }
      : null;

    const wb   = XLSX.read(req.file.buffer, { type: 'buffer' });
    const ws   = wb.Sheets[wb.SheetNames[0]];
    const rows = XLSX.utils.sheet_to_json(ws);

    const newAppointments = rows
      .filter(r => {
        if (!r['Nombre del Cliente']) return false;
        if (matriculasPermitidas) {
          const mat = String(r['Matrícula'] || matriculaDeTecnico(r['Técnico'])).trim().toUpperCase();
          return matriculasPermitidas.includes(mat);
        }
        return true;
      })
      .map((r, i) => {
        const telMovil = String(r['Teléfono Móvil'] || '').replace(/\D/g, '');
        const telFijo  = String(r['Teléfono Fijo']  || '').replace(/\D/g, '');
        const telefono = telMovil.length >= 9 ? telMovil : telFijo;
        return {
          id: i,
          tecnico: extractTechName(r['Técnico']),
          matricula: String(r['Matrícula'] || matriculaDeTecnico(r['Técnico'])),
          cliente: String(r['Nombre del Cliente'] || '').trim(),
          telefono,
          numMantenimiento: String(r['Número de Mantenimiento'] || '').trim(),
          timeslot: String(r['Timeslot'] || r['Ventana de Servicio'] || '').trim(),
          tipo: String(r['Tipo de Actividad'] || '').trim(),
          fecha: formatFecha(r['Fecha de la Actividad']),
          status: telefono.length >= 9 ? 'pendiente' : 'sin_telefono',
          respuesta: '',
          horaRespuesta: ''
        };
      });

    // Se comparan con las ya cargadas:
    //  - misma cita (mismo nº de mantenimiento + misma fecha y tramo) → se deja como
    //    está, conservando su estado (enviado/confirmado...) — no se duplica.
    //  - mismo nº de mantenimiento pero OTRA fecha o tramo → es una cita
    //    reprogramada: se actualiza y vuelve a "pendiente" para confirmarla de nuevo.
    //    (Antes se descartaba por tener el mismo nº y se quedaba la cita vieja.)
    //  - nueva → se añade.
    // Antes de comparar se eliminan las citas de hoy o anteriores (ver purgarCitasPasadas).
    purgarCitasPasadas();
    const claveCita = a => a.numMantenimiento
      ? a.numMantenimiento
      : `${a.cliente}|${a.matricula}|${a.fecha}|${a.timeslot}`;

    const existentes = new Map(appointments.map(a => [claveCita(a), a]));
    let nextId = appointments.length > 0 ? Math.max(...appointments.map(a => a.id)) + 1 : 0;
    let added  = 0;
    let updated = 0;

    newAppointments.forEach(na => {
      const actual = existentes.get(claveCita(na));
      if (!actual) {
        na.id = nextId++;
        appointments.push(na);
        existentes.set(claveCita(na), na);
        added++;
        return;
      }
      if (actual.fecha === na.fecha && actual.timeslot === na.timeslot) return; // misma cita
      Object.assign(actual, {
        tecnico: na.tecnico, matricula: na.matricula, cliente: na.cliente, telefono: na.telefono,
        timeslot: na.timeslot, tipo: na.tipo, fecha: na.fecha,
        status: na.status, respuesta: '', horaRespuesta: '', sentAt: ''
      });
      updated++;
    });

    guardarSesion();
    broadcast({ type: 'update', appointments });
    broadcast({ type: 'je', je: currentJE });
    res.json({ ok: true, count: appointments.length, added, updated, je: currentJE });
  } catch (e) {
    console.error('Error al leer Excel:', e);
    res.json({ ok: false, error: e.message });
  }
});

// ── Parámetros anti-bloqueo WhatsApp ─────────────────────────────────────────
const BATCH_SIZE       = 8;             // mensajes por lote
const DELAY_MIN        = 30 * 1000;     // 30s mínimo entre mensajes
const DELAY_MAX        = 75 * 1000;     // 75s máximo entre mensajes
const BATCH_PAUSE      = 4 * 60 * 1000; // 4 min entre lotes
const DAILY_LIMIT      = 99999;         // tope diario DESACTIVADO para pruebas (antes 45)
const LONG_PAUSE_EVERY = 18;            // cada 18 mensajes, una pausa larga "humana"
const LONG_PAUSE_MIN   = 8 * 60 * 1000;
const LONG_PAUSE_MAX   = 15 * 60 * 1000;

// ── Contador diario de mensajes (persistente, se reinicia a medianoche) ───────
let dailyStats = { date: hoyStr(), count: 0 };

function hoyStr() { return new Date().toISOString().slice(0, 10); }

// Fecha de hoy en España como "AAAA-MM-DD" (el servidor de Render corre en UTC)
function hoyMadridISO() {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Madrid' }).format(new Date());
}

// "15/10/26" o "15/10/2026" → "2026-10-15"; null si no se reconoce
function fechaCitaISO(fecha) {
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/.exec(String(fecha || '').trim());
  if (!m) return null;
  const anio = m[3].length === 2 ? '20' + m[3] : m[3];
  return `${anio}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
}

// Las citas se confirman el día ANTES (la ruta que se sube hoy es la de mañana),
// así que después de medianoche ya no sirven: se elimina toda cita con fecha de
// hoy o anterior. En Render el temporizador de medianoche casi nunca llegaba a
// ejecutarse (el servicio gratuito se duerme), por eso esto se llama también al
// arrancar, cada hora y cada vez que alguien abre sus citas.
function purgarCitasPasadas() {
  const hoy = hoyMadridISO();
  const antes = appointments.length;
  appointments = appointments.filter(a => {
    const f = fechaCitaISO(a.fecha);
    return !f || f > hoy;
  });
  const quitadas = antes - appointments.length;
  if (quitadas > 0) console.log(`  Citas de días pasados eliminadas: ${quitadas}`);
  return quitadas;
}

function purgarYGuardar() {
  if (purgarCitasPasadas() > 0) { guardarSesion(); broadcast({ type: 'update', appointments }); }
}

function asegurarDiaActual() {
  const h = hoyStr();
  if (dailyStats.date !== h) dailyStats = { date: h, count: 0 };
}
function restantesHoy() {
  asegurarDiaActual();
  return Math.max(0, DAILY_LIMIT - dailyStats.count);
}

// Baraja un array (orden aleatorio) — rompe el patrón secuencial del Excel
function barajar(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// ── Send messages ─────────────────────────────────────────────────────────────
app.post('/send', async (req, res) => {
  const { ids, includeErrors } = req.body;

  if (waStatus !== 'connected') {
    return res.json({ ok: false, error: 'WhatsApp no está conectado' });
  }
  if (sendingActive) {
    return res.json({ ok: false, error: 'Ya hay un envío en curso' });
  }

  let toSend = appointments.filter(a => {
    if (ids)           return ids.includes(a.id) && (a.status === 'pendiente' || a.status === 'error');
    if (includeErrors) return a.status === 'error';
    return a.status === 'pendiente';
  });

  if (toSend.length === 0) {
    return res.json({ ok: true, sent: 0, message: 'No hay citas pendientes' });
  }

  // Aplicar tope diario — nunca superar el límite que provoca bloqueo
  const restantes = restantesHoy();
  if (restantes <= 0) {
    return res.json({
      ok: false,
      error: `Límite diario alcanzado (${DAILY_LIMIT} mensajes hoy). Continúa mañana para no bloquear el WhatsApp.`
    });
  }

  let skipped = 0;
  if (toSend.length > restantes) {
    skipped = toSend.length - restantes;
    toSend  = toSend.slice(0, restantes); // el resto queda pendiente para mañana
  }

  // Orden aleatorio para no enviar en el orden exacto del Excel
  toSend = barajar(toSend);

  res.json({ ok: true, queued: toSend.length, skipped, dailyLimit: DAILY_LIMIT, sentToday: dailyStats.count });
  sendingActive = true;

  const totalBatches = Math.ceil(toSend.length / BATCH_SIZE);
  let sent = 0;
  let enviadosEnSesion = 0; // para las pausas largas

  broadcast({ type: 'sending', active: true, total: toSend.length, batch: 1, totalBatches });
  console.log(`\n  Iniciando envío: ${toSend.length} mensajes · ${totalBatches} lote(s)`);
  if (skipped > 0) console.log(`  (${skipped} quedan para mañana por el tope diario de ${DAILY_LIMIT})`);

  for (let b = 0; b < toSend.length; b += BATCH_SIZE) {
    const batchNum = Math.floor(b / BATCH_SIZE) + 1;
    const batch    = toSend.slice(b, b + BATCH_SIZE);

    broadcast({ type: 'sending', active: true, total: toSend.length, batch: batchNum, totalBatches });
    console.log(`\n  ── Lote ${batchNum}/${totalBatches} (${batch.length} mensajes) ──`);

    for (let i = 0; i < batch.length; i++) {
      const apt = batch[i];

      // Cortar si se alcanzó el tope diario durante el envío
      if (restantesHoy() <= 0) {
        console.log(`  ⛔ Tope diario (${DAILY_LIMIT}) alcanzado — deteniendo envío.`);
        broadcast({ type: 'notice', level: 'warning',
          text: `Tope diario de ${DAILY_LIMIT} mensajes alcanzado. El resto se enviará mañana.` });
        b = toSend.length; // forzar salida del bucle de lotes
        break;
      }

      const fullNum = '34' + normalizePhone(apt.telefono);
      if (normalizePhone(apt.telefono).length < 9) {
        apt.status = 'sin_telefono';
        broadcast({ type: 'update', appointments });
        continue;
      }

      // 1) Verificar que el número EXISTE en WhatsApp antes de enviar.
      //    Enviar a números inválidos es una de las mayores señales de spam.
      //    Solo marcamos "sin WhatsApp" si la consulta tuvo éxito y devolvió
      //    no-registrado; si la consulta falla, intentamos enviar igual.
      let numberId      = null;
      let consultaOk    = false;
      try {
        numberId   = await client.getNumberId(fullNum);
        consultaOk = true;
      } catch (e) {
        consultaOk = false;
      }

      if (consultaOk && !numberId) {
        apt.status = 'sin_whatsapp';
        apt.respuesta = 'El número no tiene WhatsApp';
        broadcast({ type: 'update', appointments });
        guardarSesion();
        console.log(`  ✗ ${apt.cliente}: número sin WhatsApp (${apt.telefono})`);
        continue;
      }

      const waId = (numberId && numberId._serialized) ? numberId._serialized : toWANumber(apt.telefono);
      if (!waId) {
        apt.status = 'sin_telefono';
        broadcast({ type: 'update', appointments });
        continue;
      }

      const firstName = apt.cliente.split(' ')[0];

      // Variaciones de saludo y cierre para que cada mensaje sea distinto
      const saludos = [
        `Hola ${firstName}, le contactamos de *Verisure*.`,
        `Buenos días ${firstName}, le escribimos desde *Verisure*.`,
        `Buenas ${firstName}, somos de *Verisure*.`,
        `Hola ${firstName}, le saludamos desde *Verisure*.`,
        `Hola ${firstName}, le contactamos desde el equipo de *Verisure*.`,
        `${firstName}, buenas, le contactamos de *Verisure*.`
      ];
      const intros = [
        `Tiene programada una visita de *${apt.tipo}* para el *${apt.fecha}* en el tramo horario *${apt.timeslot}h*.`,
        `Le recordamos su visita de *${apt.tipo}*, prevista para el *${apt.fecha}* en el tramo *${apt.timeslot}h*.`,
        `Su cita de *${apt.tipo}* está agendada para el *${apt.fecha}*, tramo horario *${apt.timeslot}h*.`
      ];
      const preguntas = [
        `¿Puede confirmar la cita?`,
        `¿Nos confirma que estará disponible?`,
        `¿Podría confirmarnos la visita?`
      ];
      const cierres = [
        `Gracias por su atención.`,
        `Muchas gracias.`,
        `Gracias y disculpe las molestias.`,
        `Agradecemos su respuesta.`,
        `Gracias por su tiempo.`
      ];
      const pick = arr => arr[Math.floor(Math.random() * arr.length)];

      const msg =
        `${pick(saludos)}\n\n` +
        `${pick(intros)}\n\n` +
        `${pick(preguntas)}\n` +
        `✅ Responda *SÍ* para confirmar\n` +
        `❌ Responda *NO* si no puede recibirnos\n\n` +
        `${pick(cierres)}`;

      try {
        // Simular escritura antes de enviar (comportamiento más humano)
        try {
          const chat = await client.getChatById(waId);
          await chat.sendStateTyping();
          await new Promise(r => setTimeout(r, 1500 + Math.random() * 2500));
          await chat.clearState();
        } catch(e) {
          await new Promise(r => setTimeout(r, 800 + Math.random() * 700));
        }

        // Enviar con un reintento: en el primer mensaje a un contacto nuevo,
        // whatsapp-web.js a veces falla con "Cannot read properties of null"
        // porque WhatsApp Web aún no ha indexado el chat internamente.
        // Casi siempre funciona al reintentar unos segundos después.
        let sentMsg;
        try {
          sentMsg = await client.sendMessage(waId, msg);
        } catch (firstErr) {
          console.log(`  [${batchNum}/${totalBatches}] Reintentando envío a ${apt.cliente} (${firstErr.message})...`);
          await new Promise(r => setTimeout(r, 3000));
          sentMsg = await client.sendMessage(waId, msg); // si falla otra vez, cae al catch de fuera
        }

        apt.sentAt = Date.now();
        apt.chatId = normalizePhone(waId.replace(/@.*/, ''));
        try {
          const sentChat = await sentMsg.getChat();
          if (sentChat && sentChat.id && sentChat.id._serialized) {
            apt.chatId = normalizePhone(sentChat.id._serialized.replace(/@.*/, ''));
          }
        } catch(e) {}
        apt.status = 'enviado';
        sent++;
        enviadosEnSesion++;
        asegurarDiaActual();
        dailyStats.count++;
        console.log(`  [${batchNum}/${totalBatches}] ✓ ${apt.cliente} | hoy: ${dailyStats.count}/${DAILY_LIMIT}`);
      } catch (e) {
        apt.status = 'error';
        // Mensaje claro para el JE en vez del error técnico en inglés
        apt.respuesta = /cannot read propert/i.test(e.message)
          ? 'Fallo temporal de WhatsApp — pulsa reenviar'
          : e.message;
        console.error(`  [${batchNum}/${totalBatches}] ✗ ${apt.cliente}: ${e.message}`);
      }

      broadcast({ type: 'update', appointments });
      guardarSesion();

      const esUltimo = (b + i + 1 >= toSend.length);
      if (esUltimo) break;

      // Pausa larga "humana" cada cierto número de mensajes — rompe el ritmo
      if (enviadosEnSesion > 0 && enviadosEnSesion % LONG_PAUSE_EVERY === 0) {
        let remainingSec = Math.round((LONG_PAUSE_MIN + Math.random() * (LONG_PAUSE_MAX - LONG_PAUSE_MIN)) / 1000);
        console.log(`\n  ☕ Pausa larga de descanso: ${Math.round(remainingSec / 60)} min...`);
        broadcast({ type: 'batch_pause', seconds: remainingSec, batch: batchNum, totalBatches, long: true });
        while (remainingSec > 0) {
          const tick = Math.min(15, remainingSec);
          await new Promise(r => setTimeout(r, tick * 1000));
          remainingSec -= tick;
          if (remainingSec > 0) broadcast({ type: 'batch_pause', seconds: remainingSec, batch: batchNum, totalBatches, long: true });
        }
      } else {
        const pausa = DELAY_MIN + Math.floor(Math.random() * (DELAY_MAX - DELAY_MIN));
        console.log(`  Esperando ${Math.round(pausa / 1000)}s...`);
        await new Promise(r => setTimeout(r, pausa));
      }
    }

    const esUltimoLote = (b + BATCH_SIZE >= toSend.length);
    if (!esUltimoLote) {
      let remainingSec = Math.round(BATCH_PAUSE / 1000);
      console.log(`\n  ⏸ Pausa entre lotes: ${remainingSec / 60} min...`);
      broadcast({ type: 'batch_pause', seconds: remainingSec, batch: batchNum, totalBatches });
      while (remainingSec > 0) {
        const tick = Math.min(15, remainingSec);
        await new Promise(r => setTimeout(r, tick * 1000));
        remainingSec -= tick;
        if (remainingSec > 0) {
          broadcast({ type: 'batch_pause', seconds: remainingSec, batch: batchNum, totalBatches });
        }
      }
      console.log(`  ▶ Reanudando lote ${batchNum + 1}/${totalBatches}...`);
    }
  }

  sendingActive = false;
  broadcast({ type: 'sending', active: false, total: 0, batch: 0, totalBatches: 0 });
  guardarSesion();
  console.log(`\n  Envío completado: ${sent} enviados · ${dailyStats.count}/${DAILY_LIMIT} hoy`);
});

// ── Borrar todas las citas ────────────────────────────────────────────────────
app.post('/clear', (req, res) => {
  appointments = [];
  currentJE    = null;
  guardarSesion();
  broadcast({ type: 'update', appointments });
  broadcast({ type: 'je', je: null });
  res.json({ ok: true });
});

// ── Resetear estado de citas a pendiente ──────────────────────────────────────
app.post('/reset', (req, res) => {
  const { ids } = req.body;
  const toReset = ids ? appointments.filter(a => ids.includes(a.id)) : appointments;
  toReset.forEach(a => {
    if (a.telefono.length >= 9) {
      a.status = 'pendiente';
      a.respuesta = '';
      a.horaRespuesta = '';
    }
  });
  broadcast({ type: 'update', appointments });
  res.json({ ok: true });
});

// ── Vista móvil para técnicos (envío por SMS desde su propio teléfono) ────────
// El técnico abre /tecnico.html, ve solo sus citas y manda el SMS con el
// enlace nativo sms: — el servidor nunca envía el SMS, solo guarda el estado.
app.get('/mis-citas', (req, res) => {
  purgarYGuardar();
  const matricula = String(req.query.matricula || '').trim().toUpperCase();
  const dni       = String(req.query.dni || '').trim();
  if (!matricula || !dni) return res.json({ ok: false, error: 'Falta matrícula o DNI' });
  if (!verificarDNI(matricula, dni)) {
    return res.json({ ok: false, error: 'Matrícula o DNI incorrectos' });
  }
  // Todas las citas cargadas del técnico, igual que ve su JE. Antes solo se
  // devolvían las de "mañana", y se quedaban fuera (p. ej. un sábado se carga la
  // ruta del lunes, o el Excel trae la fecha en otro formato que dd/mm/aa).
  const mias = appointments.filter(a =>
    String(a.matricula || '').trim().toUpperCase() === matricula
  );
  const fechas = [...new Set(mias.map(a => a.fecha).filter(Boolean))];
  res.json({ ok: true, citas: mias, fecha: fechas.join(' y ') });
});

// ── Vista móvil para JE: todo el equipo, agrupado por técnico ────────────────
// Usa la misma jerarquía en vivo (Google Sheets) que ya carga el servidor,
// así que funciona con cualquier matrícula de JE sin tener que tocar código.
app.get('/mis-citas-equipo', (req, res) => {
  purgarYGuardar();
  const matricula = String(req.query.matricula || '').trim().toUpperCase();
  const dni       = String(req.query.dni || '').trim();
  if (!matricula || !dni) return res.json({ ok: false, error: 'Falta matrícula o DNI' });
  if (!verificarDNI(matricula, dni)) {
    return res.json({ ok: false, error: 'Matrícula o DNI incorrectos' });
  }

  const tecnicos = JERARQUIA[matricula] ? JERARQUIA[matricula].map(id => id.toUpperCase()) : null;
  if (!tecnicos) {
    return res.json({ ok: false, error: 'Esa matrícula no es de un jefe de equipo reconocido' });
  }

  const delEquipo = appointments
    .filter(a => tecnicos.includes(String(a.matricula || '').trim().toUpperCase()))
    .map(a => ({ ...a, tecnico: nombreTecnicoCita(a) }));
  res.json({ ok: true, citas: delEquipo, nombre: JE_NAMES[matricula] || matricula, totalTecnicos: tecnicos.length });
});

app.post('/marcar-respuesta', (req, res) => {
  const { id, status } = req.body;
  const estadosValidos = ['enviado', 'confirmado', 'no_confirmado', 'pendiente'];
  if (!estadosValidos.includes(status)) {
    return res.json({ ok: false, error: 'Estado inválido' });
  }
  const apt = appointments.find(a => a.id === id);
  if (!apt) return res.json({ ok: false, error: 'Cita no encontrada' });

  apt.status = status;
  if (status === 'confirmado')    apt.respuesta = 'Confirmado por SMS (marcado por el técnico)';
  else if (status === 'no_confirmado') apt.respuesta = 'No confirma (marcado por el técnico)';
  else if (status === 'enviado')  { apt.respuesta = ''; apt.sentAt = Date.now(); }
  else apt.respuesta = '';
  apt.horaRespuesta = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });

  guardarSesion();
  broadcast({ type: 'update', appointments });
  res.json({ ok: true });
});

// ── Status ────────────────────────────────────────────────────────────────────
app.get('/status', (req, res) => {
  purgarYGuardar();
  res.json({ waStatus, count: appointments.length, sendingActive });
});

// ── Diagnóstico ───────────────────────────────────────────────────────────────
app.get('/diagnostico', (req, res) => {
  const chromePath = findChrome();
  const authDir    = path.join(__dirname, '.wwebjs_auth');
  let puppeteerPath = null;
  try { puppeteerPath = require('puppeteer').executablePath(); } catch(e) {}
  res.json({
    waStatus,
    chromePath:        chromePath || null,
    chromeExists:      chromePath ? fs.existsSync(chromePath) : false,
    puppeteerPath:     puppeteerPath || null,
    puppeteerExists:   puppeteerPath ? fs.existsSync(puppeteerPath) : false,
    authDirExists:     fs.existsSync(authDir),
    platform:          process.platform,
    nodeVersion:       process.version
  });
});

// ── Cerrar sesión WhatsApp ────────────────────────────────────────────────────
app.post('/logout', async (req, res) => {
  if (!WHATSAPP_ENABLED || !client) {
    return res.json({ ok: false, error: 'WhatsApp está desactivado en este servidor' });
  }
  try {
    await client.logout();
    waStatus = 'disconnected';
    lastQR   = null;
    broadcast({ type: 'wa_status', status: 'disconnected' });
    res.json({ ok: true });
    console.log('  WhatsApp: sesión cerrada');
  } catch(e) {
    res.json({ ok: false, error: e.message });
  }
});

// ── Reinicio forzado: borra sesión y crea cliente nuevo ───────────────────────
app.post('/reiniciar-wa', async (req, res) => {
  if (!WHATSAPP_ENABLED) {
    return res.json({ ok: false, error: 'WhatsApp está desactivado en este servidor' });
  }
  try {
    // Destruir cliente actual (ignorar errores — puede ya estar caído)
    try { if (client) await client.destroy(); } catch(e) {}

    waStatus = 'initializing';
    lastQR   = null;
    broadcast({ type: 'wa_status', status: 'initializing' });
    res.json({ ok: true });

    // Borrar sesión guardada en disco
    const authDir = path.join(__dirname, '.wwebjs_auth');
    if (fs.existsSync(authDir)) {
      fs.rmSync(authDir, { recursive: true, force: true });
      console.log('  Sesión anterior borrada (.wwebjs_auth)');
    }

    // Crear instancia nueva (no se puede reutilizar la anterior tras destroy)
    setTimeout(() => {
      crearClienteWA();
      console.log('  WhatsApp reiniciado — esperando QR...');
    }, 2000);

  } catch(e) {
    console.error('[reiniciar-wa]', e.message);
    if (!res.headersSent) res.json({ ok: false, error: e.message });
  }
});

// ── WebSocket: enviar estado actual a nuevas conexiones ───────────────────────
wss.on('connection', (ws) => {
  ws.send(JSON.stringify({ type: 'wa_status', status: waStatus }));
  ws.send(JSON.stringify({ type: 'update', appointments }));
  ws.send(JSON.stringify({ type: 'sending', active: sendingActive }));
  ws.send(JSON.stringify({ type: 'je', je: currentJE }));
  if (waStatus === 'qr' && lastQR) {
    ws.send(JSON.stringify({ type: 'qr', qr: lastQR }));
  }
});

// ── Errores no controlados (el servidor sigue funcionando) ────────────────────
process.on('uncaughtException', (err) => {
  console.error('\n[ERROR NO CONTROLADO]', err.message);
});
process.on('unhandledRejection', (reason) => {
  console.error('\n[PROMESA RECHAZADA]', reason);
});

// ── Limpieza automática a medianoche ─────────────────────────────────────────
function programarLimpiezaMedianoche() {
  const ahora      = new Date();
  const medianoche = new Date(ahora);
  medianoche.setHours(24, 0, 0, 0);
  const ms  = medianoche - ahora;
  const min = Math.round(ms / 60000);
  console.log(`  Limpieza automática programada en ${min} minutos (medianoche)`);

  setTimeout(() => {
    // Pasada la medianoche las citas de hoy ya no sirven. Ver purgarCitasPasadas().
    purgarCitasPasadas();
    dailyStats   = { date: hoyStr(), count: 0 }; // reiniciar contador diario
    guardarSesion();
    broadcast({ type: 'update', appointments });
    console.log('\n  Limpieza de medianoche completada (contador diario a 0)\n');
    programarLimpiezaMedianoche();
  }, ms);
}

// ── Inicio ────────────────────────────────────────────────────────────────────
cargarJerarquia();
setInterval(cargarJerarquia, 60 * 60 * 1000);
cargarAuth();
setInterval(cargarAuth, 60 * 60 * 1000);
// Al arrancar (Render reinicia el servicio a menudo) y luego cada hora
iniciarPersistencia().then(purgarYGuardar);
setInterval(purgarYGuardar, 60 * 60 * 1000);
programarLimpiezaMedianoche();

const PORT = process.env.PORT || 3000;
server.listen(PORT, (err) => {
  if (err) {
    if (err.code === 'EADDRINUSE') {
      console.error(`\n[ERROR] El puerto ${PORT} ya está en uso.`);
      console.error('  Cierra la otra ventana del servidor y vuelve a abrir INICIAR.bat\n');
    } else {
      console.error('\n[ERROR al iniciar servidor]', err.message);
    }
    process.exit(1);
  }
  console.log('\n==========================================');
  console.log('  Verisure - Confirmaciones WhatsApp');
  console.log('==========================================');
  console.log(`\n  Aplicacion lista en: http://localhost:${PORT}`);
  if (WHATSAPP_ENABLED) {
    console.log('\n  Iniciando WhatsApp...');
    console.log('  Espera unos segundos y escanea el QR');
    console.log('  que aparece en el navegador.\n');
    crearClienteWA();
  } else {
    waStatus = 'disabled';
    console.log('\n  WhatsApp desactivado en este servidor (WHATSAPP_ENABLED no está en "true").');
    console.log('  Las páginas de SMS (tecnico.html, je.html) funcionan igual.\n');
  }
  console.log('  [Para cerrar: Ctrl+C o cierra esta ventana]\n');
});
