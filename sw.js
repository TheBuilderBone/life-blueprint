// Life Blueprint Service Worker v2.0
// Handles: offline caching, push notifications, background sync

const CACHE_NAME = 'blueprint-v2';
const ASSETS = [
  '/life-blueprint/',
  '/life-blueprint/index.html',
  '/life-blueprint/manifest.json',
  'https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Barlow+Condensed:wght@400;600;700;800&family=Barlow:wght@300;400;500;600&display=swap'
];

// ============================================================
// INSTALL — cache core assets
// ============================================================
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(ASSETS).catch(err => {
        console.log('Cache addAll failed for some assets:', err);
      });
    })
  );
  self.skipWaiting();
});

// ============================================================
// ACTIVATE — clean old caches
// ============================================================
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ============================================================
// FETCH — serve from cache, fallback to network
// ============================================================
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  if (event.request.url.startsWith('chrome-extension')) return;

  const isHTML = event.request.destination === 'document' || event.request.url.endsWith('.html') || event.request.url.endsWith('/');

  // Network first for HTML — always gets latest version on refresh
  // Cache first for everything else — fonts, icons etc
  if (isHTML) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  } else {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          }
          return response;
        }).catch(() => caches.match('/life-blueprint/index.html'));
      })
    );
  }
});

// ============================================================
// PUSH NOTIFICATIONS
// ============================================================
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'Life Blueprint';
  const options = {
    body: data.body || 'Time to check in.',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: data.tag || 'blueprint-notification',
    renotify: true,
    requireInteraction: data.requireInteraction || false,
    data: { url: data.url || '/' },
    actions: data.actions || []
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.focus();
          client.postMessage({ type: 'NAVIGATE', tab: url.replace('/?tab=', '') });
          return;
        }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});

// ============================================================
// SCHEDULED NOTIFICATIONS (via periodic background sync if supported)
// Fallback: app checks on open and fires missed notifications
// ============================================================
self.addEventListener('periodicsync', event => {
  if (event.tag === 'daily-check') {
    event.waitUntil(checkScheduledNotifications());
  }
});

async function checkScheduledNotifications() {
  const now = new Date();
  const hour = now.getHours();
  const day = now.getDay(); // 0=Sun, 1=Mon...

  // Morning check-in: 6:00 AM daily
  if (hour === 6) {
    await self.registration.showNotification('Good morning.', {
      body: 'Set your priority for today. What\'s the one thing that makes today a win?',
      icon: '/icon-192.png',
      tag: 'morning-checkin',
      data: { url: '/?tab=checkin' }
    });
  }

  // Evening close: 9:30 PM daily
  if (hour === 21) {
    await self.registration.showNotification('Close the day.', {
      body: 'Log your win and one thing to improve tomorrow. Takes 60 seconds.',
      icon: '/icon-192.png',
      tag: 'evening-checkin',
      data: { url: '/?tab=checkin' }
    });
  }

  // Wednesday house day: 8:45 AM
  if (day === 3 && hour === 8) {
    await self.registration.showNotification('Wednesday — Progress Day.', {
      body: 'House block starts at 9 AM. This is your highest-ROI day of the week.',
      icon: '/icon-192.png',
      tag: 'wednesday',
      data: { url: '/?tab=house' }
    });
  }

  // Sunday weekly plan: 7:00 PM
  if (day === 0 && hour === 19) {
    await self.registration.showNotification('Set your week.', {
      body: 'What are your 3 intentions for this week? Takes 2 minutes.',
      icon: '/icon-192.png',
      tag: 'weekly-plan',
      data: { url: '/?tab=weekly' }
    });
  }
}
