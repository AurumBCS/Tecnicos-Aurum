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
// Las altas se guardan en push_altas.json (disco de Render: se pierde al redesplegar). Por eso la app
// vuelve a mandar su alta cada vez que se abre, y la lista se rehace sola.
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
    return true;
  } catch (e) {
    return false;
  }
}
ponerClavePrivada(process.env.VAPID_PRIVATE || (leer(F_VAPID, {}) || {}).priv);

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
    guardar(F_ALTAS, altas);
  }
  return ok;
}

function montar(app, { verificarDNI, registrarUso }) {
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
    Object.keys(altas).forEach(m => {
      altas[m] = altas[m].filter(s => s.endpoint !== sub.endpoint);
      if (!altas[m].length) delete altas[m];
    });
    (altas[mat] = altas[mat] || []).push({ endpoint: sub.endpoint, keys: { p256dh: sub.keys.p256dh, auth: sub.keys.auth },
      ua: String(req.body.ua || '').slice(0, 40), alta: new Date().toISOString() });
    altas[mat] = altas[mat].slice(-5);
    guardar(F_ALTAS, altas);
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
