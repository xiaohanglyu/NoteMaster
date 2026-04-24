const CACHE = "notemaster-v1";
const STATIC = ["/", "/manifest.json"];

self.addEventListener("install", e =>
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)))
);

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  if (new URL(e.request.url).pathname.startsWith("/stats") ||
      new URL(e.request.url).pathname.startsWith("/session") ||
      new URL(e.request.url).pathname.startsWith("/answer") ||
      new URL(e.request.url).pathname.startsWith("/sync")) return;
  // index.html: network first so code changes are always picked up immediately
  const url = new URL(e.request.url);
  if (url.pathname === "/" || url.pathname === "/index.html") {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
