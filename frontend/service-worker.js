const CACHE_NAME = 'awaaz-khata-shell-v1';
const APP_SHELL = [
  '/',
  '/login',
  '/register',
  '/dashboard',
  '/settings',
  '/offline.html',
  '/frontend/styles.css',
  '/frontend/app.js',
  '/frontend/auth-page.js',
  '/frontend/landing.js',
  '/frontend/settings-page.js',
  '/frontend/entries.js',
  '/frontend/effects.js',
  '/frontend/ledger.js',
  '/frontend/mic-visualizer.js',
  '/frontend/pwa.js',
  '/frontend/manifest.webmanifest',
  '/frontend/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)),
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
    )),
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname === '/voice'
    || url.pathname === '/confirm' || url.pathname.startsWith('/export/')
    || url.pathname === '/ledger' || url.pathname.startsWith('/customer/')
    || url.pathname.startsWith('/remind/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      }).catch(async () => (
        await caches.match(request)
        || await caches.match('/offline.html')
      )),
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
      }
      return response;
    })),
  );
});
