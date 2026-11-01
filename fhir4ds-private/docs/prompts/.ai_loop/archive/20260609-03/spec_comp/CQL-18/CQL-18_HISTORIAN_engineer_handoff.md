# Engineer Handoff: CQL-18 HISTORIAN

Resolved issues:
- `QA-001` HIGH: `CQLListElementEqual` now treats Code/Concept-shaped JSON as structured clinical values before raw JSON comparison. Code equality compares component names, so JSON key order is irrelevant; optional component presence mismatches such as display on one side only return SQL NULL; display/version value differences remain false for equality. Concept equality compares display plus ordered Code lists through the same Code equality helper.
- `QA-002` HIGH: Quantity list equality and containment now preserve `quantityCompare(..., '==')` SQL NULL for incompatible dimensions instead of coalescing it to false. `CQLListContainsEq`, `CQLListHasAllEq`, and `CQLListEqualEq` now propagate unknown when no definitive true/false element comparison exists.

Changed implementation:
- `fhir4ds/cql/duckdb/macros/list.py`

Regression coverage:
- `fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py`

Validation:
- `python3 .temp/qa/cql18_historian_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py -q` passed: 8/8.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py -q` passed: 14/14.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_list_operators -q` passed: 212/212.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` passed: overall 2822/2822.

No new issues were discovered during remediation.
