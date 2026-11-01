# Docs Audit Report

## Notebook Execution Status

- `docs/notebooks/cql.ipynb`: PASS. Executed successfully with `jupyter nbconvert --execute`.
- `docs/notebooks/dqm.ipynb`: PASS. Executed successfully with `jupyter nbconvert --execute`.
- `docs/notebooks/fhirpath.ipynb`: PASS. Executed successfully with `jupyter nbconvert --execute`.
- `docs/notebooks/viewdef.ipynb`: PASS. Executed successfully with `jupyter nbconvert --execute`.

Notes:
- nbconvert emitted `MissingIDFieldWarning` warnings from nbformat, but no notebook cell failed.
- After execution, install cells were updated to target release `0.0.5` as required:
  - `fhir4ds-v2==0.0.5`
  - `fhir4ds-v2[measures]==0.0.5`

## Stale Data Log

Fixed:
- `web/website/docs/getting-started/benchmarking.md`
  - Updated total conformance count from `2,821` to `2,822`.
- `web/website/docs/integrations/wasm-engine.md`
  - Updated WASM wheel references to `fhir4ds_v2-0.0.5-py3-none-any.whl`.
- `web/website/docs/getting-started/releases.md`
  - Updated current release section to version `0.0.5`, conformance total `2,822`, wheel name, and install command.
- `web/website/docs/examples/notebooks.md`
  - Updated notebook install snippets to `0.0.5`.
- `web/wasm-demo/vite.config.ts` and `web/wasm-demo/src/workers/pyodide.worker.ts`
  - Updated fallback/comment wheel references to `0.0.5`.
- `docs/notebooks/*.ipynb`
  - Updated install cells to target release `0.0.5`.

Not changed:
- Historical `0.0.3` references in older release notes.
- Numeric substrings in generated profiling JSON and fixture data.

## Audience Alignment Notes

- Developer docs remain copy-pastable and use current API/package names.
- Stakeholder-facing benchmark copy now matches current conformance totals.
- WASM integration docs now match the built and deployed 0.0.5 wheel.

## Draft Release Notes

### fhir4ds-v2 0.0.5

Release focus:
- Pressure-tested release candidate with a 10-iteration evolution loop.
- Fixed two C++/Python FHIRPath DuckDB parity bugs:
  - `fhirpath_number` simple-path fast path now preserves singleton enforcement through repeating object arrays.
  - Standalone `extension(url)` now dispatches to the C++ `ExtensionCall` evaluator path and matches Python fallback behavior.
- Rebuilt and bundled FHIRPath and CQL native DuckDB extensions.
- Updated WASM demo wheel and deployed the fresh build to the website static app.

Conformance:
- ViewDefinition: 134/134
- FHIRPath R4: 935/935
- CQL: 1706/1706
- DQM QI Core 2025: 47/47
- Overall: 2822/2822

Validation:
- Focused FHIRPath parity: 13/13
- Native FHIRPath C++ SQL suite: 110 assertions
- WASM Playwright: 11/11
