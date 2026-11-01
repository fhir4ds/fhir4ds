# CQL-03 EXPLORER (launch 2) — Remediation Engineer Handoff

All 6 issues CONFIRMED and RESOLVED. Dual-backend regression tests added to
`fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py`
(24 tests in that file now pass). Conformance gate: 2832/2832 (ViewDef 144,
FHIRPath 935, CQL 1706, DQM 47). CQL unit suite 4916 passed/4 skipped.

## Fixes

- **QA-001 (HIGH) temporal `.month`/`.year`/`.hour`/... property accessors → null.**
  Root cause: `_translate_property` lowered temporal component access on
  Date/DateTime/Time sources to `fhirpath_text(<ISO string>, 'month')`.
  Fix: new `_translate_temporal_component_property` hook in
  `fhir4ds/cql/translator/expressions/_temporal_components.py` (called early
  from `_property.py::_translate_property`) routes temporal-typed sources
  through the existing `_translate_date_component` (`dateComponent` UDF) path,
  per CQL 1.5 §09-b (property accessor ≡ `component from X`). Type gating via
  new standalone `_static_source_cql_type` (literals + ToTime/ToDate/
  ToDateTime FunctionRefs; `_infer_cql_type` is not on the ExpressionTranslator
  mixin stack). Also implemented `time from X` / `.time` DateTime Time-portion
  extraction (previously fell to the `Year()` fallback).
- **QA-002 (HIGH) temporal-literal define alias Binder error.** Root cause:
  static temporal literal defines emitted patient-correlated CTE lookups
  (`sub.patient_id = _pt.patient_id`) against patient-less literal CTEs.
  Fix: `_is_static_temporal_definition` (`_query.py`) + inlining choke point
  extension in `_core.py::_translate_identifier`, mirroring the CQL-02
  static-clinical inlining.
- **QA-003 (HIGH) seconds/milliseconds combined-decimal precision.**
  Spec: CQL 1.5.3 §1.6/§1.11 "seconds and milliseconds are combined and
  represented as a Decimal for the purposes of comparison... When
  milliseconds are null, they are combined as .0" (verified verbatim from
  cql.hl7.org/N1A 09-b-cqlreference). `@T10:00:00.0 = @T10:00:00` was null
  → now true; `.5 = no-ms` → false (certain). Fixed in BOTH engines:
  Python `_compare_at_min_precision` (udf/datetime.py, new
  `combined_seconds_ms` flag) and C++ `CompareTemporal`
  (extensions/cql/src/cql_extension.cpp). Extension rebuilt and deployed
  (md5 10eaecdb10d3e8fca597078fc94c999e across build, repo bundle,
  site-packages; ~/.duckdb cache cleared). SCOPE: the combined rule applies
  to public comparisons only; interval-boundary helper
  `_precision_aware_compare` (udf/interval.py) passes
  `combined_seconds_ms=False` because official fixture
  CqlIntervalOperatorsTest.xml DateTimeIncludedInNull pins interval-boundary
  second-vs-ms mismatch as uncertain (fixtures outrank prose).
  Stale in-repo pins updated with spec citations:
  test_temporal_complex_parity.py ToTime pin; test_list_part2_parity.py
  temporal-uncertainty expectations (now deterministic False/True per the
  combined-decimal rule; C++/no-Python parity verified).
- **QA-004 (MEDIUM) `.numerator + 5 'mg'` → null.** Root cause: Ratio
  accessor result lacked Quantity type at the arithmetic dispatch, which
  then misrouted to `dateAddQuantity`. Fix: `_is_cql_quantity_expr`
  (_operators.py) now recognizes `.numerator`/`.denominator` on
  Ratio-typed sources (via `_static_source_cql_type`, ToRatio-aware) so
  Quantity ± Quantity routes to `quantity_add`/`quantity_subtract`.
- **QA-005 (MEDIUM) `.timezoneOffset` parse error.** Fix: parser
  `_parse_identifier_name` accepts the TIMEZONE_FROM token as an identifier
  (cql.g4 lists 'timezoneoffset' as keywordIdentifier), and QA-001's hook
  routes it to `cqlTimezoneOffset`. Both casings parse; +02:00 → 2.0.
- **QA-006 (MEDIUM, discovered during QA-001 fix) `ToTime` stripped the
  leading T marker** producing non-canonical Time transport ('14' not
  'T14'), breaking component extraction/comparison on converted values.
  Fix: `ToTime` (udf/conversion.py) now always returns T-prefixed strings,
  matching the documented Time-string convention (TimeOfDay/Time literals).
  No C++ counterpart exists (Python supplement only); parity held.

## Files changed

Code: `fhir4ds/cql/translator/expressions/_temporal_components.py`,
`_property.py`, `_query.py`, `_core.py`, `_operators.py`,
`fhir4ds/cql/parser/parser.py`, `fhir4ds/cql/duckdb/udf/datetime.py`,
`udf/conversion.py`, `udf/interval.py`,
`extensions/cql/src/cql_extension.cpp` (+ rebuilt/deployed
`fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`).
Tests: `test_temporal_complex_parity.py` (4 new dual-backend tests),
`test_list_part2_parity.py` (spec-cited pin updates).

## Verification

- Reproducers (qa_handoff cases) pass on Python fallback AND native-loaded
  C++ connections.
- `pytest fhir4ds/cql/tests` → 4916 passed, 4 skipped.
- `pytest fhir4ds/cql/duckdb/tests/integration` → pass (see final summary).
- `conformance/scripts/run_all.py` → 2832/2832 (100%).
