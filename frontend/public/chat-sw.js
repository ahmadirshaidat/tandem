/* Cache visited chat shell and immutable assets, never authenticated APIs or images. */
const SHELL = "tandem-chat-shell-v1";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));
self.addEventListener("message", event => { if (event.data?.type === "clear-chat-shell") event.waitUntil(caches.delete(SHELL)); });
self.addEventListener("fetch", event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;
  const shell = request.mode === "navigate" && url.pathname === "/channels";
  const immutable = url.pathname.startsWith("/_next/static/");
  if (!shell && !immutable) return;
  event.respondWith((async () => {
    const cache = await caches.open(SHELL);
    try { const response = await fetch(request); if (response.ok) await cache.put(shell ? "/channels" : request, response.clone()); return response; }
    catch (error) { const saved = await cache.match(shell ? "/channels" : request); if (saved) return saved; throw error; }
  })());
});
