# FP-05 EXPLORER Architect Handoff (2026-08-17, iteration 1)

## Golden Standard (chunk scope)

Invariants audited for §5.3/§5.4:
1. All subsetting/combining membership decisions route through the shared
   FHIRPath `=` equality helper — no per-function equality bypasses.
2. Integer-argument functions reject non-Integer args as execution type
   errors (not coercion); wrong arity is grammatically invalid.
3. Native C++ and Python fallback must be output-identical at the DuckDB
   UDF boundary for every §5.3/§5.4 surface.
4. No silent fallbacks; DuckDB wrappers convert strict-core errors to
   empty/NULL only outside strict mode.
5. No hardcoded fixtures/resources in the subsetting/combining paths.

## Audit result

- Implementation sites reviewed:
  `fhir4ds/fhirpath/engine/invocations/filtering.py` (single/first/last/
  tail/take/skip), `subsetting.py` (intersect), `combining.py`
  (union/combine/exclude). All are small, general, and route equality
  through `equality_invocations.equality` (invariant 1 holds). No
  hardcoding, no silent fallbacks, no layering violations found in this
  chunk. Native counterpart parity empirically verified by QA (144 cases,
  0 diffs).
- Compressed QA handoff: EXPLORER probed 144 fresh dual-path cases across
  chained subsetting, boundary indexers, huge collections, mixed-resource
  combiners, combine-vs-select flattening, repeat() fixpoint interactions,
  odd-precision temporal/quantity equality, and boundary numerics. Zero
  parity diffs, zero spec violations.
- Compressed engineer handoff: zero issues to remediate; no code changes;
  conformance 2832/2832 re-verified.

## QA Enforcer Gate

QA was NOT lazy: composition/chaining batteries (the EXPLORER specialty)
were executed at depth, the `tail(` red flag was resolved via spec arity
verification rather than ignored, and validation used the established
dual-path doctrine (PYTHONPATH rule, register-assert, forced fallback).
RETRY_QA: false.

## Structural health

SOUND for this chunk. Issues by category: 0 across SPEC_VIOLATION /
API_CONTRACT / DATA_HANDLING / PERFORMANCE / REGRESSION_RISK /
MISSING_FEATURE. Recommended fix order: none.

## State hygiene

`issues[]` empty; no tombstones needed. Clean exit at iteration 1
(>= min_iterations=1, zero non-terminal CRITICAL/HIGH/MEDIUM).
exit_reason: CLEAN. Chunk FP-05 is ready for finalization by the outer
spec-compliance orchestrator (SKEPTIC 1 MEDIUM fix landed; HISTORIAN and
EXPLORER clean).
