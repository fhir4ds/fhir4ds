# Engineer Handoff - CQL-18 SKEPTIC

Implemented targeted remediation for the three QA findings.

Changes:

- Added CQL list equality SQL macros in
  `fhir4ds/cql/duckdb/macros/list.py`: `CQLListElementEqual`,
  `CQLListContainsEq`, `CQLListDistinctEq`, `CQLListExceptEq`,
  `CQLListIntersectEq`, `CQLListHasAllEq`, and `CQLListEqualEq`.
  The element helper treats nulls and compatible Quantity values according to
  CQL semantics and guards mixed non-numeric scalar types as false instead of
  letting DuckDB attempt implicit casts.
- Routed translated list `contains`, `in`, `includes`, `included in`,
  `except`, `intersect`, `=`, and `!=` through those helpers in
  `fhir4ds/cql/translator/expressions/_operators.py`.
- Kept official `IndexOf(..., null)` null propagation while routing normal
  `IndexOf` through CQL element equality in
  `fhir4ds/cql/translator/expressions/_functions.py`.
- Marked the new list helper functions as list-valued for downstream interval
  dispatch in `fhir4ds/cql/translator/expressions/_temporal_intervals.py`.
- Added regression coverage in
  `fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py`,
  `fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py`, and
  `fhir4ds/cql/duckdb/tests/test_list_udfs.py`.
- Fixed `.temp/qa/cql18_skeptic_probe.py` to force repo-root imports so script
  execution cannot accidentally import a stale installed `fhir4ds`.

Validation:

- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py fhir4ds/cql/duckdb/tests/test_list_udfs.py -q --tb=short`
  passed: 49 passed.
- `python3 -m pytest fhir4ds/cql/tests/official -q --tb=short -k CqlListOperators`
  passed: 424 passed, 2620 deselected.
- `python3 -m pytest fhir4ds/cql -q --tb=short` passed: 4976 passed, 5 skipped.
- `python3 conformance/scripts/run_all.py` passed: ViewDefinition 134/134,
  FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `python3 -m pytest -q --tb=short` passed: 7211 passed, 5 skipped.
- Targeted `git diff --check` passed.

All issues reached terminal `VERIFIED` status.
