self.addEventListener('install', e => {
  e.waitUntil(
    caches.open('wealth-pro-cache').then(cache => {
      return cache.addAll([
        '/',
        '/?source=pwa'
      ]);
    })
  );
});

self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(response => {
      return response || fetch(e.request);
    })
  );
});
