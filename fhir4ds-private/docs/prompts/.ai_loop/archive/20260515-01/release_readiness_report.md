# Release Readiness Report

## Build Status

Native:
- FHIRPath C++ extension: PASS (`cmake --build build/release`)
- CQL C++ extension: PASS (`cmake --build build/release`)
- Rebuilt package binaries copied into:
  - `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
  - `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`

Wheel:
- PASS (`hatch build`)
- Built:
  - `dist/fhir4ds_v2-0.0.5-py3-none-any.whl`
  - `dist/fhir4ds_v2-0.0.5.tar.gz`
- Wheel smoke check confirmed both native extensions are bundled.
- Version smoke check confirmed root and subpackages report `0.0.5`.

WASM:
- PASS (`cd web/wasm-demo && npm run build`)
- Updated public wheel: `web/wasm-demo/public/fhir4ds_v2-0.0.5-py3-none-any.whl`
- Removed old public wheel: `web/wasm-demo/public/fhir4ds_v2-0.0.4-py3-none-any.whl`
- Deployed current demo build to `web/website/static/wasm-app/`.

## Test Coverage

Unit / integration:
- Focused FHIRPath parity: 13/13 passed.
- Native FHIRPath C++ SQL suite: 110 assertions passed.
- CQL focused parity slices: 8/8 and 14/14 passed.
- ViewDefinition tests: 644 passed, 22 skipped, 17 xfailed.
- DQM tests: 70 passed, 2 warnings.

E2E:
- `cd web/wasm-demo && npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts`
- 11/11 passed.

## Conformance Report

Final post-build gate:

```text
>>> Running ViewDefinition conformance suite...
>>> Running FHIRPath (R4) conformance suite...
>>> Running CQL conformance suite...
>>> Running DQM (QI Core 2025) conformance suite...
ViewDefinition            | 134      | 134      |  100.0%
FHIRPath (R4)             | 935      | 935      |  100.0%
CQL                       | 1706     | 1706     |  100.0%
DQM (QI Core 2025)        | 47       | 47       |  100.0%
OVERALL COMPLIANCE        | 2822     | 2822     |  100.0%
```

## Final GO / NO-GO Recommendation

GO.

Blockers:
- None.

Residual cleanup note:
- Local validation/build commands regenerated cache/report artifacts. Review `git status` before commit and keep only intended release artifacts and source/docs changes.
