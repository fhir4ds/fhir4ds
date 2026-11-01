# Engineer Handoff: CQL-13 HISTORIAN

Issue remediated:
- `QA-001` HIGH: Public `cqlDurationBetween` / `cqlDifferenceBetween` accepted
  unsupported precision/unit strings and defaulted to day semantics.

Root cause:
- The Python fallback used `_PRECISION_INDEX.get(unit_key, 2)`.
- The C++ extension used `PrecisionFromName(...)` but fell back to
  `Precision::Day` when the lookup failed.
- Both paths therefore calculated uncertainty intervals for invalid unit text.

Fix:
- Added `_normalize_between_unit()` in `fhir4ds/cql/duckdb/udf/datetime.py`.
- Added explicit `!unit_precision` NULL returns in
  `extensions/cql/src/cql_extension.cpp`.
- Rebuilt and copied `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`.
- Added parity and no-Python regression coverage for invalid units.

Validation:
- `.temp/qa/cql13_historian_probe.py`: PASS.
- `test_datetime_part1_parity.py`: 12/12 passed.
- `test_wasm_cpp_surface.py`: 5/5 passed.
- Official DateTime operator category: 246/246 passed.
- Full conformance: 2822/2822 passed.

Next phase: ARCHITECT.
