# Engineer Handoff — CQL-12 (HISTORIAN), iteration 1

Triage:
- QA-001 MEDIUM OPAQUE_FAILURE — CONFIRMED. Combine over a chained property-list
  navigation lowered to scalar fhirpath_text and crashed at DuckDB bind time with
  an opaque BinderException on BOTH engines. FIXED with a typed translate-time
  guard.
- QA-002 LOW REFERENCE_ALIGNMENT — Split with a null separator: spec-silent,
  engine-consistent ('A B' single-element list). INTENDED, documented in
  fhir4ds/cql/AGENTS.md NOT A BUG registry.

QA-001 fix (root cause, no workarounds):
1. fhir4ds/cql/translator/expressions/_functions.py — in the Combine lowering step
   (step 6.6), after query-row folding, if the source argument is a SQLFunctionCall
   whose name starts with 'fhirpath_' (scalar extraction: chained navigation such
   as First([Patient]).name.given returns only the FIRST element as a scalar),
   raise a typed, actionable TranslationError mirroring the QA-004
   `[Resource].field` guard doctrine. This converts the runtime opaque binder
   crash into a clear translate-time failure. Deep fix (modelinfo chained typing
   producing real List<String>) remains the deferred ARCH-001 debt.
   Supported sources unaffected: literal lists, typed-null lists, folded query
   subqueries (EXPLORER doctrine), list_apply row shapes.
2. Regression test:
   fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py::
   test_cql_string_combine_scalar_fhirpath_source_fails_typed — asserts the typed
   TranslationError for the failing form and that supported Combine sources keep
   translating.

Validation (Recovery Gate):
- String parity suite: 9/9 passed (includes the prior SKEPTIC scalar-string Indexer
  regression test — fix holds).
- Full conformance suite: see architect handoff / GLOBAL_KNOWLEDGE row (fresh run
  executed this iteration).

No new issues discovered during remediation.
