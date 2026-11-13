// Confirmaciones por WhatsApp desde el Mac de cada jefe de equipo (Aurum).
//
// - Las citas salen de Render (/mis-citas-equipo, con matrícula + DNI del JE),
//   igual que la vista de JE de los SMS: solo las de sus técnicos.
// - Se envían por el WhatsApp del JE (vinculado con QR), con ritmo "humano".
// - Lee las respuestas del cliente (Sí / No), contesta solo y avisa a Render
//   (/equipo-estado) para que el estado se vea en todas las vistas.
// - En este Mac NO se guardan datos de clientes: solo el nº de mantenimiento,
//   la fecha/tramo y un hash del teléfono para reconocer la respuesta.
'use strict';
const express = require('express');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { spawn, execSync } = require('child_process');
const QRCode = require('qrcode');
const { Client, LocalAuth } = require('whatsapp-web.js');

const VERSION = '2026.11.13b';
const RENDER = (process.env.RENDER_URL || 'https://tecnicos-aurum.onrender.com').replace(/\/$/, '');
const PORT = Number(process.env.PORT || 3131);
const ES_WIN = process.platform === 'win32';
const DATA_DIR = process.env.DATA_DIR || (ES_WIN
  ? path.join(process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming'), 'AurumWhatsApp')
  : path.join(os.homedir(), 'Library', 'Application Support', 'AurumWhatsApp'));
fs.mkdirSync(DATA_DIR, { recursive: true });
const F_CONFIG = path.join(DATA_DIR, 'config.json');       // matrícula + DNI del JE (permiso 600)
const F_REGISTRO = path.join(DATA_DIR, 'registro.json');   // envíos (sin datos de clientes)
const F_PLANTILLAS = path.join(DATA_DIR, 'plantillas.json');

// ── Ritmo anti-bloqueo (mismo criterio que el sistema anterior) ─────────────
const BATCH_SIZE = 8;
const DELAY_MIN = 30e3, DELAY_MAX = 75e3;        // entre mensajes
const BATCH_PAUSE = 4 * 60e3;                     // entre lotes
const LONG_PAUSE_EVERY = 18, LONG_PAUSE_MIN = 8 * 60e3, LONG_PAUSE_MAX = 15 * 60e3;
const DAILY_LIMIT = Number(process.env.LIMITE_DIARIO || 80);

// ── Utilidades ──────────────────────────────────────────────────────────────
const leer = (f, def) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return def; } };
const escribir = (f, obj, modo) => {
  fs.writeFileSync(f + '.tmp', JSON.stringify(obj, null, 2), { mode: modo || 0o600 });
  fs.renameSync(f + '.tmp', f);
};
const espera = ms => new Promise(r => setTimeout(r, ms));
const azar = (a, b) => a + Math.floor(Math.random() * (b - a));
const pick = arr => arr[Math.floor(Math.random() * arr.length)];
const soloDigitos = s => String(s || '').replace(/\D/g, '');
const telNacional = s => soloDigitos(s).replace(/^0034/, '').replace(/^34(?=\d{9}$)/, '');
const hash = s => crypto.createHash('sha256').update('aurum|' + s).digest('hex').slice(0, 24);
const norm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ').trim();
const log = (...a) => console.log(new Date().toLocaleTimeString('es-ES'), ...a);

function fechaPasada(ddmmyy) {
  const m = String(ddmmyy || '').match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if (!m) return false;
  const y = m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3]);
  const d = new Date(y, Number(m[2]) - 1, Number(m[1]), 23, 59);
  return d.getTime() < Date.now() - 24 * 3600e3; // margen de un día
}

// ── Estado ──────────────────────────────────────────────────────────────────
let config = leer(F_CONFIG, {});            // { mat, dni, nombre }
let registro = leer(F_REGISTRO, {});        // num -> { h:[hashes], sentAt, fecha, tramo, tipo, status, gestionada, prueba, hora }
let citas = [];                             // última carga de Render (solo en memoria)
let ultimaCarga = 0;
let hoy = { fecha: new Date().toDateString(), enviados: 0 };
let envio = { activo: false, parar: false, total: 0, hechos: 0, fallos: 0, aviso: '', pausaHasta: 0 };
let wa = { estado: 'iniciando', qr: '', numero: '' };

function guardarRegistro() {
  for (const [k, r] of Object.entries(registro)) if (fechaPasada(r.fecha)) delete registro[k];
  escribir(F_REGISTRO, registro);
}
guardarRegistro();

