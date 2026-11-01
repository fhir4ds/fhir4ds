# Engineer Handoff - CQL-11 HISTORIAN

Scope: CQL Arithmetic Operators Part 2 (`Maximum`, `Minimum`, `Modulo`, `Multiply`, `Negate`, `Precision`, `Predecessor`, `Power`, `Round`, `Subtract`, `Successor`, `Truncate`, `TruncatedDivide`) across translated SQL, native-loaded DuckDB registration, forced Python fallback registration, and C++-only/browser-style direct helper calls.

Resolved seven HISTORIAN findings:

- `Negate` now handles representational boundaries: `-(minimum Integer)` and `-(minimum Long)` lower to SQL NULL, and `-(minimum Decimal)` lowers to the representable maximum Decimal numeric literal rather than a quoted string or SQL double-negative.
- `predecessor of minimum Decimal` and `successor of maximum Decimal` now fold to NULL before helper execution, and Decimal min/max constants are emitted as numeric SQL literals.
- Static DateTime literal underflow/overflow for predecessor/successor is rejected at translation time, matching the already-invalid constructor cases.
- Native C++ `predecessorOf`/`successorOf` validates Time strings and returns NULL for malformed values such as `T25:00`.
- Python fallback `mathPower` catches `OverflowError` and returns NULL for unrepresentable power results, matching native C++.
- Dynamic FHIR choice Arithmetic Part 2 numeric paths use `fhirpath_number` for `div`, `Power`/`^`, `Round`, and `Truncate`; `valueInteger` works, while `valueString: "5"` no longer becomes numeric.
- Python fallback and native C++ `CQLPrecision` strip negative DateTime timezone offsets before counting precision digits.

Files changed:

- `fhir4ds/cql/duckdb/udf/math.py`
- `extensions/cql/src/cql/boundary.cpp`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` (rebuilt native extension)

Validation completed:

- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py -q` -> 5 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py -q` -> 13 passed.
- `./build/release/test/unittest "*cql*"` from `extensions/cql` -> 662 assertions in 2 test cases passed.
- `python3 conformance/scripts/run_cql.py` -> 1706/1706 passed.
- `python3 conformance/scripts/run_all.py` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `python3 -m pytest fhir4ds -q` -> 7176 passed, 5 skipped, 9 warnings.
