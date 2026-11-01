# Engineer Handoff: CQL-19 EXPLORER List Operators Part 2

## Triage

| Issue | Severity | Category | Status |
| --- | --- | --- | --- |
| QA-001 | MEDIUM | SPEC_VIOLATION / TEMPORAL_UNCERTAINTY | RESOLVED |

## Root Cause

Generic list helper macros used scalar CQL equality helpers that return only
true/false for list membership and equality. Time literals are transported as
VARCHAR in DuckDB, so translated temporal list operations such as
`CQLListContainsEq(['T15:59:59.999'], 'T15:59:59')` treated partial Time
precision as a string mismatch instead of preserving the SQL NULL returned by
`cqlDateTimeEqual`.

## Fix

- Added temporal-specific helper macros in
  `fhir4ds/cql/duckdb/macros/list.py`:
  `CQLListTemporalElementEqual`, `CQLListContainsTemporalEq`,
  `CQLListHasAllTemporalEq`, and `CQLListEqualTemporalEq`.
- Updated `fhir4ds/cql/translator/expressions/_operators.py` so list
  `contains`, `in`, `includes`, `included in`, `properly includes`,
  `properly included in`, `=`, and `!=` use those temporal helpers only when
  the CQL AST proves both sides are temporal. Ordinary string lists remain on
  the generic list helpers.
- Added permanent regression coverage in
  `fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py`.
- Updated `extensions/cql/AGENTS.md`, `GLOBAL_KNOWLEDGE.md`, and
  `ARCHIVE_LOG.md` with the durable rule.

## Validation

- Fresh probe: `python3 .temp/qa/cql19_explorer_probe.py` -> passed.
- Focused list parity/UDF: 54 passed.
- Official CQL list category plus list parity/UDF cluster: 271 passed.
- Full conformance: 2822/2822 overall.
- Full pytest: 7218 passed, 5 skipped, 9 warnings.
- Targeted `git diff --check`: clean.