// ── Plantillas ──────────────────────────────────────────────────────────────
// {nombre} {tipo} {fecha} {tramo}. Varias versiones separadas por una línea "---":
// se elige una al azar en cada mensaje para que no salgan todos iguales.
const PLANTILLAS_DEF = {
  // Un solo mensaje para todos los tipos (decisión de Gustavo, 12/11/2026).
  // Si algún día hace falta uno propio para un tipo, se añade en porTipo desde la app.
  general: 'Hola {nombre}, soy el técnico de *Verisure* que {cuando} pasará por tu domicilio para la visita de *{tipo}*.\n\n' +
    'Estaré pasando en el horario de *{tramo}h*.\n\n' +
    '¿Te viene bien estar disponible en ese horario?\n\n' +
    '✅ Responde *SÍ* para confirmar\n' +
    '❌ Responde *NO* si no puedes y te cambiamos la cita\n\n' +
    '¡Muchas gracias!',
  porTipo: {},
  respuestaSi: '¡Perfecto, muchas gracias por confirmar! ✅\n\nNos vemos {cuando} en el horario de *{tramo}h*. 😊',
  respuestaNo: 'Entendido, gracias por avisar.\n\nTe llamaremos para buscar otro momento para la visita. 🙏'
};
function plantillas() { return { ...PLANTILLAS_DEF, ...leer(F_PLANTILLAS, {}) }; }
function cuando(fecha) {
  const m = String(fecha || '').match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if (!m) return fecha ? 'el ' + fecha : 'pronto';
  const y = m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3]);
  const d = new Date(y, Number(m[2]) - 1, Number(m[1]));
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  const dias = Math.round((d - hoy) / 864e5);
  return dias === 0 ? 'hoy' : dias === 1 ? 'mañana' : 'el ' + fecha;
}
function rellenar(txt, c) {
  const nombre = String(c.cliente || '').trim().split(/\s+/)[0] || '';
  const nom = nombre ? nombre.charAt(0).toUpperCase() + nombre.slice(1).toLowerCase() : '';
  return String(txt)
    .replace(/\{nombre\}/g, nom).replace(/\{tipo\}/g, c.tipo || 'mantenimiento')
    .replace(/\{fecha\}/g, c.fecha || '').replace(/\{cuando\}/g, cuando(c.fecha)).replace(/\{Cuando\}/g, (w => w.charAt(0).toUpperCase() + w.slice(1))(cuando(c.fecha))).replace(/\{tramo\}/g, c.timeslot || c.tramo || '')
    .replace(/Hola ,/g, 'Hola,').replace(/Buenas ,/g, 'Buenas,').replace(/días ,/g, 'días,');
}
function versiones(txt) { return String(txt || '').split(/\n\s*---\s*\n/).map(s => s.trim()).filter(Boolean); }
// Cada clave de porTipo es una "familia": una o varias palabras separadas por |.
// Una cita usa la familia cuyo texto aparece en su tipo (gana la coincidencia
// más larga): "Ampliación" vale para "Ampliación 1 a 3 elementos", "Ampliación VF4"...
function familiaDe(tipo, porTipo) {
  const t = norm(tipo);
  let mejor = null, largo = 0;
  for (const [clave, txt] of Object.entries(porTipo || {})) {
    if (!String(txt).trim()) continue;
    for (const alt of clave.split('|').map(norm).filter(Boolean)) {
      const re = new RegExp('(^|[^a-z0-9])' + alt.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
      if (re.test(t) && alt.length > largo) { mejor = clave; largo = alt.length; }
    }
  }
  return mejor;
}
function mensajePara(c) {
  const p = plantillas();
  const fam = familiaDe(c.tipo, p.porTipo);
  return rellenar(pick(versiones(fam ? p.porTipo[fam] : p.general)), c);
}

// ── Render ──────────────────────────────────────────────────────────────────
// El plan gratis de Render se duerme: se reintenta hasta ~70 s.
async function render(ruta, opciones = {}) {
  let ultimo;
  for (let i = 0; i < 4; i++) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 25e3);
      const r = await fetch(RENDER + ruta, { ...opciones, signal: ctrl.signal });
      clearTimeout(t);
      const txt = await r.text();
      try { return JSON.parse(txt); } catch { throw new Error('Respuesta no válida de Render (' + r.status + ')'); }
    } catch (e) { ultimo = e; await espera(5e3 + i * 5e3); }
  }
  throw new Error('Render no responde: ' + (ultimo && ultimo.message));
}

async function cargarCitas(mat, dni) {
  const q = `?matricula=${encodeURIComponent(mat)}&dni=${encodeURIComponent(dni)}`;
  const d = await render('/mis-citas-equipo' + q);
  if (!d.ok) throw new Error(d.error || 'No se pudieron cargar las citas');
  citas = d.citas || [];
  ultimaCarga = Date.now();
  return d;
}

