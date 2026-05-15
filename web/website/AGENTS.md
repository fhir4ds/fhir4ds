# Website Maintenance (AGENTS.md)

This document provides critical instructions for maintaining the FHIR4DS website, especially the integration with the WASM demo and SharedArrayBuffer isolation.

## WASM Demo Integration

The interactive demo is a standalone React application (`web/wasm-demo`) that is built and copied into `static/wasm-app/` during the deployment process.

### Embedding Logic
- **Legacy demo page**: `web/website/src/components/WasmDemo.tsx` embeds `${baseUrl}/wasm-app/` in an iframe for `/demo`.
- **Examples pages**: `web/website/src/components/WasmDemoWC.tsx` embeds the `<fhir4ds-demo>` web component directly on:
  - `/docs/examples/cql-playground`
  - `/docs/examples/cms-measures`
  - `/docs/examples/sdc-playground`
  - `/docs/examples/smart-demo`
- **Isolation**: Requires `SharedArrayBuffer` for DuckDB-WASM and Pyodide.
- **Current wheel path**: the Vite build serves the Python wheel from `/wasm-app/assets/fhir4ds_v2-*.whl`. Do not reintroduce old `cql_py` path assumptions in tests or docs.

## Cross-Origin Isolation (COOP/COEP)

To enable `SharedArrayBuffer` on GitHub Pages (which doesn't support custom headers by default), we use a service worker.

### COI Service Worker
- **File**: `static/coi-serviceworker.js`
- **Registration**: Managed in `docusaurus.config.ts` via `headTags`.
- **Function**: It intercepts requests and adds the necessary headers:
  - `Cross-Origin-Opener-Policy: same-origin`
  - `Cross-Origin-Embedder-Policy: require-corp`
- **Important**: do not load `coi-serviceworker.js` as a normal script tag. It must be registered with `navigator.serviceWorker.register(...)`. The first document load is not isolated until it is served through the active service worker, so the registration code performs a single reload after activation. Without that reload, examples can render `<fhir4ds-demo>` while DuckDB-WASM fails with `SharedArrayBuffer is unavailable because the page is not cross-origin isolated`.

## Testing Website Examples

The examples can appear superficially healthy if a test only checks that the custom element was injected. A valid examples test must also verify cross-origin isolation and DuckDB initialization.

From `web/website/`:

```bash
npm run build
npm run serve -- --host 127.0.0.1 --port 3001
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001/ npx playwright test tests/wasm-demo-wc.spec.ts tests/demo.spec.ts
```

`tests/wasm-demo-wc.spec.ts` should include a deep initialization check that waits for the `[DuckDB] Ready` console message and asserts `window.crossOriginIsolated === true`. The shallower checks are still useful for Docusaurus integration, but they are not enough to catch SharedArrayBuffer regressions.

## URL Resolution & Sub-paths

The website is hosted at `https://fhir4ds.com/`. When changing domains or deployment sub-paths:

1.  **Docusaurus `baseUrl`**: Must match the domain sub-path.
2.  **WASM Demo `BASE_URL`**: The `web/wasm-demo` build must use the same sub-path prefix (e.g., `/wasm-app/` or just `/` depending on setup).
3.  **Checklist**: See [web/wasm-demo/AGENTS.md](../wasm-demo/AGENTS.md) for more technical details on asset resolution.

## Troubleshooting
If the demo fails to load or shows a `SharedArrayBuffer` error, ensure `coi-serviceworker.js` is loading correctly and the iframe URL matches the actual deployment path of the WASM app.
