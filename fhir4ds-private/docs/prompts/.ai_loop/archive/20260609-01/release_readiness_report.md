# Release Readiness Report - 0.0.8

## 1. Build Status

Native: PASS

- `cmake --build build/release` in `extensions/fhirpath`: PASS.
- `cmake --build build/release` in `extensions/cql`: PASS.

Wheel: PASS

- `python3 -m build --wheel --no-isolation`: built
  `dist/fhir4ds_v2-0.0.8-py3-none-any.whl`.
- Build hook bundled:
  - `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
  - `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`

WASM: PARTIAL / BLOCKED

- `web/wasm-demo` build: PASS.
- `web/website/static/wasm-app` refreshed from the rebuilt demo.
- Dist/public/static wheel checksums match:
  `4d147061ca6a97dcf9f1dcb0f6baa5d383e434637fa8dd77134168b3aa0c6a8f`.
- WASM side-module extension rebuild was not runnable because `emcmake`,
  `emmake`, and `emcc` are not available on `PATH`. Existing checked-in WASM
  extension files remain from June 4 and were not regenerated in this
  environment.

## 2. Artifact Gate

Wheel metadata: PASS

- Installed package metadata: `fhir4ds-v2==0.0.8`.
- Required dependency metadata present:
  - `duckdb==1.5.2`
  - `numpy`
  - `pint>=0.21.0`
- Bundled native artifacts present in the wheel.

Clean install: PASS

- Fresh virtualenv under `/tmp` installed
  `dist/fhir4ds_v2-0.0.8-py3-none-any.whl[measures]`.
- Installed imports resolved from virtualenv `site-packages`, not the checkout.
- Clean virtualenv `pip check`: no broken requirements.

C++ extension proof: PASS

- `fhir4ds.register(con)` on DuckDB 1.5.2 returned:
  `{'fhirpath_cpp': True, 'cql_cpp': True}`.
- Native-backed functions passed:
  `fhirpath_text`, `fhirpath_number`, `quantityValue`,
  `cql_valueset_cache_clear`, `cql_valueset_cache_add`,
  `cql_valueset_cache_size`, and `in_valueset`.

Public API matrix: PASS

- `fhir4ds.create_connection()`: PASS.
- `fhir4ds.create_connection(valueset_cache=...)`: PASS.
- `fhir4ds.register(con)`: PASS.
- `fhir4ds.register(con, valueset_cache=...)`: PASS.
- Repeated `fhir4ds.register(con)`: PASS.

Hostile connection collision: PASS

- Pre-created `fhirpath_text`; `fhir4ds.register(con)` did not crash and
  returned `{'fhirpath_cpp': False, 'cql_cpp': True}`.

Unsupported DuckDB fallback: PASS

- Separate virtualenv force-installed `duckdb==1.4.2`.
- `fhir4ds.register(con)` returned
  `{'fhirpath_cpp': False, 'cql_cpp': False}`.
- Python fallback handled `fhirpath_text`, `ToInteger`, and `AgeInYears`.

WASM wheel consistency: PASS

- `dist/`, `web/wasm-demo/public/`, and both website static wheel copies have
  matching SHA-256 checksums.

## 3. Test Coverage

Full package pytest: PASS

- `python3 -m pytest fhir4ds -q --tb=short`
- Result: 7,922 passed, 7 skipped, 9 warnings in 705.24s.
- Warnings were existing CQL official dataclass collection warnings, DQM
  DataFrame deprecation warnings, and one FHIRPath quantity test return warning.

Focused artifact pytest: PASS

- ValueSet cache/UDF, forced backend parity, source integration, and version
  consistency selection: 73 passed.

Website and demo: PASS

- `npm run build` in `web/wasm-demo`: PASS.
- WASM preview smoke:
  - `/`: 200
  - `/fhir4ds_v2-0.0.8-py3-none-any.whl`: 200
  - `/extensions/fhirpath.duckdb_extension.wasm`: 200
  - `/extensions/cql.duckdb_extension.wasm`: 200
- `npm run typecheck` in `web/website`: PASS.
- `npm run build` in `web/website`: PASS with the existing
  `vscode-languageserver-types` dynamic require warning.
- `npm run test:e2e` in `web/website`: 17 passed.

Benchmark comparison: PASS

- Current DQM report: 47/47 measures.
- Timing regressions: 0.
- Accuracy regressions: 0.
- Total measured time ratio: 1.045x against the refreshed 0.0.8 baseline.

Global environment dependency check: ENVIRONMENT LIMITATION

- `python3 -m pip check` in the shared environment fails only on unrelated
  global packages:
  `med-term-mcp`, `trl`, `pygobject`, `torch`, and `xformers`.
- No `fhir4ds-v2` conflict was reported.
- Clean release virtualenv `pip check` passed.

## 4. Conformance Report

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

NO-GO for public release from this environment.

Blocker:

- The required WASM side-module extension rebuild could not be performed
  because the pinned Emscripten toolchain is unavailable (`emcmake`, `emmake`,
  and `emcc` not found). Rebuild and validate
  `fhirpath.duckdb_extension.wasm` and `cql.duckdb_extension.wasm` in the
  pinned DuckDB-WASM/Emscripten environment before release.

All runnable Python package, native extension, artifact, clean-install,
conformance, benchmark, website, and Playwright gates passed.
