# Engineer Handoff - CQL-04 EXPLORER

Resolved `QA-001`.

Root cause: CQL logical operator translation passed operands through `ExprUsage.BOOLEAN`, but `ExpressionTranslator` did not have static CQL type inference available at that boundary. DuckDB then applied implicit SQL truthiness/coercion for integer operands.

Fix:
- Added a narrow static logical-operand validator in `fhir4ds/cql/translator/expressions/_operators.py`.
- The validator rejects concrete non-Boolean literals, list expressions, and typed definition aliases for `and`, `or`, `xor`, `implies`, and unary `not`.
- `null`, unknown/dynamic expressions, Boolean comparisons, Boolean functions, and Boolean aliases remain allowed.
- Lowered `between ... and ...` before generic operand translation so its internal parser `and` separator is not treated as a logical predicate.

Regression tests:
- Added invalid static operand coverage to `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py`.
- Existing native-loaded and forced Python fallback parity tests continue to pass.
