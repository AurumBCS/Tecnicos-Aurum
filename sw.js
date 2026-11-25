// ── Service Worker · Aurum BC Security ──
const VERSION = 'v20261125a';
const CACHE   = 'aurum-' + VERSION;

// Al instalar: guarda el HTML en caché
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => cache.add('index.html'))
  );
  self.skipWaiting();
});

// Al activar: elimina cachés antiguas
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Estrategia: Network First → si hay red trae la versión nueva,
// si no hay red usa la caché (modo offline)
self.addEventListener('fetch', e => {
  if(e.request.method !== 'GET') return;
  // Solo cachear el propio HTML de la app, no las llamadas al Apps Script
  const url = new URL(e.request.url);
  const isAppShell = url.pathname.endsWith('index.html') || url.pathname.endsWith('/') || url.pathname.endsWith('/Tecnicos-Aurum/');

  if(!isAppShell) return; // dejar pasar sin interceptar

  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(cache => cache.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

// ── Avisos push (17/11/2026): RM al empezar un mantenimiento (técnico) y citas fuera de hora (JE).
// Los manda el servidor de Render (confirmaciones-sms/push.js) aunque la app esté cerrada.
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { cuerpo: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.titulo || 'Aurum', {
    body: d.cuerpo || '',
    tag: d.tag || undefined,
    renotify: !!d.tag,
    icon: 'icon-192.png',
    badge: 'icon-192.png',
    data: { url: d.url || './' }
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const destino = new URL((e.notification.data && e.notification.data.url) || './', self.registration.scope).href;
  e.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(ws => {
    const abierta = ws.find(w => w.url.startsWith(self.registration.scope));
    if (abierta) return abierta.focus();
    return clients.openWindow(destino);
  }));
});
