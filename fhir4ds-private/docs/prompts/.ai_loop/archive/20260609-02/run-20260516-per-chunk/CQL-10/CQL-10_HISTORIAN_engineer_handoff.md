# Engineer Handoff: CQL-10 HISTORIAN

## Changes

- `fhir4ds/cql/duckdb/udf/math.py`
  - Split and preserve time timezone suffixes for boundary helpers.
  - Route numeric strings through decimal boundary logic.
  - Preserve four-digit year-only strings as year-precision dates.
- `extensions/cql/src/cql/boundary.cpp`
  - Matched the C++ boundary implementation to the Python fallback for time suffix parsing and formatting.
  - Kept bare `HH:MM` and `T...` time detection working with negative offsets.
- `fhir4ds/cql/translator/expressions/_core.py`
  - Rejected offset-bearing `@T...` static literals as invalid CQL time literals, preserving official XML behavior.
- `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py`
  - Added direct native-loaded and forced Python fallback assertions for boundary numeric text and offset-bearing time strings.
- `fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py`
  - Added C++-only boundary assertions for numeric text and time suffixes.

The rebuilt native extension was copied into `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` so packaged native registration uses the updated binary.

## Notes

`HighBoundary` and `LowBoundary` direct helper string inputs are broader than static CQL literal syntax. `ToTime('T14:30:00.0Z')` and direct helper calls can accept offset-bearing time strings; static `@T...Z/+/-` literals should continue to fail translation because the official XML marks that grammar path invalid.

## Verification

- `cd extensions/cql && cmake --build build/release --config Release -j 8`
- `cd extensions/cql && ./build/release/test/unittest "*cql*"` passed `638 assertions`.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q` passed `15`.
- `python3 conformance/scripts/run_all.py` passed `2822/2822`.
- `python3 -m pytest fhir4ds -q` passed `7171`, with `5` skipped and `9` warnings.
