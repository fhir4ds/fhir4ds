# QA Handoff - CQL-12 HISTORIAN

Chunk: CQL-12, CQL String Operators.

Personality: HISTORIAN.

Scope independently tested:
- Official CQL string operator XML expectations across all CQL-12 string operators.
- CQL v1.5.3 regex semantics for `Matches`, `ReplaceMatches`, and `SplitOnMatches`, including single-line mode behavior.
- Direct public SQL macro behavior in forced Python fallback, native-loaded DuckDB registration, and no-Python/browser-style registration.
- Deprecated direct Python string UDF resilience where public callers may still use legacy names.

Issue found:
- `QA-CQL12-HISTORIAN-001`: regex string operators did not use single-line mode, so `.` did not match newline in `Matches`, `ReplaceMatches`, and `SplitOnMatches`.

The same pass also hardened deprecated `stringMatches` null-pattern handling and `stringReplace` null operands so direct legacy calls return NULL rather than raising. No open QA issues remain for this personality.

Validation:
- Official string operator matrix probe passed in forced Python fallback, native-loaded DuckDB, and no-Python/browser-style direct macro execution.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py -q` -> 4 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py -q` -> 12 passed.
- `./build/release/test/unittest "*cql*"` from `extensions/cql` -> 662 assertions in 2 test cases.
- `python3 conformance/scripts/run_cql.py` -> 1706/1706 passed.
- `python3 conformance/scripts/run_all.py` -> 2822/2822 passed overall.
- `python3 -m pytest fhir4ds -q` -> 7179 passed, 5 skipped, 9 warnings.
