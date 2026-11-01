# Engineer Handoff — FP-20 HISTORIAN (iteration 1, 2026-08-19)

## QA-001 (MEDIUM) — RESOLVED
Root cause: missing uri-family field-type metadata on both engines plus an
exact-only subtype check in the native is() string-subtype branch.
- fhir4ds/fhirpath/models/r4/fhir_path_to_type.json: added
  ".profile": "canonical", ".source": "uri" (data-driven; canonical->uri
  chain already in type2Parent.json).
- extensions/fhirpath/src/fhirpath/evaluator.cpp: fhirFieldType now maps
  profile -> "canonical" (was "uri", spec-wrong) and adds source -> "uri";
  the string-subtype is-branch now honors fhirTypeIsA for non-exact `is`
  (canonical/url/uuid/oid -> uri per R4, pinned by fixture testTypeA4),
  while `as`/`ofType` stay exact-only per FP-15 fixture pin
  (testFHIRPathAsFunction11).
- Extension rebuilt (make fhirpath_loadable_extension) and redeployed to
  fhir4ds/fhirpath/duckdb/extensions/ + site-packages; verified through the
  reloaded extension (fresh process).
- Regression test: fhir4ds/fhirpath/duckdb/tests/integration/
  test_uri_type_reflection_parity_fp20.py (4 dual-path tests, all passing).

## QA-002 / QA-003 (LOW) — INTENDED
Documented in AGENTS.md (NOT A BUG registry / known approximation):
2018Sep grammar has no non-empty literal lists; `.system`->uri shared
approximation.

## QA-004 (MEDIUM) — DEFERRED (pre-existing, out of chunk scope)
Full integration parity suite (~164 failures) is PRE-EXISTING: 97
arithmetic parity failures also occur with the committed binary. The
committed fhirpath.duckdb_extension is stale vs campaign evaluator.cpp
(rebuilding fixed 15 arithmetic tests). Same drift family as FP-18 QA-007 /
FP-19 QA-003 / FP-20 QA-005 — milestone review. NOTE: concurrent sibling
campaign sessions race on the shared binary path and git index; this launch
re-verified final state after such a race overwrote its edits mid-run.

## Validation
- Focused: test_uri_type_reflection_parity_fp20.py 4/4;
  test_environment_context_semantics_fp20.py 4/4; dual-path probes
  fp20_historian{2,4}: 67 exprs, 0 parity diffs.
- Gate: conformance/scripts/run_all.py = 2832/2832
  (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47). No regression.
