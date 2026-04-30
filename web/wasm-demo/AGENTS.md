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
npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts
# All 11 tests must pass (5 playground + 6 web component)
```

---

## Why Pyodide Can't Install duckdb

`fhir4ds-v2` declares `duckdb~=X.Y.Z` as a Python dependency. Pyodide's `micropip` can only install **pure Python wheels**. DuckDB requires compiled C extensions and has no pure Python wheel on PyPI.

**This is by design.** In the browser, DuckDB is provided by DuckDB-WASM (the JavaScript library). The Python-side `duckdb` package is not needed.

### How This Is Handled

1. **`fhir4ds/cql/__init__.py`** wraps `import duckdb` in `try/except ImportError` and installs a minimal stub. The `CQLToSQLTranslator` (used in the worker) never calls DuckDB — it only generates SQL strings. The stub satisfies the import without needing the real package.

2. **`pyodide.worker.ts`** uses `micropip.install(wheel, deps=False)` to skip auto-resolution of the `duckdb` dependency. It manually installs only the pure-Python deps needed by the CQL translator.

**Do not** revert either of these changes. Both are required for the WASM demo to work.

### Pure-Python Deps for CQL Translation

The worker manually installs:
- `antlr4-python3-runtime>=4.10` — required for CQL parsing
- `python-dateutil>=2.8` — required for CQL date/time operations

If new pure-Python dependencies are added to `fhir4ds-v2` that are needed in the CQL translation path, add them to the `micropip.install([...])` call in `src/workers/pyodide.worker.ts`.

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
