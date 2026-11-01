# Engineer Handoff - CQL-09 HISTORIAN

Resolved issue:
- `QA-001` HIGH: ordered comparison operators over unsupported structural
  operands no longer fall through to DuckDB native ordering.

Code changes:
- Added `_is_unsupported_ordered_comparison_operand()` in
  `fhir4ds/cql/translator/expressions/_operators.py`.
- Routed `<`, `<=`, `>`, and `>=` over statically known Ratio, List, Tuple,
  Interval, Code/Concept, ValueSet, and CodeSystem operands to SQL NULL before
  Quantity, interval, or generic SQL fallbacks.
- Added native-loaded and forced Python fallback parity coverage in
  `fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py`.
- Updated `extensions/cql/AGENTS.md` with the ordered-comparison guardrail.

Validation:
- `.temp/qa/cql09_historian_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py -q`
  passed: 7/7.
- Official comparison parser category passed: 198/198.
- `python3 conformance/scripts/run_cql.py` passed: 1706/1706.
- `python3 conformance/scripts/run_all.py` passed: ViewDefinition 134/134,
  FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

New issues discovered:
- None.
