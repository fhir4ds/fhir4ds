/**
 * Default-example handoff — host-declared initial content.
 *
 * Precedence: host web-component attr > ?example= URL param >
 * "cms125-workspace" (the S33 standalone fresh-boot default, set at the
 * App call site). Share fragments and saved non-pristine workspaces take
 * precedence everywhere. E2e specs that contract on the CleanroomDemo
 * scratch library boot with ?example=demo-workspace.
 */

let pendingDefaultExample: string | null = null;

export function setPendingDefaultExample(example: string | null): void {
  pendingDefaultExample = example;
}

/** Consume the host-declared default example (read once at restore). */
export function takePendingDefaultExample(): string | null {
  const v = pendingDefaultExample;
  pendingDefaultExample = null;
  return v;
}

/** URL ?example= spelling for the standalone app (null when absent). */
export function urlDefaultExample(): string | null {
  if (typeof window === "undefined") return null;
  const v = new URLSearchParams(window.location.search).get("example");
  return v && /^[a-z0-9-]+$/i.test(v) ? v : null;
}

/**
 * Absolute base URL for the app bundle's static assets (examples/, the
 * wheel, wasm extensions). Derived from THIS module's URL — it ships in
 * the same bundle as the app, so its import.meta.url base matches the
 * served asset root in every deployment shape:
 *
 *   Standalone SPA:  https://host/               -> module at /assets/App-*.js
 *   Website embed:   https://host/cql-cleanroom/ -> module at /cql-cleanroom/assets/*.js
 *
 * loadExample must resolve `examples/<ex>/...` against THIS base, never
 * document.baseURI: inside the website the document is a docs page
 * (/docs/examples/cql-cleanroom/), so relative fetches 404 into the SPA
 * HTML fallback and r.json() dies on the DOCTYPE.
 */
export function exampleAssetUrl(path: string): string {
  // The module ships in the bundle's assets/ directory (e.g.
  // /cql-cleanroom/assets/App-*.js); static siblings like examples/ and
  // the wheel live ONE LEVEL UP. Vite dev serves modules from /src
  // instead, where assets sit at the site root.
  const parsed = new URL("../", import.meta.url);
  if (parsed.pathname.includes("/src/")) {
    const root = new URL("/", parsed);
    return new URL(path, root).href;
  }
  return new URL(path, parsed).href;
}
