# Architect Handoff — FP-05 SKEPTIC, iteration 1 (2026-08-17)

## Summary (compressed from qa/engineer handoffs)

QA (SKEPTIC) ran a fresh N1-grounded dual-path audit of FHIRPath §5.3
Subsetting + §5.4 Combining: 120+ probe cases across 3 batteries plus a
strict-core battery, covering every briefed edge (indexer negative/out-of-range/
empty/non-Integer; single() 0/1/2+; first/last/tail corners; skip/take
0/negative/oversized/INT32_MAX/non-Integer; intersect/exclude/union `=`
equality incl. 1=1.0, quantity conversion, offset-temperature empty-equality;
combine non-dedup; chaining). Evaluation semantics: 0 parity diffs, 0 spec
violations — the 2026-05-16 FP-05 hardening holds. One MEDIUM issue (QA-001):
`fhirpath_is_valid` misclassified statically-known wrong-typed §5.3 arguments
as invalid on BOTH surfaces, contradicting the accepted execution-type-error
doctrine. The Engineer fixed both message-coupled classifiers in lockstep,
rebuilt + redeployed the native extension, added a 15-case dual-backend
regression test, and held all gates: fhirpath pytest 1738 passed, conformance
2832/2832.

## Structural audit (golden standard: `.temp/architect/golden_standard.md`)

9 invariants defined; audit of the touched surface found:
- Invariant compliance: GOOD. Membership/dedup routes through shared `=`
  helpers in both engines (verified by quantity/1.0/cross-engine probes);
  combine never dedups; union/intersect always dedup; singleton-violation
  doctrine preserved by the fix.
- Known structural fragility (documented, not new): the two is_valid
  classifiers are message-coupled and must be updated together
  (`udf.py::_is_valid_empty_result_error` ↔ native
  `FhirpathIsValidFunction`). This is now the 4th lockstep edit (FP-02 QA-002,
  FP-02 QA-003, FP-03 QA-001, FP-05 QA-001). A long-term structural
  improvement would be a shared error-taxonomy table, but that is a refactor
  outside chunk scope — logged as observation only, no new issue.
- No test-driven hacks, no silent fallbacks introduced, minimal footprint
  (2 classifier edits + 1 regression test).

## QA Enforcer Gate

QA was NOT lazy: spec fetched before judging, dual-path harness validated
(caught and fixed its own unsigned-extension trap), pre-registered
hypotheses, probed duplicate-preservation correctly via `combine`-built
collections, and audited the meta-surface (is_valid) where the only real
defect lived. RETRY_QA = false.

## Issue tally

| Category | Count |
|---|---|
| SPEC_VIOLATION (evaluation) | 0 |
| API_CONSISTENCY (is_valid doctrine) | 1 — RESOLVED |
| Structural observations (no action) | 1 (message-coupled classifiers) |

## Exit

Iteration 1 >= min_iterations (1); zero non-terminal CRITICAL/HIGH/MEDIUM
issues. Clean exit. Recommended fix order for any follow-up: none required.