// Avisos a Render en cola, para no perder ninguno si Render está dormido.
let colaRender = Promise.resolve();
function avisarRender(num, status, respuesta) {
  if (!config.mat || !config.dni) return;
  colaRender = colaRender.then(async () => {
    try {
      const d = await render('/equipo-estado', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ matricula: config.mat, dni: config.dni, numMantenimiento: num, status, respuesta })
      });
      if (!d.ok) log('Render no aceptó el estado de', num, ':', d.error);
      const c = citas.find(x => String(x.numMantenimiento) === String(num));
      if (c && d.ok) c.status = status;
    } catch (e) { log('Error avisando a Render:', e.message); }
  });
}

// ── WhatsApp ────────────────────────────────────────────────────────────────
// Se usa el Google Chrome del Mac si está instalado (no toca el Chrome normal:
// abre uno aparte, sin ventana y con su propia carpeta). Si no, el de puppeteer.
const CHROMES = ES_WIN ? [
  path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  path.join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  path.join(process.env.LOCALAPPDATA || '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  path.join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Microsoft', 'Edge', 'Application', 'msedge.exe')
] : [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  path.join(os.homedir(), 'Applications', 'Google Chrome.app', 'Contents', 'MacOS', 'Google Chrome')
];
const executablePath = process.env.CHROME_PATH || CHROMES.find(c => { try { return fs.existsSync(c); } catch { return false; } });
const client = new Client({
  authStrategy: new LocalAuth({ clientId: 'aurum-je', dataPath: path.join(DATA_DIR, 'wa') }),
  // WhatsApp Web puede tardar más de 30 s en cargar con una conexión o un equipo lentos
  authTimeoutMs: 10 * 60e3,   // en algunos equipos WhatsApp Web tarda 2-3 min en cargar: se espera sin cortar
  puppeteer: { headless: true, executablePath, args: ['--no-sandbox', '--disable-dev-shm-usage'] }
});
// Aviso a Render de cómo va el arranque (para ver fallos sin pedir capturas).
// Sin datos de clientes: matrícula del JE, versión, sistema, Chrome y el error.
let infoEquipo = null;
function datosEquipo() {
  if (infoEquipo) return infoEquipo;
  let so = ES_WIN ? 'Windows ' + os.release() : 'macOS', chrome = executablePath ? '' : 'sin Chrome';
  try { if (!ES_WIN) so = 'macOS ' + execSync('sw_vers -productVersion', { timeout: 5e3 }).toString().trim(); } catch {}
  try {
    if (executablePath) chrome = ES_WIN
      ? 'Chrome ' + execSync(`powershell -NoProfile -Command "(Get-Item '${executablePath}').VersionInfo.ProductVersion"`, { timeout: 15e3, windowsHide: true }).toString().trim()
      : execSync(`${JSON.stringify(executablePath)} --version`, { timeout: 15e3 }).toString().trim();
  } catch (e) { chrome = (chrome || 'Chrome') + ' (no responde)'; }
  let arch = process.arch;
  try { if (!ES_WIN && arch === 'x64' && execSync('sysctl -n hw.optional.arm64', { timeout: 5e3 }).toString().trim() === '1') arch = 'x64 con Rosetta en Apple Silicon'; } catch {}
  return (infoEquipo = { so, arch, chrome, node: process.version });
}
const avisados = new Set();
function diagnostico(evento, detalle = '', unaVez = false) {
  if (unaVez) { if (avisados.has(evento)) return; avisados.add(evento); }
  const cuerpo = JSON.stringify({ mat: (config && config.mat) || '', evento, version: VERSION, detalle, ...datosEquipo() });
  fetch(RENDER + '/wa-diagnostico', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: cuerpo, signal: AbortSignal.timeout(90e3) })
    .catch(() => {});
}

client.on('loading_screen', p => { wa.progreso = Number(p) || 0; });
client.on('qr', async qr => { diagnostico('qr', 'tardó ' + Math.round((Date.now() - (wa.desde || Date.now())) / 1e3) + ' s', true); wa = { estado: 'qr', qr: await QRCode.toDataURL(qr), numero: '' }; log('Escanea el QR desde la app'); });
client.on('authenticated', () => { wa.estado = 'conectando'; wa.qr = ''; desdeConectando = Date.now(); diagnostico('autenticado', '', true); });
client.on('ready', () => {
  wa = { estado: 'conectado', qr: '', numero: client.info && client.info.wid ? client.info.wid.user.slice(-4) : '' };
  log('WhatsApp conectado'); diagnostico('conectado', '', true);
});
client.on('auth_failure', m => { wa.estado = 'error'; diagnostico('fallo-auth', String(m)); log('Fallo de autenticación:', m); });
client.on('disconnected', r => {
  wa = { estado: 'desconectado', qr: '', numero: '' };
  log('WhatsApp desconectado:', r);
  setTimeout(() => arrancarWA(), 5e3);
});

