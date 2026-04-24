/**
 * Resolve the base URL for WASM app assets (extensions, data files, etc.).
 *
 * In standalone SPA mode: derived from window.location.href + Vite's BASE_URL.
 * In Web Component mode:  the host page passes wasmAppUrl (computed from the
 *                          bundle's import.meta.url).
 */
export function getAssetBase(wasmAppUrl?: string): string {
  if (wasmAppUrl) return wasmAppUrl.replace(/\/$/, "");
  // Use URL constructor to resolve BASE_URL against the current page URL.
  // This handles empty (''), relative ('./'), and absolute ('/') base paths
  // without accidental string concatenation (e.g. origin + './' = 'http://host./').
  return new URL(import.meta.env.BASE_URL || "/", window.location.href).href.replace(/\/$/, "");
}
