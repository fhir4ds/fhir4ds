# Release Readiness Report - 0.0.9

## 1. Build Status

- **Native**: PASS. `cmake --build build/release` completed for
  `extensions/fhirpath` and `extensions/cql`.
- **Wheel**: PASS. `python3 -m hatch build` produced
  `dist/fhir4ds_v2-0.0.9.tar.gz` and
  `dist/fhir4ds_v2-0.0.9-py3-none-any.whl`.
- **WASM app**: PASS. `npm run build` in `web/wasm-demo` completed and copied
  `fhir4ds_v2-0.0.9-py3-none-any.whl` plus extension side modules into
  `dist/assets/`.
- **WASM extension rebuild**: Not run in this environment because `emcmake`,
  `emmake`, and `emcc` are not on `PATH`. No C++/WASM extension source changed
  in this release-prep patch; existing side modules were served successfully in
  preview and website E2E.

## 2. Artifact Gate

- **Wheel metadata**: PASS. Metadata reports `Version: 0.0.9`; dependencies
  include `duckdb==1.5.2`, `numpy`, and `pint>=0.21.0`; bundled native
  `fhirpath` and `cql` extension files are present.
- **Clean install**: PASS. Fresh venv at `/tmp/fhir4ds-clean-venv-009`
  installed the wheel from outside the checkout; `pip check` reported no broken
  requirements.
- **C++ extension proof**: PASS. Clean installed wheel returned
  `{'fhirpath_cpp': True, 'cql_cpp': True}` and executed `fhirpath_text`,
  `fhirpath_number`, `quantityValue`, `cql_valueset_cache_clear`,
  `cql_valueset_cache_add`, `cql_valueset_cache_size`, and `in_valueset`.
- **Public API matrix**: PASS. Clean venv smoke covered
  `fhir4ds.create_connection()`, `create_connection(valueset_cache=...)`,
  `fhir4ds.register(con)`, `register(con, valueset_cache=...)`, and repeated
  `register(con)` calls.
- **Collision behavior**: PASS. A pre-created `fhirpath_text` function caused
  `fhirpath_cpp` to report `False` without crashing while `cql_cpp` still
  loaded.
- **Unsupported DuckDB fallback**: PASS. A separate venv forced
  `duckdb==1.4.2`; bundled C++ extensions did not load
  (`{'fhirpath_cpp': False, 'cql_cpp': False}`) and Python fallback executed
  representative FHIRPath/CQL UDFs.
- **WASM wheel checksum**: PASS. `dist/`, `web/wasm-demo/public/`, and both
  `web/website/static/wasm-app/` wheel copies share SHA256
  `8474b476fb40cab1ce5299e67f0f00a4ed522000e1aa2a84596362894f296f14`.
- **Preview asset smoke**: PASS. Vite preview served `/`,
  `/assets/fhir4ds_v2-0.0.9-py3-none-any.whl`,
  `/assets/fhirpath.duckdb_extension.wasm`, and
  `/assets/cql.duckdb_extension.wasm` with HTTP 200.

## 3. Test Coverage

- `python3 -m pytest fhir4ds/ -x --tb=short`: PASS,
  `7925 passed, 7 skipped, 9 warnings`.
- Focused artifact regression slice:
  `python3 -m pytest fhir4ds/tests/test_version.py fhir4ds/cql/duckdb/tests/test_valueset_udf.py fhir4ds/cql/duckdb/tests/test_cpp_valueset_cache.py fhir4ds/sources/tests/unit/test_filesystem.py fhir4ds/sources/tests/unit/test_base.py fhir4ds/sources/tests/unit/test_existing.py -q --tb=short`:
  PASS, `126 passed`.
- `web/website npm run typecheck`: PASS.
- `web/website PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001/ npm run test:e2e`:
  PASS, `17 passed`.
- Initial unqualified `npm run test:e2e` failed because Playwright reused an
  unrelated app already listening on port 3000. Fixed
  `web/website/playwright.config.ts` so `PLAYWRIGHT_BASE_URL` controls both
  the test `baseURL` and the served host/port; documented the guardrail in
  `web/website/AGENTS.md`.

## 4. Conformance Report

```text
ViewDefinition            | 134      | 134      |  100.0%
FHIRPath (R4)             | 935      | 935      |  100.0%
CQL                       | 1706     | 1706     |  100.0%
DQM (QI Core 2025)        | 47       | 47       |  100.0%
OVERALL COMPLIANCE        | 2822     | 2822     |  100.0%
```

Full filtered conformance output is in `.temp/release/conformance_summary.log`.

## 5. Final GO / NO-GO Recommendation

**GO** for the 0.0.9 Python/package/website release-prep candidate. Blockers
are empty after the Playwright configuration fix. Residual operational note:
if C++ or WASM extension source changes before final publication, rerun the
pinned Emscripten WASM extension rebuild in an environment with `emcmake`,
`emmake`, and `emcc` available.
