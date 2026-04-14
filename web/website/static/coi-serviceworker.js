/**
 * coi-serviceworker — Cross-Origin Isolation polyfill for GitHub Pages
 *
 * GitHub Pages cannot set Cross-Origin-Opener-Policy / Cross-Origin-Embedder-Policy
 * response headers, which are required for SharedArrayBuffer (used by DuckDB-WASM).
 * This service worker intercepts responses and injects the required headers,
 * enabling cross-origin isolation in supported browsers.
 *
 * Based on: https://github.com/gzuidhof/coi-serviceworker
 * License: MIT
 */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", function (event) {
  if (event.request.cache === "only-if-cached" && event.request.mode !== "same-origin") {
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then(function (response) {
        if (response.status === 0) {
          return response;
        }
        const newHeaders = new Headers(response.headers);
        newHeaders.set("Cross-Origin-Opener-Policy", "same-origin");
        newHeaders.set("Cross-Origin-Embedder-Policy", "require-corp");
        newHeaders.set("Cross-Origin-Resource-Policy", "cross-origin");
        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: newHeaders,
        });
      })
      .catch((e) => console.error(e))
  );
});
