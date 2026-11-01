# Engineer Handoff — CQL-22 EXPLORER launch (iteration 1)

## Triage
- QA-001 MEDIUM SPEC_VIOLATION → CONFIRMED (reproducer: dual-engine probe + new test).
- QA-002 LOW INTENDED (informational channel by design) — no action.
- QA-003 LOW UNCONFIRMED (error-text cosmetics, spec-silent) — no action.

## QA-001 fix (RESOLVED)
Root cause (fhir4ds/cql/translator/expressions/_query.py, _translate_query):
1. For a query whose source is a scalar fhirpath_text/fhirpath navigation
   (`Patient.name N`), the WHERE application CASE-wrapped the whole list.
2. The subsequent RETURN clause list_transform path (`_did_list_transform`)
   rebuilt the result from the raw source call and discarded that CASE —
   the where clause vanished from the final SQL (silent unfiltered results,
   swallowed Error-severity Message raises per CQL Appendix B).

Fix (same file, two edits):
- New `_defer_where_to_list_transform` flag: when the source is
  fhirpath_text/fhirpath AND a return clause exists, skip the scalar CASE
  wrap (CQL 1.5 §9: where filters the elements the query returns).
- The list_transform path now translates the where inside the same lambda
  scope (alias bound to `_lt_<alias>`) and applies it per element:
  list_filter before list_transform, or a WHERE clause in the UNNEST+list()
  variant when the where/return body contains subqueries (DuckDB lambda
  restriction honored).

Resulting SQL for the reproducer:
list_transform(list_filter(from_json(fhirpath(_pt.patient_resource,'name'),'["VARCHAR"]'),
  _lt_N -> CQLMessage(TRUE, LIST_EXTRACT(from_json(fhirpath(_lt_N,'given'),'["VARCHAR"]'),1)='Ann','F','Error','first given not Ann')),
  _lt_N -> fhirpath_text(_lt_N,'given'))
— per-element filtering and the Error raise now surface on BOTH engine modes.

Regression test: test_cql_message_where_clause_in_navigation_query_applies_per_element_cql22_explorer
in fhir4ds/cql/duckdb/tests/integration/test_message_parity.py (py + cpp).

## Validation (Recovery Gate)
- Focused: test_message_parity.py 13/13; test_nullological_parity.py 15/15;
  aggregate + list_part2 parity (see validation log; no failures).
- CQL unit: 1610 passed / 2 failed — both failures (test_audit_mode.py
  TestMinMaxAttribution arg_min/arg_max) bisected to PRE-EXISTING on the
  cumulative uncommitted tree (persist with this launch's fix disabled);
  conformance gate unaffected.
- Master gate fresh on FINAL tree: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706 (errors/messaging fixtures 4/4), DQM 47/47 first pass —
  OVERALL 2832/2832 (baseline holds).
- Binaries unchanged (translator-only): cql.duckdb_extension
  c5b22d58310c1eb7bafa17ce7877f989, fhirpath 57d0634b6ee6eddee9fc06a1355bef5a;
  repo bundle == ~/.local site-packages.
- No commits made; all changes left in the working tree.