// Limpia restos de intentos anteriores: Chrome ocultos que se quedaron abiertos
// con la carpeta de WhatsApp y los ficheros de bloqueo que dejan (si no, el
// Chrome nuevo no puede abrir la sesión y WhatsApp no llega a cargar).
const WA_DIR = path.join(DATA_DIR, 'wa');
function limpiarChromeColgados() {
  try {
    if (ES_WIN) {
      execSync(`powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*AurumWhatsApp*wa*' -and $_.Name -match 'chrome|msedge' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"`, { stdio: 'ignore', windowsHide: true, timeout: 20e3 });
    } else {
      execSync(`pkill -9 -f -- ${JSON.stringify('user-data-dir=' + WA_DIR)}`, { stdio: 'ignore', timeout: 10e3 });
    }
  } catch {}
  try {
    for (const d of fs.readdirSync(WA_DIR)) for (const f of ['SingletonLock', 'SingletonSocket', 'SingletonCookie'])
      try { fs.rmSync(path.join(WA_DIR, d, f), { force: true }); } catch {}
  } catch {}
}

// Arranca WhatsApp y, si falla (red lenta, Chrome ocupado), lo reintenta solo hasta 4 veces
let arrancando = false;
async function arrancarWA(intento = 1) {
  if (arrancando) return; arrancando = true;
  try {
    if (intento > 1) { wa.estado = 'iniciando'; wa.detalle = ''; }
    wa.desde = Date.now(); wa.progreso = 0;
    limpiarChromeColgados();
    // Al tercer intento se descarta la vinculación a medias (obliga a escanear el QR de nuevo)
    if (intento === 2) { try { fs.rmSync(WA_DIR, { recursive: true, force: true }); log('Sesión de WhatsApp reiniciada'); } catch {} }
    // whatsapp-web.js solo engancha la recarga de la página la primera vez: al
    // reutilizar el cliente hay que volver a engancharla en la página nueva
    client._framenavigatedRegistered = false;
    await client.initialize();
  } catch (e) {
    const m = String((e && e.message) || e).split('\n')[0];
    log(`No arrancó WhatsApp (intento ${intento}):`, m);
    diagnostico('error', `intento ${intento}: ${m}`);
    try { await client.destroy(); } catch {}
    if (!executablePath) { wa.estado = 'error'; wa.detalle = 'Falta Google Chrome: instálalo desde google.com/chrome y vuelve a abrir la app.'; }
    else if (intento < 4) {
      wa.estado = 'error'; wa.detalle = `WhatsApp está tardando en cargar. Reintentando solo (${intento + 1} de 4)…`;
      arrancando = false; setTimeout(() => arrancarWA(intento + 1), 15e3); return;
    } else { wa.estado = 'error'; wa.detalle = 'No arrancó WhatsApp (' + m + '). Comprueba la conexión a internet y pulsa Reintentar.'; }
  } finally { arrancando = false; }
}

// Sí / No (mismo criterio que el sistema anterior)
const SI = [/\bsi\b/, /\byes\b/, /\bok\b/, /\bokey\b/, /\bclaro\b/, /\bvale\b/, /\bconfirm(o|a|ado|amos)\b/, /\bperfecto\b/,
  /\bde acuerdo\b/, /\bestare\b/, /\bestaremos\b/, /\bpor supuesto\b/, /\bafirmativo\b/, /\bcorrecto\b/, /\bgenial\b/, /^👍/];
const NO = [/\bno puedo\b/, /\bno podre\b/, /\bno podemos\b/, /\bno estare\b/, /\bno estaremos\b/, /\bimposible\b/,
  /\bcancel/, /\banul/, /\bno confirmo\b/, /\bcambiar (la )?(cita|fecha|dia|hora)\b/, /\bno me viene\b/, /\botro dia\b/];
function clasificar(texto) {
  const t = norm(texto);
  const primera = t.split(/[\s,!?.¡¿]+/)[0];
  const no = primera === 'no' || NO.some(p => p.test(t));
  const si = ['si', 'yes', 'ok', 'vale', 'sii', 'siii'].includes(primera) || SI.some(p => p.test(t));
  if (no && !si) return 'no_confirmado';
  if (si && !no) return 'confirmado';
  return 'otra_respuesta'; // dudosas (p. ej. "sí, pero no puedo a esa hora") las revisa el JE
}

