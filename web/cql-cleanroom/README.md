# CQL Cleanroom

A browser-native CQL workbench: author CQL, load FHIR test datasets,
evaluate populations, inspect evidence, and compare runs — entirely
client-side (no server round-trips for evaluation).

Built on [fhir4ds](../..) as the third adapter of the operations layer
(alongside the CLI and MCP server): the Pyodide-hosted wheel runs the
stateless capabilities (`parse_cql`, `translate_cql`, `validate_resource`,
`resource_schema`, `fhirpath_eval`, `compare_evidence`), and DuckDB-WASM
executes the translated SQL behind a TypeScript executor that emits the
same `schema:1` envelopes as the Python operations.

## Features

- **Editor** — Monaco with a CQL grammar, live parse diagnostics as
  markers (jump-to-location), and a parameter panel.
- **AST pane** — statement-level parse trees via `parse_cql
  (include_ast=true)` (client-derived view).
- **Evaluate / run tests** — population SQL executes verbatim on
  duckdb-wasm; results table with CQL `column_types` badges and a SQL
  viewer.
- **Datasets** — paste NDJSON, per-line validation, resource stats;
  loaded straight into DuckDB-WASM (bypassing Pyodide).
- **Evidence** — per-patient audit drill-in (`explain_patient`),
  population-flow Sankey, evidence.json import, and **Compare mode**
  (`compare_evidence` delta: moved/added/removed/flipped).
- **FHIRPath playground** — evaluate any FHIRPath expression against a
  pasted resource.
- **Workspace** — IndexedDB persistence with schema migrations, zip
  export/import (fflate), multi-library tabs.
- **Share links** — libraries + settings encoded into the URL fragment
  (LZ-compressed, ≤100 KB; datasets are never embedded).

## Development

```bash
npm install
npm run build          # builds dist/ (wheel auto-discovered from public/)
npm run preview        # serve the built app (COOP/COEP required)
```

The `public/` directory must contain exactly one
`fhir4ds_v2-<version>-py3-none-any.whl` (build it with
`python3 -m hatch build -t wheel` from the repo root and copy it here)
plus `extensions/*.duckdb_extension.wasm`.

### Tests

```bash
npx playwright test     # e2e: boot, capabilities, workbench, workspace,
                        # cycle2 (AST/compare), cycle3 (compare UI/share)
npx vitest run          # envelope parity vs Python references
```

The e2e suite expects the app on `http://localhost:5176` (start
`npm run preview -- --port 5176 --strictPort`; an existing server is
reused). The capability-matrix Python test
(`fhir4ds/operations/tests/test_capability_matrix.py`) drives the same
preview server through Playwright for the three-way parity check
(CLI == MCP == browser) — keep it running when executing that suite.

## Architecture

See `fhir4ds-private/docs/architecture/plans/FEATURE_CQL_CLEANROOM.md`
(cycle 1) and `FEATURE_CQL_CLEANROOM_C2.md` (cycle 2) for the design
contracts: the exact-SQL doctrine (the executor never rewrites
translated SQL), the worker protocol mirroring operations signatures
1:1, and the envelope parity gates.
