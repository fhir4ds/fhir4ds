# Engineer Handoff — CQL-12 (SKEPTIC), iteration 1

Triage:
- QA-001 HIGH SPEC_VIOLATION — CONFIRMED via probe4 (Fam[3] -> NULL both engines). Fixed.
- QA-002 LOW REFERENCE_ALIGNMENT — spec-silent, engine-consistent; INTENDED, documented in
  fhir4ds/cql/AGENTS.md NOT A BUG registry.

QA-001 fix (root cause, no workarounds):
1. fhir4ds/cql/translator/expressions/_functions.py — _definition_resource_cte_name now
   requires meta.shape == RowShape.RESOURCE_ROWS. Previously any define with
   has_resource=True (including scalar defines whose expression contains a Retrieve,
   e.g. `define Fam: First([Patient]).name.family`, shape=PATIENT_SCALAR) was
   list-indexed as resource rows, so any index > 0 returned NULL.
2. fhir4ds/cql/translator/expressions/_lists.py — _is_string_index_source: scalar
   defines (is_scalar=True) with cql_type String or Any now route through the public
   string `Indexer` macro (0-based, null out-of-range) per the pinned CQL-12
   string-indexer doctrine; typed non-String scalars and real RESOURCE_ROWS defines
   keep the previous lowering.
3. Regression test added:
   fhir4ds/cql/duckdb/tests/integration/test_string_operator_parity.py::
   test_cql_string_indexer_over_scalar_string_define — asserts Indexer-macro lowering
   for the scalar define, list_extract preservation for `define Obs: [Observation]`,
   and end-to-end values ('t'/'M'/NULL x3) via evaluate_measure + FHIRDataLoader on
   BOTH the native/C++ and Python-only engines.

Validation (Recovery Gate):
- conformance/scripts/run_all.py fresh run: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, OVERALL 2832/2832 — baseline held, no regressions.
- pytest: 1623 passed (string parity, wasm gate, cql unit) + 137 passed (list parity,
  macros tier1, list udfs).

No new issues discovered during remediation.
