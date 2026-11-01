# Docs Audit Report - Release 0.0.8

## 1. Notebook Execution Status

- `docs/notebooks/cql.ipynb`: PASS.
- `docs/notebooks/dqm.ipynb`: PASS.
- `docs/notebooks/fhirpath.ipynb`: PASS.
- `docs/notebooks/viewdef.ipynb`: PASS.

Execution command shape:

```bash
python3 -m jupyter nbconvert --to notebook --execute <notebook> \
  --output-dir ../../.temp/docs-notebook-runs \
  --ExecutePreprocessor.timeout=900
```

Post-run output scan found no notebook `error` outputs.

## 2. Stale Data Log

Fixed:

- `web/website/docs/integrations/wasm-engine.md`
  - Updated the Pyodide install snippet to install pure-Python dependencies
    first and install the bundled `fhir4ds_v2-0.0.8` wheel with `deps=False`.
    The previous snippet would have made micropip try to resolve the native
    `duckdb` package in-browser.
- `web/website/AGENTS.md`
  - Added the durable `deps=False` Pyodide documentation rule.

Previously fixed during evolution:

- Website/WASM active release surfaces now point to 0.0.8:
  homepage version badge, website test, notebook docs, WASM integration wheel
  names, release notes, demo public wheel, and website static `wasm-app`.
- Docusaurus build passes after docs changes.

Remaining `0.0.7` references are intentional:

- `web/website/docs/getting-started/releases.md` historical Version 0.0.7
  section.
- `docs/architecture/plans/*` historical feature-plan target versions.

No `[PLACEHOLDER]` hits were found in active docs.

## 3. Audience Alignment Notes

- Stakeholder-facing release notes and homepage metrics remain strategic and
  value-oriented.
- Developer-facing WASM integration docs are now copy-pastable for Pyodide:
  dependency installation is explicit and the local wheel uses `deps=False`.
- The website build continues to emit the existing
  `vscode-languageserver-types` dynamic require warning, but Docusaurus
  generated static files successfully.

## 4. Draft Release Notes

The website now includes `Version 0.0.8` release notes under
`web/website/docs/getting-started/releases.md`.

Draft summary:

- FHIRPath native parity tightened for malformed Section 5.1 existence-helper
  arities, including specialized `exists()` and FHIR-specific `hasValue()`.
- CQL Measurement Period defaults preserve DateTime precision and authored
  open/closed interval boundaries through DQM population SQL generation.
- Public API boundaries now raise actionable package errors for malformed DQM
  config, HAPI/Mongo materialization config, and filesystem source inputs.
- DQM audit evidence preserves group-local causal targets and Mongo compact
  materialization mirrors the HAPI compact result/full audit split.
- Package metadata, public versions, notebooks, runner metadata, wheel
  contents, website docs, and WASM translator assets align with 0.0.8.
- Conformance baseline remains 2822/2822:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47.

## Verification

- Notebook execution: all four notebooks passed.
- Active stale scan: only historical 0.0.7 release notes and architecture-plan
  targets remain.
- `npm run build` in `web/website`: passed with the existing dynamic require
  warning.
