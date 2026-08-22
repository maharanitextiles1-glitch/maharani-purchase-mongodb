const CACHE_NAME = "maharani-purchase-app-v5";

const APP_SHELL = [
  "/",
  "/static/styles.css",
  "/static/script.js",
  "/static/icon-192-v2.png",
  "/static/icon-512-v2.png",
  "/static/apple-touch-icon-v2.png"
];

self.addEventListener("install", event => {
  self.skipWaiting();

  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.allSettled(
        APP_SHELL.map(url =>
          fetch(url, { cache: "reload" })
            .then(response => {
              if (response.ok) return cache.put(url, response);
            })
        )
      )
    )
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys =>
        Promise.all(
          keys
            .filter(key => key !== CACHE_NAME)
            .map(key => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;

  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Database, PDF and API data must always come from the server.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(request));
    return;
  }

  // Always try the network first for the app page and static files.
  // This prevents old CSS, JS and images from remaining after a deployment.
  if (
    request.mode === "navigate" ||
    url.pathname.startsWith("/static/")
  ) {
    event.respondWith(
      fetch(request, { cache: "no-store" })
        .then(response => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          }
          return response;
        })
        .catch(() =>
          caches.match(request).then(cached => cached || caches.match("/"))
        )
    );
    return;
  }

  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});
