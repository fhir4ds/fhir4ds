# Engineer Handoff - CQL-04 SKEPTIC

## Fixed

Resolved `QA-001` by correcting logical precedence in `fhir4ds/cql/parser/parser.py`.

- `parse_expression()` now starts at implication.
- `implies` now binds lower than disjunction.
- `or` and `xor` now share a single left-to-right disjunction level.
- `and` now binds tighter than disjunction and implication.
- `day of <expr>` / precision-of operands now parse only through `parse_type_expression()` so a following logical chain remains outside the temporal precision operand.

## Regression Coverage

Updated `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py` to execute translated CQL precedence cases on both:

- native-loaded DuckDB registration
- forced Python fallback registration

Coverage includes implication precedence, `or`/`xor` left-to-right associativity, parenthesized override behavior, and temporal precision followed by `and`.

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py -q` -> 4 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_cql.py` -> 1706/1706 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/ --tb=short` -> 4900 passed, 5 skipped
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_dqm.py` -> 47/47 measures passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` -> 2822/2822 overall; ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47

No C++ native code was changed, so no extension rebuild/copy was required.
