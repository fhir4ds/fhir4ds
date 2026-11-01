# Architect Handoff — FP-03 SKEPTIC (iteration 1, 2026-08-17)

## Golden Standard invariants applied (scoped to this chunk)
1. FHIRPath semantics must be engine-agnostic: native C++ and the Python
   fallback must agree on every §5.1 surface (dual-path parity discipline).
2. The strict core may raise spec errors; DuckDB wrappers convert evaluation
   errors to empty/NULL for row resilience — errors and spec-mandated empty
   results are DISTINCT semantics and must not be conflated inside
   iteration functions.
3. `fhirpath_is_valid` validates expression validity, not result
   non-emptiness; execution type errors classify as valid.
4. Spec-mandated empty results (§6.2 partial temporal precision,
   calendar-vs-UCUM, offset temperatures, incompatible quantity dimensions)
   must remain empty — they are not type errors.
5. Fixes must be general (class of input), spec-cited, and free of
   fixture-specific hacks.

## Audit outcome
- QA-001 fix (native `throwIncompatibleComparison` + is_valid classifier
  entry) satisfies invariants 2/3/4/5: the two terminal incompatible-type
  sites throw the canonical message; all spec-mandated empty paths above
  them are untouched (verified by 5 dedicated controls); the message form
  mirrors the Python core so both classifiers agree. Minimal footprint:
  evaluator.cpp (2 sites + helper), fhirpath_extension.cpp (classifier).
- QA-002 fix (remove `FP_Time` from ordering coercion) aligns the fallback
  with the pinned String→Time Explicit-only convention while preserving the
  shared Date/DateTime string coercion — no engine-specific behavior
  introduced.
- No generalizability, abstraction, coupling, or test-hack violations found
  in the changes. No new Architecture Drift Log entries required.

## Structural observation (logged QA-003, LOW, INTENDED)
Cross-engine error-message contracts remain load-bearing
(`_is_valid_empty_result_error` in udf.py and `FhirpathIsValidFunction` in
fhirpath_extension.cpp both match message prefixes). This iteration added
one form, updated in lockstep on both surfaces — consistent with the
established pattern; typed error codes remain the stronger long-term design.

## QA Enforcer Gate
QA was NOT lazy: 116 pre-registered hypothesis cases + a 25-case
blast-radius battery + 2 focused batteries, spec text fetched from N1,
official R4 fixtures extracted and used as controls, dual-path execution
with the PYTHONPATH discipline. All 12 chunk items were probed. A suspected
`isDistinct` anomaly was correctly chased to ground truth (union dedup at
construction) instead of being filed blindly. No RETRY_QA.

## Validation evidence
- probe.py 116/116 parity; probe2.py 25/25 parity; corner batteries clean.
- `pytest fhir4ds/fhirpath/` → 1722 passed.
- Conformance: 2832/2832 (ViewDefinition 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held.

## State hygiene
Both RESOLVED issues archived to ARCHIVE_LOG.md ("Spec Compliance FP-03 —
FHIRPath §5.1 Existence, SKEPTIC"); evolution.json carries tombstones plus
one INTENDED observation. handoff compression: QA found 2 dual-path parity
bugs rooted in §6.2 error-vs-empty conflation (native) and Time-string
coercion (fallback); the engineer fixed both engines' surfaces surgically,
added 2 parity regression tests, rebuilt/redeployed the fhirpath extension,
and held the full conformance baseline.

## Exit
Iteration 1 ≥ min_iterations (1); zero non-terminal CRITICAL/HIGH/MEDIUM
issues remain. exit_reason=CLEAN, workflow=null. Control returns to the
outer spec-compliance orchestrator (FP-03 still needs HISTORIAN/EXPLORER
personalities per the 3-personality rotation).
