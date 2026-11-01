# Engineer Handoff - CQL-19 SKEPTIC

## Issues Addressed

| Issue | Status | Summary |
| --- | --- | --- |
| QA-001 | RESOLVED | Direct `Length(NULL::INTEGER[])` now returns `0` while string/untyped null Length remains `NULL`. |
| QA-002 | RESOLVED | Direct and translated `Skip` / `Take` now reject statically known non-Integer counts. |

## Fixes

- Updated `fhir4ds/cql/duckdb/macros/string.py` so the shared `Length` macro preserves CQL list null semantics for typed list nulls without changing string null behavior.
- Updated `fhir4ds/cql/duckdb/macros/list.py` so `Skip` and `Take` reject non-integral direct macro counts instead of accepting DuckDB Decimal/String slice coercions.
- Updated `fhir4ds/cql/translator/expressions/_functions.py` and `_lists.py` so function-call and query-form `Skip` / `Take` reject statically known non-Integer count arguments before SQL generation.
- Added regression coverage to `fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py`.
- Updated `extensions/cql/AGENTS.md` with the CQL-19 SKEPTIC rerun lessons.

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/cql19_skeptic_probe.py` -> PASS.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py -q` -> 15 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py::TestCQLComplianceByCategory::test_list_operators -q` -> 212 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes For Architect

`docs/architecture/translator/AGENTS.md` is absent in this checkout. I used root `AGENTS.md`, `extensions/cql/AGENTS.md`, loop rules, and durable knowledge. No schedule/archive files were modified.
