# Engineer Handoff: FP-06 Remediation

## Triage

| Issue | Category | Status |
| --- | --- | --- |
| QA-001 | SPEC_VIOLATION | RESOLVED |
| QA-002 | SPEC_VIOLATION | RESOLVED |
| QA-003 | SPEC_VIOLATION | RESOLVED |

## Fixes

- Python core `to_integer()` now rejects Decimal inputs and only accepts Integer, Boolean, and regex-integer String inputs with 32-bit bounds.
- Native C++ `fn_toInteger()` and `fn_convertsToInteger()` now reject Decimal inputs, including `1.0`, and only parse strings when the effective type is String.
- Native C++ singleton enforcement now includes `iif()`, so multi-item input raises the same semantic error class that public DuckDB UDFs convert to empty/NULL outside strict mode.
- Direct helper API `fhir4ds.fhirpath.duckdb.functions.conversion.to_integer()` and `to_boolean()` now follow the FHIRPath §5.5.2/§5.5.3 conversion tables instead of Python truthiness/truncation.
- Rebuilt `extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension` and copied it to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

## Regression Coverage

- `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`: Decimal literal `toInteger()`/`convertsToInteger()` parity across native and Python fallback.
- `fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py`: native/Python fallback parity for multi-item `iif()` input.
- `fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py`: direct helper conversion tables.

## Validation

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q` -> 8 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py::TestToInteger fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py::TestToBoolean -q` -> 16 passed.
- `./extensions/fhirpath/build/release/test/unittest '*fhirpath*'` -> 114 assertions passed.
- `python3 conformance/scripts/run_fhirpath_r4.py` -> 935/935 passed.
- `python3 -m pytest fhir4ds/fhirpath -q` -> 1167 passed, 1 pre-existing warning.

## Residual Risk

No known open FP-06 issues remain. The direct helper module still contains older convenience behavior for other conversion families outside this chunk; those were not changed.

## Retry Remediation

Resolved `ARCH-001` by adding native C++ `isFHIRPathIntegerString()` validation before `std::stoll` in `fn_toInteger()` and `fn_convertsToInteger()`. This rejects leading/trailing whitespace and decimal strings while preserving `+1`/`-1`. Rebuilt and copied the bundled extension again.

Additional validation:

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q` -> 8 passed.
- `./extensions/fhirpath/build/release/test/unittest '*fhirpath*'` -> 114 assertions passed.
- `python3 conformance/scripts/run_fhirpath_r4.py` -> 935/935 passed.
- `python3 -m pytest fhir4ds/fhirpath -q` -> 1167 passed, 1 pre-existing warning.
