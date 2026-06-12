// ── Service Worker · Aurum BC Security ──
const VERSION = 'v20260612';
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
