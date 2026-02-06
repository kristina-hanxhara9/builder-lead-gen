// Service worker for Smith & Sons Lead Generation PWA
// Currently a no-op — add caching strategies here for offline support

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Pass through all requests to the network
  return;
});
