# Docs Audit Report

## Notebook Execution Status

- `docs/notebooks/cql.ipynb`: PASS.
- `docs/notebooks/dqm.ipynb`: PASS.
- `docs/notebooks/fhirpath.ipynb`: PASS.
- `docs/notebooks/viewdef.ipynb`: PASS.

## Stale Data Log

Fixed:
- `web/website/docs/api-reference/sources/index.md`
  - Corrected adapter API reference links to the actual Docusaurus routes.

Checked:
- `web/website` build now completes without broken-link warnings after the fix.
- WASM wheel copied to `web/wasm-demo/public/` matches the fresh `dist/` wheel checksum.

## Audience Alignment Notes

- Developer docs remain copy-pastable for source adapters after route correction.
- Release validation docs/results align with current conformance total 2822/2822.

## Draft Release Notes

### fhir4ds-v2 0.0.5

Release focus:
- Freshly rerun 10-iteration release-prep loop from scratch.
- Fixed Python/C++ FHIRPath collection equality drift for multi-item `=`/`!=`.
- Preserved spec-strict core FHIRPath behavior while aligning DuckDB wrapper resilience outside strict mode.
- Rebuilt and bundled native DuckDB extensions.
- Rebuilt WASM demo, synchronized the public wheel, and deployed the fresh website static app.

Conformance:
- ViewDefinition: 134/134
- FHIRPath R4: 935/935
- CQL: 1706/1706
- DQM QI Core 2025: 47/47
- Overall: 2822/2822
