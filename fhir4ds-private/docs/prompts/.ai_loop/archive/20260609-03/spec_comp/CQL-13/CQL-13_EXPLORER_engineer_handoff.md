# Engineer Handoff - CQL-13 EXPLORER

## Triage

| Issue | Severity | Category | Status |
| --- | --- | --- | --- |
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fix

Resolved `QA-001` by replacing translated numeric Date/Time component substring extraction with the existing validated `dateComponent` helper. This fixes the class of timezone-suffixed DateTime/Time inputs where a requested millisecond component is absent, for example `millisecond from @2024-01-01T10:00:00+05:00`.

The direct helper already returned SQL NULL for missing precision; translated CQL now uses the same semantic boundary instead of slicing `05:` from the timezone offset and raising a DuckDB cast error.

## Files Changed

- `fhir4ds/cql/translator/expressions/_temporal_components.py`
- `fhir4ds/cql/duckdb/tests/integration/test_datetime_part1_parity.py`
- `AGENTS.md`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql13_explorer_probe.py`

## Validation

- `python3 .temp/qa/cql13_explorer_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part1_parity.py -q` passed, 13/13.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q` passed, 5/5.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_datetime_operators -q` passed, 246/246.
- `python3 conformance/scripts/run_all.py` passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes

No new issues were discovered during remediation.
