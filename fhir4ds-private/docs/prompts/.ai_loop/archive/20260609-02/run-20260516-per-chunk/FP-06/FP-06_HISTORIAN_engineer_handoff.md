# Engineer Handoff - FP-06 HISTORIAN

Issue addressed:
- `QA-001` (MEDIUM, RESOLVED): native C++ source/binary drift for `iif()` multi-item input handling.

Fix:
- Restored the explicit `input.size() > 1` guard in `extensions/fhirpath/src/fhirpath/evaluator.cpp::fn_iif` before criterion or branch evaluation.
- Added a native SQL regression to `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt the native extension with `cmake --build build/release --config Release -j 8`.
- Copied the rebuilt extension to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
- Updated `extensions/fhirpath/AGENTS.md` with the source/binary drift lesson.

Validation:
- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/fp06_historian_probe.py | tail -n 8` -> `mismatch_count=0`.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q` -> 8 passed.
- `./build/release/test/unittest test/sql/fhirpath.test` from `extensions/fhirpath` -> 58 assertions passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py -q` -> 120 passed.
- `python3 conformance/scripts/run_fhirpath_r4.py` plus report parse -> 935/935 passed.

No new issues discovered.
