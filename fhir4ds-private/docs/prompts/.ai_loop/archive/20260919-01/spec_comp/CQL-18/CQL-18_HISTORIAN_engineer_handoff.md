# Engineer Handoff — CQL-18 re-launch (HISTORIAN), iteration 1

All 4 CONFIRMED issues resolved; regression tests added; baseline holds.

## Fixes (all Python translator-level; no C++ changes)

- QA-001 (CRITICAL) alias-bound dynamic list defines:
  - `translator.py`: dynamic multi-valued property defines (`define G:
    Patient.name.given`) now promote to the list projection AND are marked
    `RowShape.PATIENT_SCALAR` + `List<Any>` + new
    `DefinitionMeta.stores_list_value` (also set for static SQLArray list
    defines), matching the static list-define shape every list operator
    already handles.
  - `_functions.py::_translate_aggregate_pre`: Count/Sum/Min/Max/Avg over a
    `stores_list_value` define aggregate over the stored list
    (len(list_filter(x IS NOT NULL)) / list_sum / list_min / list_max /
    list_avg) instead of COUNT(*) over the single-row CTE.
  - `_functions.py` IndexOf: skips the rows-to-list wrap (list-in-list,
    every lookup -1) for `stores_list_value` references.
  - New `_translate_first_last_list_define_pre` pre-translate: First/Last
    over a `stores_list_value` define LIST_EXTRACT the stored list (previously
    returned the whole list).
  - `_temporal_intervals.py::_is_list_operands` now recognizes
    `_is_list_returning_sql` operands (from_json list projections, LIST()
    subqueries) so list SQL never falls into interval dispatch.
- QA-002 (HIGH) both-dynamic `includes` / `included in`: `_operators.py`
  promotes both 2-arg `fhirpath_text` operands to list projections before the
  list gate (guarded by `_is_fhir_interval_expression` so Period-typed
  operands keep interval routing). A includes A is now true (§10.10).
- QA-003 (HIGH) First/Last over String: typed TranslationError (§10.8/§10.9
  have no String overload; previously First('final') → 'f').
- QA-004 (MEDIUM) multi-valued navigation over retrieve defines:
  `_property.py::_resource_rows_navigation` collapses Property chains rooted
  at a row-set define into one dotted path and, when any segment is
  multi-valued (new `FHIRSchemaRegistry.is_multi_valued_element`, prefix-
  walking schema cardinality), aggregates per-row lists into one flattened
  per-patient list: `flatten(LIST(from_json(fhirpath(...))))`. Count(O.
  component)=2, `'29463-7' in O.component.code.coding.code`=true. Sub-claim
  INTENDED: `O.component.code.code` is invalid FHIRPath navigation
  (CodeableConcept has no `code` child) — empty/false is spec-correct.

## Files changed
- fhir4ds/cql/translator/translator.py
- fhir4ds/cql/translator/context.py (DefinitionMeta.stores_list_value)
- fhir4ds/cql/translator/fhir_schema.py (is_multi_valued_element)
- fhir4ds/cql/translator/expressions/_operators.py
- fhir4ds/cql/translator/expressions/_temporal_intervals.py
- fhir4ds/cql/translator/expressions/_functions.py
- fhir4ds/cql/translator/expressions/__init__.py
- fhir4ds/cql/translator/expressions/_property.py
- Tests: fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py
  (3 new historian-relaunch tests, py+cpp parity)

## Validation
- Reproducer: .temp/qa/cql18_historian/repro_fix.py — all cases pass py==cpp.
- Focused: list part1+part2 parity 26/26; CQL unit 1612/1612;
  comparison parity included in focused run (175 total).
- Master gate (fresh, final tree): ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, OVERALL 2832/2832 — baseline holds.
- Extension binaries unchanged (Python-only fixes); md5 parity:
  cql.duckdb_extension 3e7d4167143e01907fdd8561db43b7d7 and
  fhirpath.duckdb_extension 57d0634b6ee6eddee9fc06a1355bef5a identical
  across repo bundle and ~/.local site-packages.

## Notes for Architect
- stores_list_value is the new single discriminator for "CTE value column
  holds a whole list"; consumers must not guess from List< cql_type alone
  (query-produced defines like `define Q: (from {1,2,3} X return X)` are
  List<Integer> but do NOT store a list value — this distinction caused the
  one mid-fix regression caught by test_list_part2_parity).
- Sum over Integer list returns Decimal-typed SQL list_sum result (6.0) —
  numeric equality holds; flag for a future Integer-preservation pass.
