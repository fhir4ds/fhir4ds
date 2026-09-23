/**
 * Resolve the base URL for WASM app assets (extensions, data files, etc.).
 *
 * In standalone SPA mode: derived from window.location.href + Vite's BASE_URL.
 * In Web Component mode:  the host page passes wasmAppUrl (computed from the
 *                          bundle's import.meta.url).
 */
export function getAssetBase(wasmAppUrl?: string): string {
  if (wasmAppUrl) return wasmAppUrl.replace(/\/$/, "");
  // Resolve BASE_URL against the current page URL — works on the main
  // thread (window.location) and inside workers (self.location).
  const baseHref: string =
    typeof window !== "undefined"
      ? window.location.href
      : (self as any).location?.href ?? "http://localhost/";
  return new URL(import.meta.env.BASE_URL || "/", baseHref).href.replace(/\/$/, "");
}
