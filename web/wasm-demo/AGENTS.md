# WASM Demo Maintenance (AGENTS.md)

This document provides critical instructions for maintaining and troubleshooting the WASM demo's resource resolution logic.

## ⚠️ Release Checklist — Do This Every Release

The following steps **must all be done** when releasing a new version, or the CQL playground will fail with a Pyodide initialization error.

### Step 1: Build and copy the wheel

```bash
cd /path/to/fhir4ds
hatch build -t wheel
cp dist/fhir4ds_v2-NEW_VERSION-py3-none-any.whl web/wasm-demo/public/
rm web/wasm-demo/public/fhir4ds_v2-OLD_VERSION-py3-none-any.whl  # remove old
```

`vite.config.ts` auto-discovers the newest `fhir4ds_v2-*.whl` in `public/` at build time. There must be exactly one wheel in that directory.

### Step 2: Update all version references

Search `web/wasm-demo/` and `web/website/docs/` for the old version string (e.g. `0.0.2`) and update to the new version. The key files:
- `web/website/docs/integrations/wasm-engine.md` — translator wheel filename in two places
- `web/wasm-demo/vite.config.ts` — fallback wheel filename in the `WHEEL_NAME` constant
- `web/wasm-demo/src/workers/pyodide.worker.ts` — comment with example filename
- `web/website/src/pages/index.tsx` — homepage `PRODUCT_VERSION`
- `web/website/tests/demo.spec.ts` — homepage version assertion
- `web/website/docs/examples/notebooks.md` and `docs/getting-started/releases.md`
  — public install snippets and current release notes

### Step 3: Update `__version__` in subpackages

The root package version comes from `pyproject.toml`. But four subpackages have their own `__version__` that must be updated manually:
- `fhir4ds/cql/__init__.py`
- `fhir4ds/dqm/__init__.py`
- `fhir4ds/fhirpath/__init__.py`
- `fhir4ds/viewdef/__init__.py`

### Step 4: Build the WASM demo

```bash
cd web/wasm-demo
npm run build
```

### C++ WASM extension rebuild prerequisite

The `.duckdb_extension.wasm` files in `public/extensions/` are DuckDB extension
side modules, not outputs of `npm run build`. When the C++ FHIRPath or CQL
extensions change, rebuild them from the extension directories first:

```bash
cd extensions/fhirpath
make wasm_eh

cd ../cql
make wasm_eh
```

This requires an Emscripten SDK environment on `PATH` (`emcmake`, `emmake`,
`emcc`). Use the Emscripten version pinned by the matching DuckDB-WASM package.
For `@duckdb/duckdb-wasm@1.33.1-dev41.0`, that is `emsdk 3.1.56` from the
DuckDB-WASM build image. Newer SDKs can compile successfully but produce
side modules that fail at browser load time with dynamic-linking ABI errors.
If `make wasm_eh` fails with `emcmake: not found`, install/activate emsdk and
source `emsdk_env.sh` before building.

After a successful rebuild, copy the generated `fhirpath.duckdb_extension.wasm`
and `cql.duckdb_extension.wasm` artifacts into:

```bash
web/wasm-demo/public/extensions/
```

Then run `npm run build` so Vite copies them into `dist/assets/`.

### Step 5: ⚠️ Deploy the build to the website static directory

```bash
rm -rf web/website/static/wasm-app
cp -r web/wasm-demo/dist/. web/website/static/wasm-app/
```

**This is the most commonly missed step.** The Docusaurus website serves the WASM demo from
`web/website/static/wasm-app/` — a pre-built snapshot. Rebuilding `web/wasm-demo/` does NOT
auto-update the website. When this step is skipped:
- The standalone demo (`vite preview`) works fine.
- The website CQL playground (`Examples > CQL Playground`) fails with a Pyodide error.
- The compiled worker in `static/wasm-app/assets/pyodide.worker-XXXX.js` has a different hash than `wasm-demo/dist/assets/`, making the divergence easy to verify after the fact.

### Step 6: Run Playwright tests

```bash
cd web/wasm-demo
npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts tests/e2e/cms-measures.spec.ts
# All playground, web component, and CMS measure execution tests must pass.
```

Do not skip `cms-measures.spec.ts`. The playground and web-component tests can
pass while the quality-measure examples fail at runtime because the CQL
translator emits UDFs that are not registered in the CQL WASM extension.

After refreshing `web/website/static/wasm-app/`, also run the website gates:

```bash
cd web/website
npm run typecheck
npm run build
```

### Browser CQL Runtime Surface

The browser runs translated SQL in DuckDB-WASM and uses Pyodide only for CQL
translation. Python fallback UDFs registered through the native `duckdb` Python
package are not callable from DuckDB-WASM. Any UDF name emitted into browser SQL
must therefore be available from the compiled C++ WASM extensions.

If CQL extension registrations are changed in `extensions/cql/src/cql_extension.cpp`:
- rebuild the native extension and run `./build/release/test/unittest "*cql*"`;
- rebuild `make wasm_eh` with the pinned emsdk;
- copy the new `cql.duckdb_extension.wasm` into `public/extensions/`;
- rebuild `web/wasm-demo`;
- run the CMS Playwright tests, not only playground tests.

### Native/WASM UDF Surface Drift

Some CQL UDF registrations have historically been guarded by `__EMSCRIPTEN__`.
That makes native extension tests insufficient unless the same browser-required
function surface is also exercised in a direct C++-only native test or a WASM
load test. Any function emitted into browser SQL should be present in the
required C++/SQL-macro inventory, not merely available through Python fallback
on native DuckDB.

