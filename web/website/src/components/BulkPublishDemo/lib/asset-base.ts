/**
 * Resolve the base URL for static assets (extensions, wheel, NDJSON files).
 *
 * In the standalone Vite demo this used `import.meta.env.BASE_URL` so it
 * worked on GitHub Pages subpaths. In the Docusaurus embed the assets live
 * under `static/bulk-publisher-app/` and the site is deployed at the domain
 * root, so we resolve relative to `window.location.origin` to stay correct
 * under whatever path Docusaurus is mounted at.
 */
export function getAssetBase(): string {
  if (typeof window === "undefined") return "/bulk-publisher-app";
  return `${window.location.origin}/bulk-publisher-app`.replace(/\/$/, "");
}