client.on('message', async msg => {
  try {
    if (msg.fromMe || msg.from.endsWith('@g.us') || msg.from === 'status@broadcast') return;
    const claves = new Set([hash(msg.from)]);
    try { const ct = await msg.getContact(); if (ct && ct.number) claves.add(hash(telNacional(ct.number))); } catch {}
    try { const ch = await msg.getChat(); if (ch && ch.id) claves.add(hash(ch.id._serialized)); } catch {}

    // La última cita enviada a ese número que aún espera respuesta
    const candidatas = Object.entries(registro)
      .filter(([, r]) => r.h && r.h.some(h => claves.has(h)) && ['enviado', 'otra_respuesta'].includes(r.status))
      .sort((a, b) => b[1].sentAt - a[1].sentAt);
    if (!candidatas.length) return;
    const [num, r] = candidatas[0];
    if (msg.timestamp && msg.timestamp * 1000 < r.sentAt) return;

    const status = clasificar(msg.body || '');
    r.status = status;
    r.hora = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    guardarRegistro();
    log(`Respuesta de ${num}: ${status}`);
    if (!r.prueba) avisarRender(num, status, String(msg.body || '').slice(0, 300));

    if (status === 'confirmado' || status === 'no_confirmado') {
      const p = plantillas();
      const txt = rellenar(status === 'confirmado' ? p.respuestaSi : p.respuestaNo, { fecha: r.fecha, tramo: r.tramo, tipo: r.tipo });
      await espera(azar(3e3, 7e3));
      try { const ch = await msg.getChat(); await ch.sendStateTyping(); await espera(azar(1500, 3500)); } catch {}
      await client.sendMessage(msg.from, txt);
    }
  } catch (e) { log('Error leyendo respuesta:', e.message); }
});

