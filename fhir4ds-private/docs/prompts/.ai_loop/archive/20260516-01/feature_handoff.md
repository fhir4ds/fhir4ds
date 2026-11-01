# Feature Handoff: WASM CQL Complete Runtime Parity

Status: implemented and verified on 2026-05-16.

## Goal

Execute any CQL supported by the current fhir4ds Python translator in
DuckDB-WASM without Python DuckDB UDF fallback. Pyodide may translate CQL to
SQL; DuckDB-WASM execution must use only compiled extensions plus pure SQL
macros.

## Completed Work

- Added strict no-Python runtime helpers and translate-and-execute pytest gate.
- Added browser CQL SQL macro registration and wired it into DuckDB-WASM
  initialization.
- Implemented translator-required CQL runtime gaps in the C++ extension,
  including temporal comparison helpers, duration/uncertainty helpers,
  boundary/predecessor/successor overloads, age/week aliases, expand helpers,
  interval null/precision edge cases, and time/date serialization fixes.
- Rebuilt and copied native `cql.duckdb_extension`.
- Rebuilt and copied `cql.duckdb_extension.wasm`.
- Rebuilt `web/wasm-demo` and refreshed `web/website/static/wasm-app`.

## Acceptance Evidence

- Strict official CQL XML suite through no-Python C++/macro runtime:
  `1706/1706`, `FAILURE_COUNT: 0`.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py -q`:
  `2 passed`.
- `cd extensions/cql && ./build/release/test/unittest "*cql*"`:
  `612 assertions in 2 test cases`.
- `cd extensions/fhirpath && ./build/release/test/unittest "*fhirpath*"`:
  `114 assertions in 2 test cases`.
- `python3 -m pytest fhir4ds -q`:
  `6942 passed, 5 skipped, 9 warnings`.
- `python3 conformance/scripts/run_all.py`:
  `2822/2822`, `100.0%`.
- `cd web/wasm-demo && npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts`:
  `12 passed`.

## Residual Notes

Native development registration can still load Python fallback UDFs when the
Python package is available. That fallback is no longer part of the browser
acceptance contract: the strict no-Python runtime directly proves the C++/SQL
execution path for the full official CQL suite.

