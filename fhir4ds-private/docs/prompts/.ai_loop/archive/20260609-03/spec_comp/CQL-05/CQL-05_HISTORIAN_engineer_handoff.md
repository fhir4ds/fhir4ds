# Engineer Handoff - CQL-05 HISTORIAN

Resolved:
- `QA-001` HIGH, CQL structural `cast` strictness. The parser now preserves
  strict cast intent with `BinaryExpression.strict=True` for `cast X as T`.
  The translator keeps ordinary `X as T` null-returning, but wraps strict casts
  in the same type predicate used by `is T`; mismatches now raise
  `CQL strict cast failed` through DuckDB `error(...)`.

Changed files:
- `fhir4ds/cql/parser/ast_nodes.py`
- `fhir4ds/cql/parser/parser.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`
- `AGENTS.md`
- `.temp/qa/cql05_historian_probe.py`

Validation:
- `python3 .temp/qa/cql05_historian_probe.py`: passed
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py -q`: 24 passed
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > validation_summary.log && cat validation_summary.log`: overall 2822/2822

No new issues were discovered during remediation.
