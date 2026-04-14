# Website Maintenance (AGENTS.md)

This document provides critical instructions for maintaining the FHIR4DS website, especially the integration with the WASM demo and SharedArrayBuffer isolation.

## WASM Demo Integration

The interactive demo is a standalone React application (`web/wasm-demo`) that is built and copied into `static/wasm-app/` during the deployment process.

### Embedding Logic
- **Component**: `web/website/src/components/WasmDemo.tsx`
- **Iframe URL**: `${baseUrl}/wasm-app/`
- **Isolation**: Requires `SharedArrayBuffer` for DuckDB-WASM and Pyodide.

## Cross-Origin Isolation (COOP/COEP)

To enable `SharedArrayBuffer` on GitHub Pages (which doesn't support custom headers by default), we use a service worker.

### COI Service Worker
- **File**: `static/coi-serviceworker.js`
- **Registration**: Managed in `docusaurus.config.ts` via `headTags`.
- **Function**: It intercepts requests and adds the necessary headers:
  - `Cross-Origin-Opener-Policy: same-origin`
  - `Cross-Origin-Embedder-Policy: require-corp`

## URL Resolution & Sub-paths

The website is hosted at `https://fhir4ds.com/`. When changing domains or deployment sub-paths:

1.  **Docusaurus `baseUrl`**: Must match the domain sub-path.
2.  **WASM Demo `BASE_URL`**: The `web/wasm-demo` build must use the same sub-path prefix (e.g., `/wasm-app/` or just `/` depending on setup).
3.  **Checklist**: See [web/wasm-demo/AGENTS.md](../wasm-demo/AGENTS.md) for more technical details on asset resolution.

## Troubleshooting
If the demo fails to load or shows a `SharedArrayBuffer` error, ensure `coi-serviceworker.js` is loading correctly and the iframe URL matches the actual deployment path of the WASM app.
