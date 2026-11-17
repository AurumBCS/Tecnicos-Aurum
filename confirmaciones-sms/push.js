// ── Avisos push (17/11/2026) ─────────────────────────────────────────────────
// Notificaciones al móvil o al ordenador de técnicos y JE, aunque la app esté cerrada:
//  - al técnico, cuando empieza en Oracle un mantenimiento con sugerencias de RM;
//  - al JE, cuando una cita de su equipo está en riesgo de salirse de la franja o ya se ha salido.
// Los decide la Lambda (agenda_vivo.py, cada 20 min) y los manda aquí; este módulo solo guarda a qué
// navegadores va cada matrícula y entrega cada aviso una vez.
//
// Claves: VAPID_PUBLICA va en el código (es pública). La privada no está en el repositorio ni en Render:
// se deriva de RECUENTOS_KEY (sha256("aurum-vapid|" + clave)) y la manda la Lambda en cada pasada;
// aquí se comprueba que corresponde a VAPID_PUBLICA y se guarda en push_vapid.json. Tras un redespliegue,
// los avisos vuelven a funcionar con la siguiente pasada de la Lambda (cada 20 min, L-V de 8 a 19).
// La Lambda se identifica con RECUENTOS_KEY; aquí solo está su huella SHA-256.
//
// Las altas se guardan en push_altas.json (disco de Render: se pierde al redesplegar y cuando Render se
// duerme por la noche). Por eso también se anotan, cifradas, en la pestaña "Uso" de la hoja de
// confirmaciones (filas con mat "~PUSH", que no cuentan como uso) y se recuperan de ahí en cuanto el
// servidor tiene la clave privada (18/11/2026). Además la app renueva su alta al abrirse y al volver a ella.
// Sin datos de clientes: los avisos llevan número de mantenimiento, tipo, franja y nombre del técnico.

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const VAPID_PUBLICA = 'BL0AMLqEJffGoZQFTobM9t_Rm05pBX8JuzQGP5R0BlT2usBXF6JAd6s9dgSBSW_P0JGPkDSE2jYBbBwFAXGWtiU';
const HUELLA_CLAVE_LAMBDA = '852949f987c32da79da727136c10f3ed86ad270b11b0c17dd77098b271848f9b';
const F_ALTAS = path.join(__dirname, 'push_altas.json');
const F_ENVIADOS = path.join(__dirname, 'push_enviados.json');
const F_VAPID = path.join(__dirname, 'push_vapid.json');
const ORIGENES = ['https://aurumbcs.github.io'];

const leer = (f, def) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) { return def; } };
const guardar = (f, v) => { try { fs.writeFileSync(f, JSON.stringify(v), { mode: 0o600 }); } catch (e) { console.error('[push]', e.message); } };

let libreria = null;
try { libreria = require('web-push'); } catch (e) { console.error('[push] falta web-push'); }
let webpush = null;   // la librería, solo cuando ya tiene la clave privada

// True si la clave privada corresponde a VAPID_PUBLICA; entonces quedan activados los avisos
function ponerClavePrivada(priv) {
  if (!libreria || typeof priv !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(priv)) return false;
  try {
    const ecdh = crypto.createECDH('prime256v1');
    ecdh.setPrivateKey(Buffer.from(priv, 'base64url'));
    if (ecdh.getPublicKey().toString('base64url') !== VAPID_PUBLICA) return false;
    libreria.setVapidDetails('mailto:avisos@aurumbcs.com', VAPID_PUBLICA, priv);
    webpush = libreria;
    clavePriv = priv;
    return true;
  } catch (e) {
    return false;
  }
}
let clavePriv = '';

// { MATRICULA: [ {endpoint, keys, ua, alta} ] }
let altas = leer(F_ALTAS, {});
// { dia: 'AAAA-MM-DD', ids: { 'MAT|id': hora } }
let enviados = leer(F_ENVIADOS, { dia: '', ids: {} });

const hoyMadrid = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Madrid' });
const huella = t => crypto.createHash('sha256').update(String(t || '')).digest('hex');
const igualSeguro = (a, b) => a.length === b.length && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));

