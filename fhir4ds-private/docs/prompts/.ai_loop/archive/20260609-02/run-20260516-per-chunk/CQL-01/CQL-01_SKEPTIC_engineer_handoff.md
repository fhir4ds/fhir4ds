# Engineer Handoff — CQL-01 SKEPTIC

Resolved all three QA issues.

Changes made:
- `fhir4ds/cql/translator/expressions/_query.py`: `is Any` now lowers to a non-null test; primitive literal type checks now resolve exact Integer-vs-Long matches at compile time instead of treating them as interchangeable.
- `fhir4ds/cql/translator/expressions/_operators.py`: unary negation now handles signed Integer/Long minima before positive-literal range validation.
- `fhir4ds/cql/translator/expressions/_core.py`: positive Long range validation added; Decimal literals with `raw_str` preserve exact SQL rendering.
- `fhir4ds/cql/translator/types.py`: `SQLLiteral.raw_sql` added for exact primitive literal rendering without changing the in-memory Python value.
- `fhir4ds/cql/duckdb/macros/conversion.py`: `ToInteger` now uses integer-string regex gating and `TRY_CAST`, returning NULL instead of rounding or raising.
- `fhir4ds/cql/duckdb/udf/conversion.py`: direct Python `ConvertsToInteger`, `ConvertsToLong`, and `ToLong` now enforce the CQL integer-string grammar and Boolean overloads.
- `fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py`: added regressions for Any type checks, primitive numeric boundaries, exact Decimal SQL rendering, direct Python conversion APIs, and native-vs-fallback DuckDB conversion parity.

Validation completed:
- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/cql01_probe.py`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py -q` — 4 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py -q` — 7 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py -k 'CqlTypesTest or ValueLiteralsAndSelectors or CqlTypeOperatorsTest' -q` — 195 passed, 2849 deselected
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/tests/unit/test_parser.py fhir4ds/cql/tests/unit/test_v2_expressions.py fhir4ds/cql/tests/unit/test_operator_type_dispatch.py -q` — 237 passed
- `cd extensions/cql && ./build/release/test/unittest "*cql*"` — 612 assertions passed
- `git diff --check` — passed

Full conformance summary is running and will be recorded by the architect phase.
