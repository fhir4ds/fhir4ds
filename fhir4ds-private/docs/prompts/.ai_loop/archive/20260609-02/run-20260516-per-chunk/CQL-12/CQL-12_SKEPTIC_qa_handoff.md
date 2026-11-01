# QA Handoff - CQL-12 SKEPTIC

Chunk: CQL-12, CQL String Operators.

Personality: SKEPTIC.

Scope independently tested:
- Official XML string operator behavior in `fhir4ds/cql/tests/official/cql-tests/tests/cql/CqlStringOperatorsTest.xml`.
- Translated CQL execution through native-loaded DuckDB registration and forced Python fallback registration.
- Direct public DuckDB macro/UDF surface, including no-Python/browser-style registration where functions are available as SQL macros.
- Regression risk around empty lists, substring boundaries, wildcard-looking string operands, null search operands, and string bracket indexing.

Issues found:
- `QA-CQL12-SKEPTIC-001`: `Combine({})` and `Combine({}, '-')` returned `''` instead of `NULL`.
- `QA-CQL12-SKEPTIC-002`: `Substring` boundary cases returned `''` or a slice instead of `NULL`.
- `QA-CQL12-SKEPTIC-003`: translated `StartsWith`/`EndsWith` used SQL `LIKE`, so `%` and `_` were treated as wildcards.
- `QA-CQL12-SKEPTIC-004`: string bracket indexer lowered through list extraction and returned `''` at the end boundary.

All issues were reproduced before remediation and rechecked after fixes. No open QA issues remain for this personality.

Validation:
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py -q` -> 3 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py -q` -> 11 passed.
- `./build/release/test/unittest "*cql*"` from `extensions/cql` -> 662 assertions in 2 test cases.
- `python3 conformance/scripts/run_cql.py` -> 1706/1706 passed.
- `python3 conformance/scripts/run_all.py` -> 2822/2822 passed overall.
- `python3 -m pytest fhir4ds -q` -> 7178 passed, 5 skipped, 9 warnings.
