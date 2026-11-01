# Release Readiness Report: 0.0.7

## 1. Build Status

- Native FHIRPath extension: rebuilt successfully with `cmake --build extensions/fhirpath/build/release`.
- Native CQL extension: rebuilt successfully with `cmake --build extensions/cql/build/release`.
- Python artifacts: rebuilt successfully with `hatch build`.
- WASM side modules: rebuilt successfully in Docker using `emscripten/emsdk:3.1.56`; refreshed:
  - `web/wasm-demo/public/extensions/fhirpath.duckdb_extension.wasm`
  - `web/wasm-demo/public/extensions/cql.duckdb_extension.wasm`
- Web artifacts:
  - `web/wasm-demo` production build passed.
  - `web/website` Docusaurus production build passed.
  - `web/website/static/wasm-app` refreshed from the final `web/wasm-demo/dist`.

## 2. Artifact Gate

- Wheel: `dist/fhir4ds_v2-0.0.7-py3-none-any.whl` (9,663,759 bytes).
- Sdist: `dist/fhir4ds_v2-0.0.7.tar.gz` (9,261,514 bytes).
- Wheel metadata:
  - Name: `fhir4ds-v2`
  - Version: `0.0.7`
  - DuckDB dependency: `duckdb==1.5.2`
  - Includes `numpy` and `pint>=0.21.0`
  - Includes bundled native extension files for FHIRPath and CQL.
- Clean install gate:
  - Fresh venv installed the wheel with dependencies.
  - Import came from venv site-packages, not the checkout.
  - `fhir4ds.__version__ == "0.0.7"`.
  - `fhir4ds.register()` is idempotent and reported `{"fhirpath_cpp": True, "cql_cpp": True}`.
  - Representative FHIRPath, `ToQuantity`, valueset cache, and `in_valueset` calls passed.
  - Clean venv `pip check`: no broken requirements.
- Collision gate:
  - Pre-existing `fhirpath_text` function did not crash registration.
  - FHIRPath native was skipped on that connection, CQL native remained usable.
- Unsupported DuckDB gate:
  - Forced `duckdb==1.4.2` reported `{"fhirpath_cpp": False, "cql_cpp": False}`.
  - Python fallback handled representative FHIRPath and `ToQuantity` calls.
  - `pip check` correctly reported the intentional DuckDB version conflict.

## 3. Test Coverage

- Full package pytest: `7654 passed, 5 skipped, 9 warnings`.
- Code review focused gate: `124 passed`.
- WASM demo Playwright gate: `22 passed`.
- Website Playwright gate: `17 passed`.
- WASM static validation: passed with `--skip-load`; direct Node side-module `LOAD` remains unsuitable because DuckDB-WASM `dlopen` can deadlock in Node worker threads.
- Benchmark dry-run: DQM report validated `47/47`; baseline not updated.

## 4. Conformance Report

`python3 conformance/scripts/run_all.py` completed successfully:

| Specification | Passed | Total | Rate |
| --- | ---: | ---: | ---: |
| ViewDefinition | 134 | 134 | 100.0% |
| FHIRPath (R4) | 935 | 935 | 100.0% |
| CQL | 1706 | 1706 | 100.0% |
| DQM (QI Core 2025) | 47 | 47 | 100.0% |
| Overall | 2822 | 2822 | 100.0% |

## 5. Final GO / NO-GO Recommendation

GO for the 0.0.7 release.

All release-blocking gates passed: native builds, WASM rebuilds, Python artifacts, clean install, public API smoke, fallback behavior, full conformance, full package pytest, browser runtime tests, website integration tests, and benchmark dry-run validation.
