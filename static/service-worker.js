const EDA_CACHE_VERSION = "easy-dune-admin-0.8.3-alpha";

// Cache only static app-shell assets. Authenticated pages and API responses
// stay network-first so sensitive admin data is not intentionally stored for
// offline viewing on phones or shared browsers.
const EDA_STATIC_ASSETS = [
    "/static/offline.html",
    "/static/site.webmanifest",
    "/static/favicon.ico",
    "/static/favicon-32.png",
    "/static/favicon-192.png",
    "/static/apple-touch-icon.png",
    "/static/dune-admin.js",
    "/static/dune-admin.png"
];

self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(EDA_CACHE_VERSION)
            .then(cache => cache.addAll(EDA_STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", event => {
    event.waitUntil(
        caches.keys()
            .then(keys => Promise.all(
                keys
                    .filter(key => key.startsWith("easy-dune-admin-") && key !== EDA_CACHE_VERSION)
                    .map(key => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", event => {
    const request = event.request;
    const url = new URL(request.url);

    if (request.method !== "GET" || url.origin !== self.location.origin) {
        return;
    }

    if (url.pathname.startsWith("/api/")) {
        event.respondWith(fetch(request));
        return;
    }

    if (request.mode === "navigate") {
        event.respondWith(
            fetch(request).catch(() => caches.match("/static/offline.html"))
        );
        return;
    }

    if (url.pathname.startsWith("/static/")) {
        event.respondWith(
            caches.match(request).then(cached => cached || fetch(request))
        );
    }
});
