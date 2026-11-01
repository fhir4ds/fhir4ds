# Architect Handoff — FP-20 HISTORIAN (iteration 1, 2026-08-19)

## Golden Standard (scoped to this chunk)
1. Dual-engine lockstep: every §9-§12 semantic (env vars, type(), is/as/ofType,
   type metadata) must behave identically on native C++ and Python fallback,
   pinned by parity tests.
2. Model knowledge is data-driven: field->type mappings belong in
   models/r4 JSON metadata; hand-curated lists in evaluator.cpp are tolerated
   legacy but must stay aligned with the JSON tables.
3. Fixtures outrank spec prose (as/ofType exact-match for FHIR primitives,
   testTypeA4 uri-family subtype chain for is).
4. §12 conformance is against the official 2018Sep N1 grammar.

## Audit of this iteration's fix (QA-001)
- Conforms to invariants 1-3: JSON suffix entries + native fhirFieldType
  alignment + subtype-aware is(); parity locked by
  test_uri_type_reflection_parity_fp20.py; conformance gate 2832/2832.
- Remaining drift (logged, not fixed here): native fhirFieldType is still a
  hand-curated field-name list parallel to fhir_path_to_type.json — the
  known dual-heuristic seam already on the FP-20 milestone-review docket
  (QA-004/QA-005 family). Recommended fix order for the reconciliation
  chunk: (1) regenerate native field-type tables from models/r4 metadata,
  (2) reconcile the 4 pinned parity drift tests, (3) repair the stale
  committed binary vs source drift (~15 arithmetic parity tests fail with
  the committed binary but pass after rebuild).

## QA Quality Gate
PASS — no veto. The HISTORIAN pass went beyond the SKEPTIC's probes
(uri-family field typing, §12 literal/grammar verification against the
downloaded official grammar, trace/type()/logical-operator spec quotes),
found a genuine parity+spec bug the SKEPTIC missed, and verified every
surprising behavior against primary spec text before logging.

## Operational finding (new)
Concurrent sibling campaign sessions share this working tree and the
deployed binary path; mid-launch, a race overwrote this session's
evaluator.cpp edits and deadlocked the git index (stray index.lock +
stuck `git` processes). Inner launches must verify file markers and
re-verify through the reloaded extension before concluding. Recorded in
AGENTS.md.

## Issue summary
QA-001 MEDIUM RESOLVED; QA-002/QA-003 LOW INTENDED; QA-004 MEDIUM DEFERRED
(pre-existing drift family). Zero non-terminal CRITICAL/HIGH/MEDIUM.
Clean exit at iteration 1 (min_iterations=1).