// ── Envío ───────────────────────────────────────────────────────────────────
function barajar(a) { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
function contarHoy() { const d = new Date().toDateString(); if (hoy.fecha !== d) hoy = { fecha: d, enviados: 0 }; return hoy.enviados; }

async function pausa(ms) {
  envio.pausaHasta = Date.now() + ms;
  while (Date.now() < envio.pausaHasta && !envio.parar) await espera(1e3);
  envio.pausaHasta = 0;
}

async function enviarUno(c) {
  const tel = telNacional(c.telefono);
  if (tel.length !== 9) { if (!c.prueba) avisarRender(c.numMantenimiento, 'sin_whatsapp', 'Teléfono no válido'); return 'sin'; }
  let id = null, consultaOk = false;
  try { id = await client.getNumberId('34' + tel); consultaOk = true; } catch {}
  if (consultaOk && !id) {
    registro[c.numMantenimiento] = { h: [hash(tel)], sentAt: Date.now(), fecha: c.fecha, tramo: c.timeslot, tipo: c.tipo, status: 'sin_whatsapp', prueba: !!c.prueba };
    guardarRegistro();
    if (!c.prueba) avisarRender(c.numMantenimiento, 'sin_whatsapp', 'El número no tiene WhatsApp');
    return 'sin';
  }
  const waId = id ? id._serialized : `34${tel}@c.us`;
  try { const ch = await client.getChatById(waId); await ch.sendStateTyping(); await espera(azar(2e3, 5e3)); await ch.clearState(); }
  catch { await espera(azar(1e3, 2e3)); }
  const texto = mensajePara(c);
  let enviado;
  try { enviado = await client.sendMessage(waId, texto); }
  catch (e) { await espera(3e3); enviado = await client.sendMessage(waId, texto); }

  const h = new Set([hash(tel), hash(waId), hash(`34${tel}@c.us`)]);
  try { const ch = await enviado.getChat(); if (ch && ch.id) h.add(hash(ch.id._serialized)); } catch {}
  registro[c.numMantenimiento] = { h: [...h], sentAt: Date.now(), fecha: c.fecha, tramo: c.timeslot, tipo: c.tipo, status: 'enviado', prueba: !!c.prueba };
  guardarRegistro();
  if (!c.prueba) avisarRender(c.numMantenimiento, 'enviado');
  hoy.enviados++;
  return 'ok';
}

async function bucleEnvio(lista) {
  envio = { activo: true, parar: false, total: lista.length, hechos: 0, fallos: 0, aviso: '', pausaHasta: 0 };
  let seguidos = 0;
  try {
    for (let i = 0; i < lista.length && !envio.parar; i++) {
      if (contarHoy() >= DAILY_LIMIT) { envio.aviso = `Tope diario de ${DAILY_LIMIT} mensajes alcanzado: sigue mañana.`; break; }
      if (wa.estado !== 'conectado') { envio.aviso = 'WhatsApp desconectado: envío parado.'; break; }
      try { const r = await enviarUno(lista[i]); if (r === 'ok') seguidos++; envio.hechos++; }
      catch (e) { envio.fallos++; envio.hechos++; log('Fallo al enviar', lista[i].numMantenimiento, e.message); }
      if (i === lista.length - 1) break;
      if (seguidos && seguidos % LONG_PAUSE_EVERY === 0) await pausa(azar(LONG_PAUSE_MIN, LONG_PAUSE_MAX));
      else if ((i + 1) % BATCH_SIZE === 0) await pausa(BATCH_PAUSE);
      else await pausa(azar(DELAY_MIN, DELAY_MAX));
    }
  } finally { envio.activo = false; envio.pausaHasta = 0; }
}

// ── Mantener el Mac despierto mientras la app esté abierta ──────────────────
if (process.platform === 'darwin') {
  try { spawn('caffeinate', ['-i', '-w', String(process.pid)], { stdio: 'ignore', detached: true }).unref(); } catch {}
} else if (ES_WIN) {
  // Equivalente de caffeinate en Windows: no suspender mientras viva este proceso
  const ps = `Add-Type -Name P -Namespace W -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);';` +
    `while (Get-Process -Id ${process.pid} -ErrorAction SilentlyContinue) { [W.P]::SetThreadExecutionState(0x80000001) | Out-Null; Start-Sleep 50 }`;
  try { spawn('powershell.exe', ['-NoProfile', '-WindowStyle', 'Hidden', '-Command', ps], { stdio: 'ignore', detached: true, windowsHide: true }).unref(); } catch {}
}

// ── API local (solo en este Mac) ────────────────────────────────────────────
const app = express();
app.use(express.json({ limit: '1mb' }));
app.use(express.static(path.join(__dirname, 'public')));

function vista() {
  return citas.map(c => {
    const r = registro[c.numMantenimiento] || {};
    return {
      num: c.numMantenimiento, tecnico: c.tecnico || c.matricula, matricula: c.matricula,
      cliente: c.cliente, telefono: c.telefono, tipo: c.tipo, fecha: c.fecha, tramo: c.timeslot,
      status: (r.status && r.fecha === c.fecha && String(r.tramo) === String(c.timeslot) && (!c.status || ['pendiente', 'enviado'].includes(c.status))) ? r.status : c.status,
      respuesta: c.respuesta || '', hora: r.hora || c.horaRespuesta || '',
      gestionada: !!r.gestionada, porWhatsApp: !!r.sentAt
    };
  });
}

app.get('/api/estado', (req, res) => {
  contarHoy();
  res.json({
    version: VERSION, wa, sesion: config.mat ? { mat: config.mat, nombre: config.nombre || config.mat } : null,
    envio: { ...envio, segundosPausa: envio.pausaHasta ? Math.max(0, Math.round((envio.pausaHasta - Date.now()) / 1e3)) : 0 },
    hoy: hoy.enviados, limite: DAILY_LIMIT, ultimaCarga
  });
});

app.post('/api/login', async (req, res) => {
  const mat = String(req.body.mat || '').trim().toUpperCase(), dni = String(req.body.dni || '').trim().toUpperCase();
  if (!mat || !dni) return res.json({ ok: false, error: 'Escribe matrícula y DNI' });
  try {
    const d = await cargarCitas(mat, dni);
    config = { mat, dni, nombre: d.nombre || mat };
    escribir(F_CONFIG, config);
    res.json({ ok: true, nombre: config.nombre });
  } catch (e) { res.json({ ok: false, error: e.message }); }
});

app.post('/api/salir', (req, res) => { config = {}; citas = []; try { fs.unlinkSync(F_CONFIG); } catch {} res.json({ ok: true }); });

app.get('/api/citas', async (req, res) => {
  if (!config.mat) return res.json({ ok: false, error: 'Entra con tu matrícula y DNI' });
  try {
    if (req.query.recargar === '1' || Date.now() - ultimaCarga > 60e3) await cargarCitas(config.mat, config.dni);
    res.json({ ok: true, citas: vista() });
  } catch (e) { res.json({ ok: citas.length > 0, error: e.message, citas: vista() }); }
});

app.post('/api/enviar', (req, res) => {
  if (wa.estado !== 'conectado') return res.json({ ok: false, error: 'Primero vincula el WhatsApp (QR)' });
  if (envio.activo) return res.json({ ok: false, error: 'Ya hay un envío en curso' });
  const nums = new Set((req.body.nums || []).map(String));
  const lista = citas.filter(c => nums.has(String(c.numMantenimiento)) && !['confirmado', 'no_confirmado'].includes((registro[c.numMantenimiento] || {}).status || c.status));
  if (!lista.length) return res.json({ ok: false, error: 'No hay citas para enviar en la selección' });
  bucleEnvio(barajar(lista));
  res.json({ ok: true, enCola: lista.length });
});

// El JE marca a mano (p. ej. una "otra respuesta" que ha leído)
app.post('/api/marcar', (req, res) => {
  const num = String(req.body.num || ''), status = String(req.body.status || '');
  if (!['confirmado', 'no_confirmado', 'pendiente'].includes(status)) return res.json({ ok: false, error: 'Estado inválido' });
  if (registro[num]) { registro[num].status = status; guardarRegistro(); }
  avisarRender(num, status, status === 'pendiente' ? '' : 'Marcado por el JE');
  const c = citas.find(x => String(x.numMantenimiento) === num); if (c) c.status = status;
  res.json({ ok: true });
});

app.post('/api/parar', (req, res) => { envio.parar = true; res.json({ ok: true }); });

app.post('/api/gestionada', (req, res) => {
  const num = String(req.body.num || '');
  const c = citas.find(x => String(x.numMantenimiento) === num);
  registro[num] = registro[num] || { h: [], sentAt: 0, fecha: c ? c.fecha : '', tramo: c ? c.timeslot : '', tipo: c ? c.tipo : '', status: c ? c.status : '' };
  registro[num].gestionada = !!req.body.valor;
  guardarRegistro();
  res.json({ ok: true });
});

// Prueba: envía el mensaje a un número que escribe el JE (no toca Render).
app.post('/api/prueba', async (req, res) => {
  if (wa.estado !== 'conectado') return res.json({ ok: false, error: 'Primero vincula el WhatsApp (QR)' });
  const tel = telNacional(req.body.telefono);
  if (tel.length !== 9) return res.json({ ok: false, error: 'Teléfono de 9 cifras' });
  const ref = 'PRUEBA-' + Date.now().toString().slice(-6);
  const c = { prueba: true, numMantenimiento: ref, telefono: tel, cliente: req.body.nombre || 'Prueba',
    tipo: req.body.tipo || 'Mantenimiento', fecha: req.body.fecha || new Date(Date.now() + 864e5).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: '2-digit' }), timeslot: req.body.tramo || '09-11' };
  try { const r = await enviarUno(c); res.json({ ok: r === 'ok', ref, error: r === 'sin' ? 'Ese número no tiene WhatsApp' : '' }); }
  catch (e) { res.json({ ok: false, error: e.message }); }
});
app.get('/api/pruebas', (req, res) => {
  res.json(Object.entries(registro).filter(([, r]) => r.prueba).map(([ref, r]) => ({ ref, status: r.status, hora: r.hora || '' })));
});

