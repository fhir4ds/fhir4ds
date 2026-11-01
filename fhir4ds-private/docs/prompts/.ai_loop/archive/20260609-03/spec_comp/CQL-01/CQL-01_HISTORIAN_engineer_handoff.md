# Engineer Handoff - CQL-01/HISTORIAN

## Resolved Issues
- QA-001 HIGH: scalar primitive CQL parameters lost defaults and declared type metadata by lowering through untyped `getvariable()` VARCHAR references.

## Fix
- Canonicalized translator parameter type names from AST type specifiers.
- Bound scalar parameter defaults as compile-time expressions, including explicit `default null`.
- Preserved supplied scalar runtime parameter bindings in population SQL.
- Cast unbound required runtime scalar parameter references according to declared primitive type.
- Extended primitive parity tests for scalar defaults and runtime population parameters.

## Validation
- `python3 .temp/qa/cql01_historian_probe.py`
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_primitive_parity.py fhir4ds/cql/tests/unit/test_lexer.py -q` -> 143 passed
- `python3 -m pytest fhir4ds/cql/tests/unit/test_parser.py fhir4ds/cql/tests/unit/test_gap_remediation.py fhir4ds/cql/tests/unit/test_v2_function_inlining.py -q` -> 179 passed
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > validation_summary.log && cat validation_summary.log` -> 2822/2822

## Notes
No new issues were discovered during remediation.
