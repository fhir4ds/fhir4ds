# Engineer Handoff: CQL-19 HISTORIAN

## Triage

| Issue | Severity | Category | Status |
|---|---:|---|---|
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fix

Resolved `QA-001` by updating the direct CQL list helper surface in `fhir4ds/cql/duckdb/macros/list.py`.

Root cause: interval literals are transported through SQL as JSON strings. The list helper stack already recognized clinical values and Quantity JSON, but interval-shaped JSON fell through to raw SQL/VARCHAR equality. That made semantically equal intervals with different authored boundaries, such as `Interval(1, 6]` and `Interval[2, 6]`, compare unequal inside list operators.

Spec basis: CQL list equality, distinct, proper inclusion, and union use element equality semantics; CQL interval equality uses semantic interval boundaries, including effective boundaries for open endpoints.

Implementation:

- Added `CQLIntervalValueHasShape(...)`.
- Routed `CQLListElementEqual(...)` interval pairs to `intervalEquals(...)`.
- Routed `CQLListElementEquivalent(...)` interval pairs to `intervalEquivalent(...)`.
- Left mixed interval/non-interval comparisons as `false`.
- Added regression coverage in `test_list_part2_parity.py` for translated and direct helper behavior across forced Python fallback, native-loaded registration, and no-Python C++.

## Validation

- `.temp/qa/cql19_historian_probe.py`: PASS.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py -q`: 16 passed.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_list_operators -q`: 212 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`: full baseline preserved, 2822/2822 overall.

## Files Changed

- `fhir4ds/cql/duckdb/macros/list.py`
- `fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql19_historian_probe.py`

No new issues were discovered during remediation.
