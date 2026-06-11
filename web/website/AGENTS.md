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
- **SMART demo eager load**: `docs/examples/smart-demo.md` intentionally does not pass `lazyLaunch` to `WasmDemoWC`. The SMART example should render the web component directly, and `tests/wasm-demo-wc.spec.ts` should protect that behavior.
- **Release version assets**: when the Python package version changes, update
  the homepage `PRODUCT_VERSION`, `tests/demo.spec.ts`, install snippets,
  `docs/getting-started/releases.md`, and the bundled WASM wheel under
  `web/wasm-demo/public/`; rebuild `web/wasm-demo`, copy `dist/` into
  `static/wasm-app/`, then run `npm run typecheck` and `npm run build` here.
- **Pyodide install snippets**: examples that install the bundled wheel in
  Pyodide must load Pyodide-hosted packages such as `duckdb`, `orjson`, and
  `pyarrow`, install pure-Python dependencies first, and call
  `micropip.install(..., deps=False)` for the fhir4ds wheel. Without
  `deps=False`, micropip tries to install the native `duckdb` Python package
  and fails in browser environments.

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

The website tests prove that the embedded WASM app loads, but they do not
exercise every translated SQL path. When the CQL WASM extension changes, also
run `web/wasm-demo/tests/e2e/cms-measures.spec.ts`; quality-measure examples can
fail from missing CQL UDF registrations even when the website shell and CQL
playground examples pass.

Playwright must serve and test the same origin. `PLAYWRIGHT_BASE_URL` controls
both `use.baseURL` and the `webServer` host/port in `playwright.config.ts`;
when port 3000 is already occupied, run with an alternate URL such as
`PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001/ npm run test:e2e`. Do not let
`reuseExistingServer` point tests at an unrelated local app.

SMART OAuth popup callbacks must not rely solely on `window.opener`. The
cross-origin isolation service worker applies COOP/COEP headers, and the EHR
round trip can sever the opener relationship before the popup returns to
`/docs/examples/smart-demo?code=...&state=...`. Keep the localStorage popup
marker, SMART PKCE state `popupLaunch` flag, and BroadcastChannel/storage
callback path covered by `tests/wasm-demo-wc.spec.ts`.

After the opener receives a SMART token/error result, it must close the retained
popup window handle itself. Real EHR redirects can leave the callback page
unable to close itself with `window.close()` even after it successfully posts
the result back to the main SMART page.

The opener must poll the stored callback result while authorization is pending,
not just listen for `postMessage`, BroadcastChannel, and `storage` events. Real
browser/EHR timing can store the token and close the popup while the opener
misses the event, leaving the main SMART page in the authorizing/select state.
When the popup closes, continue a short grace poll against both
`fhir4ds_smart_callback_result` and `fhir4ds_smart_token` before treating
closure as cancellation.

Logout/reconnect depends on clearing every SMART localStorage key. In
particular, stale `fhir4ds_smart_callback_result` values can make a later
connect skip the patient portal and restore the prior patient.

The COI service worker must also skip COOP/COEP injection on same-origin URLs
that contain SMART OAuth `code` and `state` parameters. Those callback pages do
not need DuckDB-WASM isolation, and adding COOP there prevents the popup from
closing/returning control to the original SMART page. The website Playwright
suite has a header regression test for this.

## URL Resolution & Sub-paths

The website is hosted at `https://fhir4ds.com/`. When changing domains or deployment sub-paths:

1.  **Docusaurus `baseUrl`**: Must match the domain sub-path.
2.  **WASM Demo `BASE_URL`**: The `web/wasm-demo` build must use the same sub-path prefix (e.g., `/wasm-app/` or just `/` depending on setup).
3.  **Checklist**: See [web/wasm-demo/AGENTS.md](../wasm-demo/AGENTS.md) for more technical details on asset resolution.

## Troubleshooting
If the demo fails to load or shows a `SharedArrayBuffer` error, ensure `coi-serviceworker.js` is loading correctly and the iframe URL matches the actual deployment path of the WASM app.
