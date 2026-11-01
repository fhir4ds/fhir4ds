# FP-16 Remediation Handoff (iteration 1, 2026-08-18)

QA-001 (MEDIUM, SPEC_VIOLATION, FHIRPath §6.4.2/§6.4.3) → RESOLVED.
- Root cause: fhir4ds/fhirpath/duckdb/operators.py membership()/contains() helpers
  returned FHIRPathCollection([]) for multi-item singleton operands instead of raising,
  diverging from core engine (engine/invocations/collections.py) and native
  evaluator.cpp (identical messages already exist there and in the error-classification
  contract lists, so no new error-message entries were needed).
- Fix: raise FHIRPathError("in requires the left operand to contain at most one item") /
  ("contains requires the right operand to contain at most one item"); empty-operand
  §6.4 semantics preserved (left-empty in → empty; right-empty contains → empty).
- Regression test: tests/integration/test_collection_operator_parity.py::
  test_membership_helper_singleton_violations_raise_fhirpath_error (12/12 pass in file).
- Full unit suite run in background; conformance gate: ViewDefinition 144/144,
  FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832 — no regression.
- No C++ changes; no extension rebuild required (Python-only helper surface).