app.get('/api/plantillas', (req, res) => {
  const p = plantillas();
  // Qué tipos de las citas cargadas caen en cada familia (y cuáles usan el general)
  const reparto = {};
  for (const c of citas) {
    const f = familiaDe(c.tipo, p.porTipo) || '';
    const r = (reparto[f] = reparto[f] || {});
    r[c.tipo] = (r[c.tipo] || 0) + 1;
  }
  res.json({ ...p, reparto });
});
app.post('/api/plantillas', (req, res) => {
  const b = req.body || {};
  const p = { general: String(b.general || PLANTILLAS_DEF.general), porTipo: {}, respuestaSi: String(b.respuestaSi || PLANTILLAS_DEF.respuestaSi), respuestaNo: String(b.respuestaNo || PLANTILLAS_DEF.respuestaNo) };
  for (const [t, v] of Object.entries(b.porTipo || {})) if (String(v).trim()) p.porTipo[t] = String(v);
  escribir(F_PLANTILLAS, p, 0o644);
  res.json({ ok: true });
});
app.post('/api/vista-previa', (req, res) => {
  const c = { cliente: 'María', tipo: req.body.tipo || 'Mantenimiento', fecha: '14/11/26', timeslot: '09-11' };
  res.json({ texto: mensajePara(c) });
});

app.post('/api/reintentar', (req, res) => { if (wa.estado === 'error') arrancarWA(); res.json({ ok: true }); });

app.post('/api/desvincular', async (req, res) => {
  try { await client.logout(); } catch {}
  wa = { estado: 'desconectado', qr: '', numero: '' };
  setTimeout(() => arrancarWA(), 2e3);
  res.json({ ok: true });
});

// Cerrar la app desde la pantalla (la app instalada no tiene ventana propia)
app.post('/api/apagar', async (req, res) => {
  res.json({ ok: true });
  log('Cerrando la app');
  try { await client.destroy(); } catch {}
  setTimeout(() => process.exit(0), 500);
});

