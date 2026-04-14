# FHIR4DS Interactive WASM Demo

Browser-based interactive demo for FHIR4DS — CQL authoring, real-time CQL→SQL
translation, and in-browser query execution against FHIR data.

## Architecture

- **UI:** React + TypeScript + Vite
- **Database:** `@duckdb/duckdb-wasm` — columnar SQL engine in the browser
- **CQL Translation:** `fhir4ds.cql` running via Pyodide (Python-in-Wasm) in a Web Worker
- **Editor:** Monaco Editor (VS Code engine)

All processing happens locally in the browser. No data leaves the client.

## Quick Start

```bash
cd web/wasm-demo
npm install
npm run dev
```

## How It Works

1. **DuckDB-Wasm** initializes in the browser and loads synthetic FHIR data.
2. **Pyodide** loads in a Web Worker with the `fhir4ds` package.
3. **Translate** sends CQL to the Pyodide worker → `fhir4ds.cql` parses and generates SQL.
4. **Run** executes the generated SQL against DuckDB-Wasm.

## Maintenance & URL Resolution

This application uses a complex resolution logic for WASM extensions and Python wheels to ensure it works both as a standalone app and when embedded in the Docusaurus website at a sub-path (`/wasm-app/`).

**CRITICAL: See [AGENTS.md](./AGENTS.md) for the URL resolution checklist and troubleshooting instructions.**

