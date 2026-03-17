const CACHE = 'blueprint-v2';
const SHELL = ['./index.html', './manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.mode === 'navigate') {
    // Network-first for navigation: always fetch fresh index.html from GitHub Pages.
    // If the network returns a 404 (e.g. direct URL visit) or is offline,
    // fall back to the cached index.html so the app still loads.
    e.respondWith(
      fetch(e.request)
        .then(res => {
          if (res.ok) return res;
          return caches.match('./index.html').then(cached => cached || res);
        })
        .catch(() => caches.match('./index.html'))
    );
    return;
  }
  // All other requests (JS, CSS, fonts, API calls) — cache-first, fall back to network
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