function abrirNavegador(url) {
  if (process.env.NO_ABRIR) return;
  const cmd = ES_WIN ? ['cmd', ['/c', 'start', '', url]] : ['open', [url]];
  try { spawn(cmd[0], cmd[1], { stdio: 'ignore', detached: true, windowsHide: true }).unref(); } catch {}
}

process.on('uncaughtException', e => { log('Error inesperado:', e && e.stack || e); diagnostico('excepcion', String(e && e.message || e)); });
process.on('unhandledRejection', e => {
  const m = String(e && e.message || e);
  log('Error sin tratar:', m); diagnostico('rechazo', m);
  // WhatsApp Web recargó la página y no se pudo volver a enganchar: se reconecta
  // Solo si ya estaba vinculado: con el QR en pantalla, reiniciar cambiaría el QR que el JE está escaneando
  if ((wa.estado === 'conectado' || wa.estado === 'conectando') && /auth timeout|ready timeout|Execution context|Target closed|Session closed/i.test(m)) reiniciarWA('tras recarga: ' + m);
});

// ── Vigilante: si WhatsApp se cuelga después de vincular, se reconecta solo ──
// (con la sesión guardada, sin pedir otro QR)
let desdeConectando = 0, fallosVigilancia = 0, reiniciando = false, reconexiones = [];
async function reiniciarWA(motivo) {
  if (reiniciando || arrancando) return;
  // Como mucho 5 reconexiones por hora (si no, se para y se muestra Reintentar)
  reconexiones = reconexiones.filter(t => Date.now() - t < 36e5);
  if (reconexiones.length >= 5) {
    wa = { estado: 'error', qr: '', numero: '', detalle: 'WhatsApp se desconecta una y otra vez. Comprueba la conexión a internet y pulsa Reintentar.' };
    return diagnostico('demasiadas-reconexiones', motivo);
  }
  reconexiones.push(Date.now());
  reiniciando = true;
  log('Reconectando WhatsApp:', motivo); diagnostico('reconexion', motivo);
  wa = { estado: 'iniciando', qr: '', numero: '', detalle: '' };
  try { await client.destroy(); } catch {}
  setTimeout(() => { reiniciando = false; fallosVigilancia = 0; arrancarWA(); }, 5e3);
}
setInterval(async () => {
  if (reiniciando || arrancando) return;
  if (wa.estado === 'conectando' && desdeConectando && Date.now() - desdeConectando > 15 * 60e3) {
    desdeConectando = 0; return reiniciarWA('vinculado pero sin terminar de cargar en 15 min');
  }
  if (wa.estado !== 'conectado') { fallosVigilancia = 0; return; }
  try {
    const st = await Promise.race([client.getState(), new Promise((_, r) => setTimeout(() => r(new Error('sin respuesta')), 20e3))]);
    if (!st) throw new Error('estado vacío');
    fallosVigilancia = 0;
  } catch (e) {
    if (++fallosVigilancia >= 2) reiniciarWA('WhatsApp no responde (' + e.message + ')');
  }
}, 60e3);

const servidor = app.listen(PORT, '127.0.0.1', () => {
  abrirNavegador(`http://localhost:${PORT}`);
  log(`App lista en http://localhost:${PORT}  (datos en ${DATA_DIR})`);
  arrancarWA();
  setTimeout(() => diagnostico('arranque', executablePath || 'sin Chrome', true), 3e3);
  if (config.mat) cargarCitas(config.mat, config.dni).catch(e => log('Carga inicial:', e.message));
});
// Si ya hay una abierta (doble clic otra vez), solo se abre el navegador
// Si la que está abierta es otra versión (p. ej. la anterior), se cierra y arranca esta.
let reintentosPuerto = 0;
servidor.on('error', async e => {
  if (e.code === 'EADDRINUSE') {
    let otra = null;
    try { otra = await (await fetch(`http://127.0.0.1:${PORT}/api/estado`)).json(); } catch {}
    if (otra && otra.version === VERSION) { abrirNavegador(`http://localhost:${PORT}`); setTimeout(() => process.exit(0), 1000); return; }
    if (reintentosPuerto++ >= 5) { log('El puerto sigue ocupado'); abrirNavegador(`http://localhost:${PORT}`); setTimeout(() => process.exit(0), 1000); return; }
    log('Cerrando la versión anterior que estaba abierta');
    try { await fetch(`http://127.0.0.1:${PORT}/api/apagar`, { method: 'POST' }); } catch {}
    setTimeout(() => servidor.listen(PORT, '127.0.0.1'), 4e3);
  }
  else { log('Error del servidor:', e.message); process.exit(1); }
});
