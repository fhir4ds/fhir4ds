# Engineer Handoff — CQL-18 EXPLORER launch, iteration 1 (FIX phase)

All 5 CONFIRMED issues RESOLVED at root cause (Python translator layer; no C++
changes). NOTE: this FIX session resumed after an interruption; the fixes below
were completed in the working tree during this launch and fully re-validated
fresh by the resumed session.

## Fixes

- QA-001 (CRITICAL) deep 0..* navigation over retrieve-define aliases:
  `_property.py::_resource_rows_navigation` now marks its per-patient
  flattened-list subquery with `stores_patient_list`, and `translator.py`
  reclassifies such defines (`define CC: Obs.component.code.coding.code`) as
  PATIENT_SCALAR stored-list CTEs (same shape as static list defines), keeping
  the `_pt` correlation that the PATIENT_MULTI_VALUE wrap destroyed. All
  consumers (Count/First/contains/distinct/except/includes/intersect) now
  return correct per-patient values (P1=2, P2=1 counts verified).
- QA-002 (HIGH) chained list operators: `_temporal_intervals.py::
  _is_single_list_expr` recognizes list-producing SQL (CQLListExcept/
  Intersect/TemporalEq, flatten, list_value, list_slice, ...) so chained
  includes/included-in dispatch to the list-list overload instead of emitting
  subqueries inside table functions; `_operators.py::
  _promote_list_setop_scalar_operands` promotes scalar operands beside list
  operands (`CC except '8867-4'`) to singleton lists per App B list promotion.
- QA-003 (HIGH) includes/included-in null semantics: singleton overload now
  routes to the contains macro (null elements equal: `{null,1} includes null`
  → true, `null included in {1,null,3}` → true); list-list overload with a
  typed-null operand returns SQLNull (`{1,3} includes (null as List<Integer>)`
  → null at the expression level). Verified via list-wrap probes: `[None]`.
  The Boolean-define boundary flattening of null→false is the documented
  population presence-encoding convention (INTENDED at that layer).
- QA-004 (HIGH) `First(alias-of-distinct)`: `translator.py` marks a
  PATIENT_SCALAR List<-typed define whose translated SQL is list-returning
  (`define A2: distinct A_Lit`) with `stores_list_value` (helper
  `inference.py::_definition_result_is_list_returning`), so the existing
  First/Last LIST_EXTRACT pre-translate re-enters. First(A2) → 10.
- QA-005 (MEDIUM) heterogeneous list literals: `_lists.py::
  _validate_list_selector_common_type` raises a typed TranslationError at
  translate time for String/numeric/Boolean mixed literals (CQL 1.5 App B
  List selector common-type requirement) instead of a raw DuckDB
  ConversionException at execution.

## Regression tests
`fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py`
`test_explorer_qa001_deep_navigation_define_alias`,
`test_explorer_qa002_chained_list_operators`,
`test_explorer_qa003_includes_null_semantics`,
`test_explorer_qa004_first_through_two_alias_levels`,
`test_explorer_qa005_heterogeneous_list_literal_translation_error` (py+cpp
parity). 18/18 pass.

## Validation (fresh, this session)
- QA reproducer `.temp/qa/cql18e3_2026_08_22/followup.py`: all cases correct
  (incl. multi-patient MP cases); null-list list-list overload verified via
  `{ ({1,3} includes (null as List<Integer>)) }` → `[None]`.
- Focused: test_list_part1_parity 18/18; CQL unit 1612/1612.
- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, OVERALL 2832/2832 — baseline holds.
- Extension binaries unchanged (Python-only): cql.duckdb_extension
  md5 3e7d4167143e01907fdd8561db43b7d7, fhirpath.duckdb_extension
  md5 57d0634b6ee6eddee9fc06a1355bef5a.

## Files changed (code)
- fhir4ds/cql/translator/translator.py
- fhir4ds/cql/translator/inference.py
- fhir4ds/cql/translator/expressions/_property.py
- fhir4ds/cql/translator/expressions/_operators.py
- fhir4ds/cql/translator/expressions/_temporal_intervals.py
- fhir4ds/cql/translator/expressions/_lists.py
- (plus adjacent pre-existing working-tree edits from earlier CQL-18 launches)
