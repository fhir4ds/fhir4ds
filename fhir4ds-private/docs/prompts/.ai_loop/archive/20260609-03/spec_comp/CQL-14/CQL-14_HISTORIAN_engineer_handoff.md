# Engineer Handoff: CQL-14 HISTORIAN

## Triage

| Issue | Severity | Category | Status |
| --- | --- | --- | --- |
| QA-001 | HIGH | SPEC_VIOLATION | VERIFIED |

## Fix

Resolved `QA-001` in
`fhir4ds/cql/translator/expressions/_temporal_components.py`.

The translated `Time(...)` constructor now follows the official CQL Time
constructor rule that trailing null components represent unspecified precision.
Runtime translation selects the highest valid precision:

- `Time(12, null)` -> `T12`
- `Time(12, 30, null)` -> `T12:30`
- `Time(12, 30, 0, null)` -> `T12:30:00`
- `Time(12, null, 0)` -> SQL NULL

The change is scoped to the translator's Time component constructor and does not
alter direct public DuckDB helper/UDF registrations.

## Tests

- `python3 .temp/qa/cql14_historian_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q`
  passed: 10/10.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_datetime_operators -q`
  passed: 246/246.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`
  passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, OVERALL 2822/2822.

## Files Changed

- `fhir4ds/cql/translator/expressions/_temporal_components.py`
- `fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql14_historian_probe.py`

