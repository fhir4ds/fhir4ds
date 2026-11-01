# Engineer Handoff: CQL-09 SKEPTIC

Resolved all open QA issues.

Fixes implemented:
- QA-001: Added dedicated `between` translation with an explicit CQL null-argument guard before evaluating the lowered `>=`/`<=` comparisons.
- QA-002: Routed interval-valued `between` to `intervalIncludedIn(interval, intervalFromBounds(low, high, true, true))` instead of scalar interval equality.
- QA-003: Added `ratioCompare` and routed Ratio equality/equivalence through Ratio/Quantity semantics rather than raw JSON/string comparison.

Changed files:
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/udf/ratio.py`
- `fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql09_skeptic_probe.py`

Validation:
- `python3 .temp/qa/cql09_skeptic_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py -q` passed: 6/6.
- `python3 conformance/scripts/run_all.py | grep ...` passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No new issues discovered during remediation.
