/**
 * Resolve the base URL for WASM app assets (extensions, data files, etc.).
 *
 * In standalone SPA mode: derived from window.location.origin + Vite's BASE_URL.
 * In Web Component mode:  the host page passes wasmAppUrl (computed from the
 *                          bundle's import.meta.url).
 */
export function getAssetBase(wasmAppUrl?: string): string {
  if (wasmAppUrl) return wasmAppUrl.replace(/\/$/, "");
  return (window.location.origin + import.meta.env.BASE_URL).replace(/\/$/, "");
}
