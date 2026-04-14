# WASM Demo Maintenance (AGENTS.md)

This document provides critical instructions for maintaining and troubleshooting the WASM demo's resource resolution logic.

## URL Resolution Checklist

The WASM demo depends on three types of external assets that must resolve correctly in four environments (Standalone Dev, Standalone Preview, Website Dev, Website Production).

### 1. DuckDB Extensions (`.wasm`)
- **Location**: `public/extensions/`
- **Resolution**: Managed in `src/hooks/useDuckDB.ts`.
- **Logic**: Uses `window.location.origin + import.meta.env.BASE_URL + "/extensions/"`.
- **Why**: Ensures extensions are loaded from the correct sub-path when embedded in Docusaurus.

### 2. Python Wheels (`.whl`)
- **Location**: `public/`
- **Resolution**: Managed in `src/workers/pyodide.worker.ts`.
- **Logic**: Uses `new URL("../cql_py-*.whl", import.meta.url)` with a root-relative fallback.
- **Why**: Workers are bundled into `assets/`, so `../` reaches the application root.

### 3. DuckDB Worker (`.js`)
- **Location**: Resolved by Vite via `@duckdb/duckdb-wasm/dist/...`
- **Resolution**: Managed via `?url` imports in `useDuckDB.ts`.
- **Why**: Prevents "Invalid URL" errors in `dlopen` caused by CDN blob workers.

## Environment Matrix

| Environment | BASE_URL | Extension Path | Wheel Path |
|-------------|----------|----------------|------------|
| Standalone Dev | `/` | `/extensions/` | `/cql_py-*.whl` |
| Website Prod | `/wasm-app/` | `/wasm-app/extensions/` | `/wasm-app/cql_py-*.whl` |

## Troubleshooting
If engines fail to load, check the Network tab for 404s on `.wasm` or `.whl` files. Ensure the path includes the expected sub-path prefix if running within the website.
