# CQL-10 SKEPTIC Engineer Handoff

## Changes

- Updated `fhir4ds/cql/translator/expressions/_operators.py`.
- Added parity coverage in `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py`.
- Added date/time regression coverage in `fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py`.

## Implementation Details

- Numeric `+` now avoids the string concatenation branch when either operand is a numeric SQL literal, numeric cast, numeric arithmetic result, or `fhirpath_number` projection.
- Arithmetic casting now asks `_fhirpath_number_projection()` first, so dynamic FHIR `value` and `value.*` paths use typed numeric extraction rather than `fhirpath_text` plus `TRY_CAST`.
- Quantity plus/minus non-Quantity dispatch now returns NULL for definitely non-temporal scalar peers. Temporal or unknown aggregate/query peers still flow to `dateAddQuantity`/`dateSubtractQuantity`.
- FunctionRef temporal detection now includes Today, Now, and TimeOfDay for date/time plus Quantity arithmetic.
- `TimeOfDay()` comparison avoids the precision-aware DateTime UDF route because DuckDB renders `CURRENT_TIME` as offset-bearing time text that the DateTime UDF surface does not parse consistently.

## Verification

- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py -q` -> 6 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py -q` -> 3 passed.
- `python3 conformance/scripts/run_cql.py` -> 1706/1706.
- `python3 conformance/scripts/run_all.py` -> overall 2822/2822.
- `cd extensions/cql && ./build/release/test/unittest "*cql*"` -> 638 assertions passed.
- `python3 -m pytest fhir4ds -q` -> 7170 passed, 5 skipped, 9 warnings.
