# Release Readiness Report

Target version: `0.0.6`
Wheel: `fhir4ds_v2-0.0.6-py3-none-any.whl`

## 1. Build Status

Native:
- `cmake --build build/release` passed for `extensions/fhirpath`.
- `cmake --build build/release` passed for `extensions/cql`.
- Rebuilt native artifacts were copied into the Python package extension directories.

WASM:
- `cmake --build build/wasm_eh` passed for `extensions/fhirpath` with Emscripten on `PATH`.
- `cmake --build build/wasm_eh` passed for `extensions/cql` with Emscripten on `PATH`.
- Rebuilt WASM artifacts were copied to `web/wasm-demo/public/extensions/`.
- `web/wasm-demo` was rebuilt and synced to `web/website/static/wasm-app/`.

Wheel:
- `python3 -m hatch build` passed.
- Built wheel: `dist/fhir4ds_v2-0.0.6-py3-none-any.whl`.

## 2. Artifact Gate

Wheel metadata:
- Required dependencies present: `duckdb==1.5.2`, `numpy`, `pint>=0.21.0`.
- `duckdb==1.5.2` is intentionally stricter than the previous compatible range because the bundled DuckDB extensions are built for DuckDB `1.5.2`.
- Bundled native artifacts present:
  - `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
  - `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`

Clean supported install:
- Fresh venv: `/tmp/fhir4ds-clean-venv`.
- Installed from the wheel outside the checkout.
- `fhir4ds.__file__` resolved inside venv `site-packages`.
- `pip check` passed.
- `fhir4ds.register(con)` returned `{"fhirpath_cpp": True, "cql_cpp": True}` on supported DuckDB `1.5.2`.
- Native-backed smoke checks passed for `fhirpath_text`, `fhirpath_number`, `quantityValue`, `cql_valueset_cache_clear`, `cql_valueset_cache_add`, `cql_valueset_cache_size`, and `in_valueset`.

Public API matrix:
- `fhir4ds.create_connection()` passed.
- `fhir4ds.create_connection(valueset_cache=...)` passed.
- `fhir4ds.register(con)` passed.
- `fhir4ds.register(con, valueset_cache=...)` passed.
- Repeated `fhir4ds.register(con)` calls passed.

Collision behavior:
- Pre-created `fhirpath_text` collision did not crash registration.
- Registration returned `{"fhirpath_cpp": False, "cql_cpp": True}` and preserved the preexisting function.

Unsupported DuckDB fallback:
- Fresh venv: `/tmp/fhir4ds-unsupported-venv`.
- Forced `duckdb==1.4.2` after wheel install.
- Native extensions did not load: `{"fhirpath_cpp": False, "cql_cpp": False}`.
- Python fallback smoke checks passed for representative FHIRPath and CQL UDF calls.

WASM wheel checksum:
- SHA256 matched across all copied wheels:
  - `dist/fhir4ds_v2-0.0.6-py3-none-any.whl`
  - `web/wasm-demo/public/fhir4ds_v2-0.0.6-py3-none-any.whl`
  - `web/wasm-demo/dist/assets/fhir4ds_v2-0.0.6-py3-none-any.whl`
  - `web/website/static/wasm-app/assets/fhir4ds_v2-0.0.6-py3-none-any.whl`
- Checksum: `3438212cb54e00d7bb22ceea3e3c84a6c3c103e5315dccfc34327c8adc15339b`.

## 3. Test Coverage

Unit and integration:
- `python3 -m pytest fhir4ds/ -x --tb=short | tail -n 100`
- Result: `7461 passed, 5 skipped, 9 warnings in 437.07s`.

Focused artifact regressions:
- `python3 -m pytest fhir4ds/cql/duckdb/tests/test_valueset_udf.py fhir4ds/cql/duckdb/tests/test_cpp_valueset_cache.py fhir4ds/sources/tests/integration/test_integration.py fhir4ds/sources/tests/unit/test_filesystem.py -q --tb=short`
- Result: `103 passed in 2.09s`.

Website E2E:
- `npm run build` in `web/website` passed.
- `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001/ npx playwright test tests/wasm-demo-wc.spec.ts tests/demo.spec.ts`
- Result: `17 passed`.

WASM demo E2E:
- `npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts tests/e2e/cms-measures.spec.ts`
- Result: `22 passed`.

Benchmark artifact gate:
- `python3 benchmarks/run_comparison.py --runs 1 --skip-cr`
- Result: 47/47 cql-py 2025 QI-Core measures executed at `100.0%` accuracy.
- Regenerated `benchmarks/COMPARISON.md` and `benchmarks/output/summary_stats.json`.

Repository cleanup:
- Removed generated `__pycache__`, `.pytest_cache`, and `.omc` cache directories outside active work areas.

## 4. Conformance Report

Verbatim Phase 4 gate snapshot:

```text
Running 16 CQL test files...
>>> Discovering DQM measures (suite: 2025)...
Suite timings:
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

## 5. Final GO / NO-GO Recommendation

GO.

All release gates passed:
- Native, WASM, and wheel builds completed.
- Clean install, native extension loading, unsupported DuckDB fallback, collision behavior, public API matrix, and WASM wheel checksum passed.
- Full pytest, focused artifact tests, website E2E, WASM demo E2E, benchmarks, and conformance gates passed.
- ViewDefinition, FHIRPath, CQL, and DQM conformance are all at `100.0%`.

Blockers: none.