function cors(req, res) {
  const o = req.headers.origin;
  if (ORIGENES.includes(o) || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(o || '')) {
    res.set('Access-Control-Allow-Origin', o);
    res.set('Vary', 'Origin');
    res.set('Access-Control-Allow-Headers', 'Content-Type');
    res.set('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
  }
}

// Quien entra en la app con contraseña fija (AUTH_FIJAS / AUTH_HASH de index.html, p. ej. GD5381 o César)
// no la tiene en el cuadrante, que es lo que mira verificarDNI. Se comprueba también contra la app
// publicada, leída de GitHub Pages cada 15 min: así no se copia ninguna contraseña aquí (17/11/2026).
const URL_APP = 'https://aurumbcs.github.io/Tecnicos-Aurum/index.html';
let fijasApp = { t: 0, fijas: {}, hash: {} };
async function claveFijaApp(mat, dni) {
  if (Date.now() - fijasApp.t > 15 * 60e3) {
    try {
      const html = await (await fetch(URL_APP + '?_=' + Date.now())).text();
      const objeto = nombre => {
        const m = html.match(new RegExp('const ' + nombre + '\\s*=\\s*\\{([\\s\\S]*?)\\};'));
        const out = {};
        if (m) for (const x of m[1].matchAll(/['"]?([A-Za-z0-9._-]+)['"]?\s*:\s*['"]([^'"]+)['"]/g)) out[x[1].toUpperCase()] = x[2];
        return out;
      };
      fijasApp = { t: Date.now(), fijas: objeto('AUTH_FIJAS'), hash: objeto('AUTH_HASH') };
    } catch (e) {
      console.error('[push] no se pudo leer la app para las contraseñas fijas:', e.message);
    }
  }
  const d = String(dni || '').trim().toUpperCase();
  if (!mat || !d) return false;
  if (fijasApp.fijas[mat] && String(fijasApp.fijas[mat]).trim().toUpperCase() === d) return true;
  return !!fijasApp.hash[mat] && huella(d) === String(fijasApp.hash[mat]).toLowerCase();
}

// ── Copia de las altas en la hoja (pestaña Uso) ──────────────────────────────
// sub:<cifrado> = alta { m, e, k, u, a }   ·   baja:<sha256 del endpoint> = baja
// Cifrado AES-256-GCM con una clave derivada de la clave privada VAPID (la hoja se puede leer con la URL).
const MAT_HOJA = '~PUSH';
let hoja = { registrar: null, leer: null };
let enHoja = {};          // endpoint -> 'MAT|p256dh' tal como está anotado en la hoja
let pendientesHoja = [];  // anotaciones hechas antes de tener la clave
let restaurada = null;    // promesa de la recuperación (una vez por arranque)
let hojaLista = false;    // true cuando ya se leyó la hoja
const claveHoja = () => crypto.createHash('sha256').update('aurum-push-altas|' + clavePriv).digest();
function cifrar(obj) {
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv('aes-256-gcm', claveHoja(), iv);
  const ct = Buffer.concat([c.update(JSON.stringify(obj), 'utf8'), c.final()]);
  return Buffer.concat([iv, c.getAuthTag(), ct]).toString('base64url');
}
function descifrar(t) {
  try {
    const b = Buffer.from(t, 'base64url');
    const d = crypto.createDecipheriv('aes-256-gcm', claveHoja(), b.subarray(0, 12));
    d.setAuthTag(b.subarray(12, 28));
    return JSON.parse(Buffer.concat([d.update(b.subarray(28)), d.final()]).toString('utf8'));
  } catch (e) { return null; }
}
function anotarEnHoja(tipo, mat, s) {
  if (!hoja.registrar) return;
  if (!clavePriv || !hojaLista) { pendientesHoja.push([tipo, mat, s]); return; }
  if (tipo === 'sub') {
    const marca = mat + '|' + s.keys.p256dh;
    if (enHoja[s.endpoint] === marca) return;
    enHoja[s.endpoint] = marca;
    hoja.registrar(MAT_HOJA, 'push-sub', 'sub:' + cifrar({ m: mat, e: s.endpoint, k: s.keys, u: s.ua, a: s.alta }));
  } else {
    if (!enHoja[s.endpoint]) return;
    delete enHoja[s.endpoint];
    hoja.registrar(MAT_HOJA, 'push-sub', 'baja:' + huella(s.endpoint));
  }
}
function quitarEndpoint(endpoint) {
  Object.keys(altas).forEach(m => {
    altas[m] = altas[m].filter(s => s.endpoint !== endpoint);
    if (!altas[m].length) delete altas[m];
  });
}
// Rehace las altas desde la hoja; las que ya hay en memoria (más recientes) mandan
function restaurarDeHoja() {
  if (restaurada || !clavePriv || !hoja.leer) return restaurada || Promise.resolve();
  restaurada = (async () => {
    try {
      const desde = new Date(Date.now() - 120 * 864e5).toISOString().slice(0, 10);
      const eventos = (await hoja.leer(desde)).filter(e => e.mat === MAT_HOJA && e.rol === 'push-sub');
      const porEndpoint = {};   // endpoint -> { mat, sub }
      for (const ev of eventos) {
        const a = String(ev.accion || '');
        if (a.startsWith('sub:')) {
          const o = descifrar(a.slice(4));
          if (o && o.m && validaAlta({ endpoint: o.e, keys: o.k })) porEndpoint[o.e] = { mat: o.m, sub: { endpoint: o.e, keys: o.k, ua: o.u || '', alta: o.a || '' } };
        } else if (a.startsWith('baja:')) {
          const h = a.slice(5);
          Object.keys(porEndpoint).forEach(e => { if (huella(e) === h) delete porEndpoint[e]; });
        }
      }
      let recuperadas = 0;
      const enMemoria = new Set(Object.values(altas).flat().map(s => s.endpoint));
      for (const [e, { mat, sub }] of Object.entries(porEndpoint)) {
        enHoja[e] = mat + '|' + sub.keys.p256dh;
        if (enMemoria.has(e)) continue;
        (altas[mat] = altas[mat] || []).push(sub);
        altas[mat] = altas[mat].slice(-5);
        recuperadas++;
      }
      guardar(F_ALTAS, altas);
      console.log(`[push] altas recuperadas de la hoja: ${recuperadas} (en total ${Object.keys(altas).length} personas)`);
    } catch (e) {
      console.error('[push] no se pudieron recuperar las altas de la hoja:', e.message);
    }
    hojaLista = true;
    const p = pendientesHoja; pendientesHoja = [];
    p.forEach(x => anotarEnHoja(...x));
  })();
  return restaurada;
}

function validaAlta(s) {
  return s && typeof s.endpoint === 'string' && /^https:\/\//.test(s.endpoint) && s.endpoint.length < 1000
    && s.keys && typeof s.keys.p256dh === 'string' && typeof s.keys.auth === 'string';
}

async function enviarA(mat, aviso) {
  const lista = altas[mat] || [];
  let ok = 0;
  const muertas = [];
  for (const s of lista) {
    try {
      await webpush.sendNotification({ endpoint: s.endpoint, keys: s.keys }, JSON.stringify(aviso), { TTL: 3600, urgency: 'high' });
      ok++;
    } catch (e) {
      // 404/410: el navegador dio de baja la suscripción (permiso quitado, app desinstalada)
      if (e.statusCode === 404 || e.statusCode === 410) muertas.push(s.endpoint);
      else console.error('[push] envío a', mat, 'falló:', e.statusCode || e.message);
    }
  }
  if (muertas.length) {
    altas[mat] = lista.filter(s => !muertas.includes(s.endpoint));
    if (!altas[mat].length) delete altas[mat];
    muertas.forEach(endpoint => anotarEnHoja('baja', mat, { endpoint }));
    guardar(F_ALTAS, altas);
  }
  return ok;
}

function montar(app, { verificarDNI: dniCuadrante, registrarUso, leerUso }) {
  hoja = { registrar: registrarUso, leer: leerUso };
  if (ponerClavePrivada(process.env.VAPID_PRIVATE || (leer(F_VAPID, {}) || {}).priv)) restaurarDeHoja();
  const verificarDNI = async (mat, dni) => (await dniCuadrante(mat, dni)) || claveFijaApp(String(mat || '').toUpperCase(), dni);

  app.options('/push/*', (req, res) => { cors(req, res); res.sendStatus(204); });

  app.get('/push/clave', (req, res) => {
    cors(req, res);
    res.json({ ok: true, activo: !!webpush, clave: VAPID_PUBLICA });
  });

  // La app manda su alta al activar los avisos y cada vez que se abre: { mat, dni, sub }
  app.post('/push/alta', async (req, res) => {
    cors(req, res);
    const mat = String(req.body.mat || '').trim().toUpperCase();
    const sub = req.body.sub;
    if (!(await verificarDNI(mat, req.body.dni))) return res.json({ ok: false, error: 'Matrícula o DNI incorrectos' });
    if (!validaAlta(sub)) return res.json({ ok: false, error: 'Alta no válida' });
    // Un navegador solo puede estar a nombre de una persona (el último que entró en ese móvil)
    quitarEndpoint(sub.endpoint);
    const nueva = { endpoint: sub.endpoint, keys: { p256dh: sub.keys.p256dh, auth: sub.keys.auth },
      ua: String(req.body.ua || '').slice(0, 40), alta: new Date().toISOString() };
    (altas[mat] = altas[mat] || []).push(nueva);
    altas[mat] = altas[mat].slice(-5);
    guardar(F_ALTAS, altas);
    anotarEnHoja('sub', mat, nueva);
    if (req.body.primera) registrarUso(mat, 'push', 'alta-avisos');
    res.json({ ok: true, activo: !!webpush, aparatos: altas[mat].length });
  });

  app.post('/push/baja', async (req, res) => {
    cors(req, res);
    const mat = String(req.body.mat || '').trim().toUpperCase();
    const endpoint = String((req.body.sub && req.body.sub.endpoint) || '');
    if (!(await verificarDNI(mat, req.body.dni))) return res.json({ ok: false, error: 'Matrícula o DNI incorrectos' });
    if (altas[mat]) {
      altas[mat] = altas[mat].filter(s => s.endpoint !== endpoint);
      if (!altas[mat].length) delete altas[mat];
      guardar(F_ALTAS, altas);
    }
    if (endpoint) anotarEnHoja('baja', mat, { endpoint });
    res.json({ ok: true });
  });

  // Botón "Probar aviso" de la app: se lo manda a sí mismo
  app.post('/push/prueba', async (req, res) => {
    cors(req, res);
    const mat = String(req.body.mat || '').trim().toUpperCase();
    if (!(await verificarDNI(mat, req.body.dni))) return res.json({ ok: false, error: 'Matrícula o DNI incorrectos' });
    if (!webpush) return res.json({ ok: false, error: 'Los avisos aún no están activados en el servidor' });
    const n = await enviarA(mat, { titulo: '🔔 Aviso de prueba', cuerpo: 'Los avisos de Aurum funcionan en este aparato.', tag: 'prueba' });
    res.json({ ok: n > 0, aparatos: n, error: n ? '' : 'No hay ningún aparato con los avisos activados' });
  });

  // La Lambda: { key, avisos: [{ mat, id, titulo, cuerpo, url }] }. Cada (mat, id) se entrega una vez al día.
  app.post('/push/avisos', async (req, res) => {
    if (!igualSeguro(huella(req.body.key), HUELLA_CLAVE_LAMBDA)) return res.status(403).json({ ok: false, error: 'No autorizado' });
    if (!webpush) {
      if (!ponerClavePrivada(req.body.vapid)) return res.json({ ok: false, error: 'Clave de avisos no válida' });
      guardar(F_VAPID, { priv: req.body.vapid });
    }
    await restaurarDeHoja();
    const hoy = hoyMadrid();
    if (enviados.dia !== hoy) enviados = { dia: hoy, ids: {} };
    const avisos = Array.isArray(req.body.avisos) ? req.body.avisos.slice(0, 2000) : [];
    let entregados = 0, sinAparato = 0, repetidos = 0;
    for (const a of avisos) {
      const mat = String(a.mat || '').trim().toUpperCase();
      const clave = mat + '|' + String(a.id || '');
      if (!mat || !a.id) continue;
      if (enviados.ids[clave]) { repetidos++; continue; }
      if (!altas[mat]) { sinAparato++; continue; }
      const n = await enviarA(mat, {
        titulo: String(a.titulo || '').slice(0, 80), cuerpo: String(a.cuerpo || '').slice(0, 300),
        url: String(a.url || ''), tag: String(a.id).slice(0, 60)
      });
      if (n) { enviados.ids[clave] = new Date().toISOString().slice(11, 16); entregados++; }
    }
    guardar(F_ENVIADOS, enviados);
    res.json({ ok: true, recibidos: avisos.length, entregados, sinAparato, repetidos, conAvisos: Object.keys(altas).length });
  });
}

module.exports = { montar };
