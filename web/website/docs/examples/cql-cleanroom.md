---
id: cql-cleanroom
title: CQL Cleanroom
sidebar_label: CQL Cleanroom
description: A fully browser-native CQL workbench — author, validate, evaluate, test, and diff clinical logic entirely client-side with FHIR4DS in Pyodide and DuckDB-WASM.
hide_table_of_contents: true
---

# CQL Cleanroom

The CQL Cleanroom is a browser-native workbench for Clinical Quality
Language. Everything runs client-side: the FHIR4DS wheel executes in
Pyodide for stateless operations (parse, translate, validate), and the
translated SQL runs on DuckDB-WASM behind a TypeScript executor that emits
envelopes **field-for-field identical** to the CLI and MCP adapters —
verified by a three-way capability matrix on a shared fixture.

:::info
First boot takes ~40–60 seconds (Pyodide + DuckDB-WASM download); warm
boots are cached. The workbench needs no server and no data leaves the
browser.
:::

## Workbench capabilities

- **Editor** — Monaco with CQL syntax, live diagnostics (markers from
  structured error locations), parameter panel, and multi-library tabs.
  Workspaces persist to IndexedDB and export/import as zip.
- **Run** — evaluate libraries against an inline dataset with typed
  result columns, view the generated SQL, and run test cases with
  pass/fail diffs and failure reasons.
- **Evidence** — per-patient audit drill-in (population membership with
  the reasoning tree), population Sankey flows, evidence compare
  (baseline vs. current with moved/added/removed/flipped classifications),
  and evidence.json import.
- **Explore** — FHIRPath playground, statement-level AST trees, and a
  visual algorithm editor that emits CQL (with a parse round-trip guard
  before applying).
- **Build** — a schema-driven FHIR resource builder (8 resource types +
  raw JSON fallback). The *validate ⇒ loads* invariant holds: a resource
  that passes the form's validation always loads cleanly into evaluation.
- **Share** — LZ-compressed URL fragments carry libraries, cases, and
  parameters (never datasets; capped at 100 KB).

## Parity contract

The Cleanroom is the third adapter over `fhir4ds.operations`:

| Capability | CLI | MCP | Browser |
|---|---|---|---|
| `parse_cql` | — | ✓ | ✓ (incl. `include_ast`) |
| `translate_cql` | — | ✓ | ✓ (audit modes + `output_columns`) |
| `evaluate_library` / `run_tests` | ✓ | ✓ | ✓ |
| `explain_patient` | — | ✓ | ✓ |
| `validate_resource` / `resource_schema` | — | ✓ | ✓ |
| `compare_evidence` | ✓ (`--baseline`) | ✓ | ✓ |

The three-way matrix test asserts identical normalized envelopes across
adapters for both `run_tests` and `compare_evidence`, and a macro-sync
contract test keeps the browser SQL macro surface in lockstep with the
Python translator.

## Running locally

```bash
cd web/cql-cleanroom
npm install
npm run build          # bundles the wheel + WASM extensions into dist/
npx vite preview --port 5176   # COOP/COEP headers required for DuckDB-WASM
```

The app requires exactly one `fhir4ds_v2-*.whl` in `public/` (built from
the working tree) plus the two `.duckdb_extension.wasm` binaries — the
build copies them into `dist/assets/`.
