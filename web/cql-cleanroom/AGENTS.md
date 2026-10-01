# web/cql-cleanroom — AGENTS.md

Browser-native CQL workbench over `fhir4ds.operations` (the third adapter
after CLI and MCP). Pyodide hosts the fhir4ds wheel for stateless
capabilities; DuckDB-WASM executes translated SQL behind a TS executor
that emits schema:1 envelopes identical to the Python adapters.

## Commands

```bash
npm install
npm run build      # bundles wheel + wasm extensions into dist/assets
npx vitest run     # unit tests (tests/unit only — vitest.config.ts scoped)
npx playwright test        # e2e (needs vite preview on :5176, see below)
```

## Asset invariants

- Exactly ONE `fhir4ds_v2-*.whl` in `public/` (build fails on duplicates).
  Refresh it after Python capability changes:
  `python3 -m hatch build -t wheel && cp dist/fhir4ds_v2-*.whl public/`
  then rebuild (the post-build hook copies it into `dist/assets/`).
- `public/extensions/{fhirpath,cql}.duckdb_extension.wasm` must track the
  current extension builds (WASM targets).
- The e2e suite and the pytest capability-matrix legs require `vite preview`
  on port 5176 (NOT the dev server — stale-bundle hazard on WSL/drvfs):
  `npx vite preview --port 5176 --strictPort &` before tests.

## Testing doctrine

- Playwright tests boot the full engine per fresh page (wait on
  `.version-badge`); zero retries, zero flaky. Each full-suite run ~2.6m.
- The three-way capability matrix (`fhir4ds/operations/tests/test_capability_matrix.py`)
  drives `tests/e2e/matrix-leg.spec.ts` via the `CLEANROOM_MATRIX_FIXTURE`
  env (one fixture mechanism; per-leg sections) and SKIPS cleanly when the
  preview server is down.
- Macro-sync contract: `test_macro_sync.py` diffs the Python translator
  macro surface against `src/lib/cql-macros.ts`. New Python macros must be
  ported or added to `BROWSER_MACRO_GAP_ALLOWLIST` (justified entries only;
  the test prunes stale and flags silently-ported entries).

## Architecture seams

- `src/workers/cleanroom.worker.ts` — single worker owning Pyodide +
  DuckDB-WASM; protocol 1:1 with operations signatures; envelopes cross
  as JSON strings (S12).
- `src/lib/executor.ts` — exact-SQL executor (translated SQL runs
  VERBATIM; no client-side SQL rewriting, ever); Arrow rows materialize
  with DECIMAL rescale (typeId 7 + field scale); positional audit structs
  decode to named evidence dicts.
- `src/lib/resourceForm.ts` / `graphToCql.ts` — pure helpers with vitest
  round-trip invariants (no silent data loss; deterministic emission).
- Share links (`src/lib/share.ts`) carry libraries/cases/params ONLY —
  never datasets; fragments capped at 100 KB.

## Layout (workbench-reorg, schemaVersion 3)

- Editor column: library tabs + Monaco + two drawers — Visual editor
  (graph→CQL, apply-only) and FHIRPath scratchpad (both default
  collapsed).
- Run column: Results with THREE tabs — CQL output (table + Evidence
  drawer: explain + run-history compare), MeasureReport output (Measure
  mapping + Tests expected grid + rendered reports + the single Sankey),
  ViewDefinition output (VD over MeasureReports only). One shared
  Evaluate; tabs never re-execute. Show SQL is contextual (translation
  SQL on CQL/MR, flatten SQL on View); Show AST is global with a
  define-name filter.
- Side column: Dataset tree (patient-grouped, per-type subgroups,
  25-row cap + show-more + filter) and the recursive Resource Builder.
- Tab panels stay MOUNTED but hidden (`.tab-panel[hidden]` CSS guard);
  e2e must use `state: "hidden"`, not `detached`, for inactive panes.
- Run history: every evaluate appends a row-shaped run to IndexedDB
  (cap 20; `src/lib/runHistory.ts`); compare = current vs selected
  prior run via compare_evidence; drift warning compares SHA-256
  library/dataset hashes (never blocks). Runs NEVER enter zips or
  share links. The Evidence drawer is a `<details open>` — e2e toggles
  must check the DOM `open` property (attribute renders as `""`).

FDDs: `fhir4ds-private/docs/architecture/plans/FEATURE_CQL_CLEANROOM*.md`
(cycles 1-3), `FEATURE_CLEANROOM_MEASURE_REPORTS.md`,
`FEATURE_CLEANROOM_TEST_DATA_AUTHORING.md`,
`FEATURE_CLEANROOM_WORKBENCH_REORG.md`.
