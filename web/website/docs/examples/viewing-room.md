---
id: viewing-room
title: SQL-on-FHIR Viewing Room
sidebar_label: Viewing Room
description: A ViewDefinition playground — load FHIR resources, author a ViewDefinition, and see the flattened SQL view recalculate live, entirely in your browser via FHIR4DS-WASM.
hide_table_of_contents: true
---

# SQL-on-FHIR Viewing Room

The Viewing Room is a browser-native playground for
[SQL-on-FHIR v2 ViewDefinitions](https://build.fhir.org/ig/HL7/sql-on-fhir/index.html) —
the radiology reading room where you examine what a view really produces.
Load or edit FHIR resources, author or edit a ViewDefinition, and the
flattened SQL output recalculates live as you type. No Run button, no
server: the FHIR4DS viewdef engine runs in Pyodide, the generated SQL
executes on DuckDB-WASM, and nothing leaves the browser.

:::info
First boot takes ~30–60 seconds (Pyodide + DuckDB-WASM download); warm
boots are cached. The Viewing Room needs no server.
:::

import ViewingRoomWC from '@site/src/components/ViewingRoomWC';

<ViewingRoomWC height="85vh" popout />

## Walkthrough

### 1. Browse what's loaded

The data pane opens on **Browse** — your resources grouped by type, with
the ViewDefinition's target type highlighted. Switch to the **Editor** tab
to edit the raw NDJSON (one resource per line, or a JSON array).

### 2. Edit and watch it recalc

Every edit to the ViewDefinition or the resources triggers a debounced
auto-recalc (~0.8 s) — the output table, SQL, and diagnostics update
without pressing anything. Rapid typing collapses to the latest state.

### 3. Inspect the exact SQL

The **SQL** tab shows the verbatim SQL the FHIR4DS generator emitted —
the exact-SQL doctrine made visible: what you see is exactly what ran on
DuckDB, never rewritten or prettified.

### 4. Read typed diagnostics

An invalid ViewDefinition (missing `select`, unknown column type,
malformed JSON) surfaces a typed diagnostics list — code, severity, and
the engine's message — never a blank screen. Wrong-resourceType input
yields a 0-rows hint that names both the view's target and what you
actually loaded.

### 5. Load a sample

The gallery ships six engine-verified samples: the sql-on-fhir.org
reference demographics set (the default — same patients and VD as the
reference playground), patient addresses (`forEach`), a patient + contact
address union (`unionAll`), US Core blood pressures (deep `forEach` +
`where` on component coding), questionnaire responses (`repeat`), and
observation values (`collection: true` typed columns rendered as JSON
arrays).

## Capabilities

*   **Auto-recalc** — debounced live recalculation on every edit; manual
    Run removed (retry-boot is the only explicit affordance).
*   **Browse + Edit** — grouped resource tree (vendored from the CQL
    Clinic data viewer) with the VD target highlighted, plus the raw
    NDJSON editor.
*   **Exact-SQL doctrine** — the SQL tab shows the generated SQL verbatim.
*   **Typed diagnostics** — parse/validation/evaluation errors as coded
    diagnostics, not stack traces.
*   **Collection columns** — `collection: true` columns render as JSON
    arrays with NULL chips for empty cells.
*   **Web component** — the same app ships as
    `<sqlonfhir-viewing-room>` with a stable bundle filename for
    embedding (this page embeds it).

## Running locally

```bash
cd web/viewing-room
npm install
npm run build          # bundles the wheel + fhirpath WASM extension into dist/
npx vite preview --port 5177   # COOP/COEP headers required for DuckDB-WASM
```

The app requires exactly one `fhir4ds_v2-*.whl` in `public/` (built from
the working tree) plus `fhirpath.duckdb_extension.wasm` — the build
copies them into `dist/assets/`. The e2e journey suite runs against the
preview server: `npm run e2e`.
