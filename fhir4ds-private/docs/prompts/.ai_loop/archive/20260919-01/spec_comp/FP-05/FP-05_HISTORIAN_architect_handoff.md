# Architect Handoff — FP-05 HISTORIAN, iteration 1 (2026-08-17)

## Scope

Architectural audit of the FP-05 HISTORIAN launch (§5.3 Subsetting / §5.4
Combining). No code changed in this launch; the audit therefore focused on
(a) the structural soundness of the SKEPTIC QA-001 fix already in the working
tree, (b) verification that this launch introduced no drift, and (c) the QA
Enforcer Gate.

## Golden Standard invariants applied (chunk-scoped)

1. Both execution surfaces (Python fallback `udf.py` and native
   `fhirpath_extension.cpp`) must classify identical error message forms
   identically in `fhirpath_is_valid` — message-coupling must stay in lockstep.
2. Fixes must be doctrine-general (execution-type-error class), not
   expression-specific.
3. No silent fallbacks, no test-fixture special-casing in §5.3/§5.4 paths.
4. is_valid validity semantics must track grammar + statically-known arity
   misuse, not evaluation emptiness (documented doctrine).

## Findings

- **Invariant 1 holds**: `udf.py:2435-2437` accepts `Expected integer, got: `
  / `Indexer requires an integer index`; `fhirpath_extension.cpp:1908-1910`
  accepts the indexer + skip/take integer-argument forms. Empirically
  re-verified this launch: both surfaces returned identical is_valid values on
  all 24 checks, with singleton/multi-item violation forms correctly still
  False on both. The message-coupled dual-classifier pattern is a pre-existing,
  documented design constraint (error strings are the coupling contract); the
  fix respected it.
- **Invariant 2 holds**: the accepted prefixes are class-level ("requires an
  integer argument"), not per-expression.
- **Invariants 3-4**: no new hardcoding, fallbacks, or fixture hacks observed;
  QA's fresh probes confirmed grammar-invalid forms remain False while
  empty-evaluating valid forms (`skip(1)` on empty focus) remain True.
- **Structural observation (LOW, informational, not logged as an issue)**: the
  is_valid classifier's reliance on exact engine error-message prefixes is
  fragile by design — any future copy change to evaluator error text must be
  mirrored in both classifiers. This is already institutional knowledge
  (message-coupled classifiers); no drift was introduced.

## QA Enforcer Gate

QA (HISTORIAN) was NOT lazy: 82 fresh dual-path evaluations plus 24 is_valid
checks with genuinely new angles (computed/expression-valued nums, overflow,
temporal wrong-type args, `$this`/`$index` in args, FP-02 derived-unit equality
seams through intersect/exclude/union/combine, cross-type and object-membership
equality, error propagation through empty-singleton operands), full re-verification
of the prior fix including over-acceptance risk, and the full conformance gate.
**RETRY_QA: false.** No veto.

## Verdict

Zero open issues. Exit recommendation: **CLEAN at iteration 1 (min_iterations=1)**.
State advanced: workflow=null, exit_reason=CLEAN. Control returns to the outer
spec-compliance orchestrator (FP-05 now has SKEPTIC fix + HISTORIAN clean
confirmation; EXPLORER pass may follow per outer scheduling).
