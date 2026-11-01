# Architect Handoff: CQL-17 HISTORIAN

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with 10 falsifiable invariants for CQL interval public helpers, no-Python/browser parity, official conformance precedence, and validation coverage.

## Structural Audit

The QA probe was not lazy: it exercised translated CQL and direct public helper calls across forced Python fallback, native-loaded registration, and no-Python/browser-style C++. It found a real C++ browser-surface parity defect and also exposed a spec-prose/conformance-suite conflict. The recovery handling was appropriate: the endpoint-inclusive experiment was backed out after official conformance failed, deep research was documented, and strict boundary behavior was preserved for the active official XML target.

No new architecture issues were logged. The retained implementation change is narrow and general: C++ `intervalStartsSame` / `intervalEndsSame` now use existing effective-bound helpers and enforce the complete CQL starts/ends predicates instead of adding test-specific branches.

## Issue Outcomes

- `QA-001`: `INTENDED`. Current prose can be read as endpoint-inclusive for interval-point `properly includes`, but the active official CQL XML conformance target expects strict endpoint behavior for `TimeProperContainsFalse` and `TimeProperInFalse`.
- `QA-002`: `VERIFIED`. No-Python/browser-style C++ starts/ends parity fixed.

## Validation

- Fresh HISTORIAN probe: passed across forced Python fallback, native-loaded registration, and no-Python C++.
- CQL-17 parity pytest: 3 passed.
- Interval/browser cluster: 80 passed.
- Native C++ sqllogictest: 746 assertions passed.
- Official conformance: 2822/2822, with CQL 1706/1706 and DQM 47/47.
- Full pytest: 7202 passed, 5 skipped, 9 warnings.
- Native/bundled CQL extension SHA-256 matched: `a273b6cb4068e6661f5674b24440f6b31893fa68dbdfea3c275f2ac66e7ea608`.
- Targeted `git diff --check`: clean.

## Recommended Next Step

Return control to the outer spec-compliance orchestrator for CQL-17 EXPLORER archival/startup. No retry QA is needed for this HISTORIAN run.
