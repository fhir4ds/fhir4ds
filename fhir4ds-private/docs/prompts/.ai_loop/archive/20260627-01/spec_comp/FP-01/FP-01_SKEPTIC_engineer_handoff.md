# Engineer Handoff - FP-01 SKEPTIC

## Issues
- `QA-001` RESOLVED, MEDIUM: DateTime literals with offsets beyond `+/-14:00` were accepted as valid in native DuckDB and forced Python fallback.

## Root Cause
- Python fallback `FP_DateTime.__new__` allowed timezone hours through `23`.
- Native C++ `parseDateTimeParts()` allowed timezone hours through `23`.
- `fhirpath_is_valid()` evaluates a minimal resource and should classify these semantic literal errors as invalid; result UDFs should continue returning empty/NULL for invalid temporal literals.

## Fix
- Added `hours < 14 || hours == 14 && minutes == 0` offset validation in:
  - `fhir4ds/fhirpath/engine/nodes.py`
  - `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- Added regressions in:
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py`
  - `extensions/fhirpath/test/sql/fhirpath.test`
- Rebuilt and copied the bundled native extension:
  - `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
  - `extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/fhirpath.duckdb_extension`

## Validation
- `python3 .temp/qa/fp01_skeptic_probe.py` - PASS
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py -q --tb=short` - 18 passed
- `./build/release/test/unittest '*fhirpath*'` - 714 assertions passed
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` - 2822/2822 overall

## Notes
- The lexer-level range check was intentionally not kept because it changed invalid constant expressions into parse/bind errors for result UDFs. The semantic evaluator check preserves the public empty/NULL behavior while making `fhirpath_is_valid()` false.
