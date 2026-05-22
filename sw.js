/* The Arts Wire — service worker
   Makes the site installable and readable offline. Strategy:
   - App shell (icons, manifest): cache-first.
   - Editions (HTML pages): network-first, fall back to the last cached copy,
     so readers always get today's edition when online and yesterday's when not.
   Bump CACHE_VERSION whenever you want every reader to refresh cached assets. */

const CACHE_VERSION = "arts-wire-v1";
const SHELL = [
  "./",
  "./index.html",
  "./subscribe.html",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) =>
      // addAll fails if any single file 404s, so add them resiliently.
      Promise.allSettled(SHELL.map((url) => cache.add(url)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const isPage = req.mode === "navigate" || req.destination === "document";

  if (isPage) {
    // Network-first for editions: freshest when online, cached when offline,
    // and ALWAYS a valid response (never blank).
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_VERSION).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() =>
          caches.match(req)
            .then((hit) => hit || caches.match("./index.html"))
            .then((r) => r || new Response(
              "<!doctype html><meta charset=utf-8><body style='font-family:Georgia,serif;padding:2rem'>You're offline — reconnect to load the latest edition.</body>",
              { headers: { "Content-Type": "text/html" } }))
        )
    );
  } else {
    // Cache-first for static assets (icons, fonts, etc.).
    event.respondWith(
      caches.match(req).then((hit) =>
        hit ||
        fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(CACHE_VERSION).then((c) => c.put(req, copy));
          return res;
        }).catch(() => hit)
      )
    );
  }
});
