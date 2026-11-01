# Docs Audit — v0.0.20

## Notebooks (5/5 executed clean against the 0.0.20 wheel)

All five notebooks (`cql`, `dqm`, `fhirpath`, `omop-mapping`, `viewdef`)
executed in a clean venv with the 0.0.20 wheel installed. Install pins
updated to `fhir4ds-v2==0.0.20` / `fhir4ds-v2[measures]==0.0.20`; stale
pip error outputs cleared from install cells. Zero Python error cells.
(The pip install cell itself shows "not found" until 0.0.20 publishes to
PyPI — expected pre-release; subsequent cells ran against the local wheel.)

## Release notes

`web/website/docs/getting-started/releases.md`: v0.0.20 section added
(perf optimizations with retest numbers, DuckDB 1.5.6 triple-bundle
support, serve layer, VD form editor, terminology provenance rule,
medterm4ds 0.0.8, QA summary). PRODUCT_VERSION badge updated.

## WASM surfaces (all at 0.0.20, zero stale wheels)

| Surface | Wheel | Rebuilt | Deployed |
|---------|-------|---------|----------|
| wasm-demo → website/static/wasm-app/ | ✓ | ✓ | ✓ |
| cql-cleanroom → website/static/cql-cleanroom/ + devserver/static-cleanroom/ | ✓ | ✓ | ✓ both |
| cql-clinic → website/static/cql-clinic-app/ | ✓ | ✓ | ✓ |
| viewing-room → website/static/viewing-room-app/ | ✓ | ✓ | ✓ |
| bulk-publisher-app (website static) | ✓ | — | ✓ |
| vite.config fallbacks (cleanroom, clinic, viewing-room) | ✓ | | |

Playwright e2e on wasm-demo: 13/13 passed. Website build clean (zero
non-0.0.20 wheels in build output). wasm-engine.md references updated.

## medterm4ds

PyPI wheel byte-identical to the local dist (md5 e1f17071...). The
`[terminology]` extra resolves 0.0.8 from PyPI in a clean venv; pip
check clean.
