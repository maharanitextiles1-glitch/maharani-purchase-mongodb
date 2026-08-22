
const CACHE_NAME = "maharani-purchase-app-v8";
const APP_SHELL = [
  "/",
  "/static/styles.css",
  "/static/script.js",
  "/static/maharani-logo-v4.png",
  "/static/icon-192-v4.png",
  "/static/icon-512-v4.png",
  "/static/apple-touch-icon-v4.png",
  "/static/favicon-v4.png"
];

self.addEventListener("install", event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.allSettled(APP_SHELL.map(url => cache.add(url)))
    )
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // Never cache API/database/PDF requests. Always use current server data.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(req));
    return;
  }

  // Network-first for HTML and JS/CSS so deployments update quickly.
  if (req.mode === "navigate" ||
      url.pathname.endsWith(".js") ||
      url.pathname.endsWith(".css")) {
    event.respondWith(
      fetch(req)
        .then(response => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, copy));
          return response;
        })
        .catch(() => caches.match(req).then(r => r || caches.match("/")))
    );
    return;
  }

  // Cache-first for icons/static images.
  event.respondWith(
    caches.match(req).then(cached =>
      cached || fetch(req).then(response => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(req, copy));
        return response;
      })
    )
  );
});
