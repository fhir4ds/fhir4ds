# Engineer Handoff - CQL-18 EXPLORER

Resolved issue: `QA-001` HIGH.

## Root Cause

`CQLIndexOf` used a single filtered aggregate:
`WHERE CQLListElementEqual(item, elem)`. SQL filtering dropped `NULL`, so an
unknown CQL equality result was treated exactly like a known false comparison.
That made incompatible Quantity dimensions and clinical Code equality with a
missing optional component return `-1` instead of SQL `NULL`.

The translated query-list form had a second boundary error: `IndexOf((from ...
return ...), elem)` passed a row-producing `SELECT` into `CQLIndexOf`, causing
DuckDB to reject the macro expansion with an `UNNEST()` binder error.

## Fix

- Updated `fhir4ds/cql/duckdb/macros/list.py` so `CQLIndexOf`:
  - returns the first zero-based index whose element equality is true,
  - returns SQL `NULL` when no true match exists but at least one equality is
    unknown,
  - returns `-1` only when all candidate comparisons are known false.
- Updated `fhir4ds/cql/translator/expressions/_functions.py` so translated
  `IndexOf` folds SQL row sources into `COALESCE(list(value), [])` before
  invoking `CQLIndexOf`.
- Added direct and translated regression coverage in
  `fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py`.
- Updated durable CQL guidance in `AGENTS.md` and `extensions/cql/AGENTS.md`.

## Validation

- `.temp/qa/cql18_explorer_probe.py`: PASS
- `test_list_part1_parity.py`: 8 passed
- `test_list_part1_parity.py` + `test_list_part2_parity.py`: 14 passed
- Official `CqlListOperatorsTest`: 212 passed
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822

No new issues were discovered during remediation.