### SMART OAuth Popup Callbacks

Do not depend only on `window.opener` for SMART popup callbacks. The website is
cross-origin isolated for DuckDB-WASM, and COOP/COEP can sever opener during
the cross-origin EHR login round trip. Popup launch state is marked in
localStorage and persisted on the SMART PKCE state payload, and callbacks
broadcast success/error with BroadcastChannel plus a storage fallback. Keep
`tests/e2e/smart-callback.spec.ts` and the website `tests/wasm-demo-wc.spec.ts`
callback regression test passing when changing SMART auth.

The opener should close its retained popup handle after receiving a SMART
success/error callback. The callback page also calls `window.close()`, but real
EHR round trips can leave the popup script unable to close itself reliably even
after token exchange succeeds.

The opener must also poll `fhir4ds_smart_callback_result` while authorization is
pending. Browser storage/BroadcastChannel delivery can be missed around popup
closure, and treating a closed popup as cancellation before consuming that
stored result leaves the main page disconnected even though a token exists.
On popup close, continue a short grace poll against both the stored callback
result and `fhir4ds_smart_token` before resetting auth state.

`clearAuth()` must clear every SMART localStorage key, including
`fhir4ds_smart_callback_result` and `fhir4ds_smart_popup_pending`. Leaving a
stale callback result behind makes a later reconnect skip the patient portal and
restore the previous user.

---

## Why the Pyodide Worker Uses `deps=False`

`fhir4ds-v2` declares `duckdb~=X.Y.Z` as a Python dependency. Pyodide's `micropip` can only install **pure Python wheels**. DuckDB requires compiled C extensions and has no pure Python wheel on PyPI.

**This is by design.** Browser query execution uses DuckDB-WASM (the JavaScript library), but the translator import graph still imports Python-side DuckDB-facing modules at package load. Load Pyodide-hosted binary packages with `pyodide.loadPackage(...)`; do not let `micropip` resolve them from PyPI.

### How This Is Handled

1. **`fhir4ds/cql/__init__.py`** wraps direct `import duckdb` in `try/except ImportError` and installs a minimal stub for translator-only paths. Other package initializers can still import `fhir4ds.fhirpath.duckdb` and require Pyodide-hosted binary packages.

2. **`pyodide.worker.ts`** uses `micropip.install(wheel, deps=False)` to skip PyPI auto-resolution of native dependencies. It manually loads Pyodide-hosted packages such as `duckdb`, `orjson`, and `pyarrow`, then installs only the pure-Python deps needed by the CQL translator.

**Do not** revert either of these changes. Both are required for the WASM demo to work.

### Pure-Python Deps for CQL Translation

The worker manually installs:
- `duckdb`, `orjson`, and `pyarrow` via `pyodide.loadPackage(...)` — imported by fhir4ds at module load
- `antlr4-python3-runtime>=4.10` — required for CQL parsing
- `python-dateutil>=2.8` — required for CQL date/time operations

If new dependencies are added to `fhir4ds-v2` that are needed in the CQL
translation path, load Pyodide-hosted packages with `pyodide.loadPackage([...])`
and add pure-Python wheels to the `micropip.install([...])` call in
`src/workers/pyodide.worker.ts`.

---

## URL Resolution Details

The WASM demo depends on three types of external assets that must resolve correctly in all environments (Standalone Dev, Standalone Preview, Website Dev, Website Production).

### 1. DuckDB Extensions (`.wasm`)
- **Location**: `public/extensions/`
- **Resolution**: Managed in `src/hooks/useDuckDB.ts`.
- **Logic**: Uses `window.location.origin + import.meta.env.BASE_URL + "/extensions/"`.
- **Why**: Ensures extensions are loaded from the correct sub-path when embedded in Docusaurus.

### 2. Python Wheels (`.whl`)
- **Location**: `public/`
- **Resolution**: Managed in `src/workers/pyodide.worker.ts`.
- **Logic**: Uses `new URL("./${__FHIR4DS_WHEEL_NAME__}", import.meta.url)` where `__FHIR4DS_WHEEL_NAME__` is injected by `vite.config.ts` at build/dev time.
- **Why**: Workers are bundled into `assets/`, so the URL is relative to the worker bundle location.

### 3. DuckDB Worker (`.js`)
- **Location**: Resolved by Vite via `@duckdb/duckdb-wasm/dist/...`
- **Resolution**: Managed via `?url` imports in `useDuckDB.ts`.
- **Why**: Prevents "Invalid URL" errors in `dlopen` caused by CDN blob workers.

## Environment Matrix

| Environment | BASE_URL | Extension Path | Wheel Path |
|-------------|----------|----------------|------------|
| Standalone Dev | `/` | `/extensions/` | auto-resolved from worker URL |
| Website Prod | `/wasm-app/` | `/wasm-app/extensions/` | auto-resolved from worker URL |

## Troubleshooting

If engines fail to load, check the browser's Network tab for 404s on `.wasm` or `.whl` files. Ensure the path includes the expected sub-path prefix if running within the website.

If the Pyodide init fails with `Can't find a pure Python 3 wheel for 'duckdb'`:
- Verify `pyodide.worker.ts` uses `micropip.install(__wheel_url__, deps=False)`.
- Verify `fhir4ds/cql/__init__.py` wraps the `import duckdb` in `try/except ImportError`.
- Rebuild the wheel: `hatch build -t wheel` and copy to `public/`.
