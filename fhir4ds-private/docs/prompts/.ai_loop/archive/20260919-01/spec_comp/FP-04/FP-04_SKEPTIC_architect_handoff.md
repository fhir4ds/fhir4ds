# FP-04 SKEPTIC Architect Handoff (iteration 1, 2026-08-17)

## Scope audited
FHIRPath §5.2 (where/select/repeat/ofType) QA launch and its single fix.

## Golden-standard invariants applied
1. Dual-path parity: native C++ and Python fallback must produce
   byte-identical FHIRPath results on shared surfaces.
2. Type-test inference (is/as/ofType/type) must be a single shared root
   per engine and mirror the other engine's semantics (§5.2.4, §6.3.1,
   §6.3.3).
3. FHIR model knowledge in generic runtime paths must be curated
   metadata, not ad-hoc schema coupling (GLOBAL_RULES).
4. No silent fallbacks; fixes at root cause; focused regression tests.

## Audit of the fix (QA-001)
- Change is minimal and located at the correct root: one new helper
  `structuralFHIRComplexType()` in evaluator.cpp consumed by BOTH
  inference sites (fn_isType and type() reflection), eliminating the
  divergent blanket BackboneElement default.
- The curated backbone-field set {communication, component, compose,
  contact, expansion, item, link} is derived from
  models/r4/fhir_path_to_type.json (same precedent as the existing
  fhirFieldType table) — metadata-coupled, documented in-code.
- No test-driven hacks, no hint wrappers, no silent fallbacks.
- Drift risk logged in AGENTS.md: the two engines' structural inference
  orders must stay in lockstep; the new parity regression test guards it.

## QA Enforcer Gate
QA was NOT lazy: 5 pre-registered SKEPTIC hypotheses, spec fetched from
the normative N1 source, 105+ dual-path probe cases across four
batteries, blast-radius sizing before fixing, and one initially
suspicious finding correctly dispositioned as INTENDED via the spec's
own example (`is(System.String).not()`). No veto; RETRY_QA not set.

## Issue summary
- QA-001 MEDIUM — RESOLVED (fix + regression test + full validation).
- QA-002 LOW — INTENDED (terminal).
- Open CRITICAL/HIGH/MEDIUM issues: 0.

## Recommended fix order for next engineer
None. Clean exit at iteration 1 (min_iterations=1 met; zero non-terminal
CRITICAL/HIGH/MEDIUM issues).

## State hygiene
Issues tombstoned in evolution.json; details preserved in
qa_handoff.md/engineer_handoff.md and GLOBAL_KNOWLEDGE.md.
