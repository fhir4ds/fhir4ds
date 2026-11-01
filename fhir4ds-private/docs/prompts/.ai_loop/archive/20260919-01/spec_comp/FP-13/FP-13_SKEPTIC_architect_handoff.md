# Architect Handoff — FP-13 launch, iteration 1

## Golden Standard (focused, this chunk)
See /mnt/d/fhir4ds/.temp/architect/golden_standard.md — §6.1 equality/
equivalence invariants incl. dual-engine lockstep, least-precision decimal
rounding, empty-propagation asymmetry between = and ~, temporal
reduced-precision false-not-empty, pinned offset-temperature empty.

## Audit of this launch's change (evaluator.cpp)
- The fix is uniform and general: cmp_prec = min(l,r) at all four native
  sites, rounding applied at precision 0. No fixture-specific branches.
  Spec-grounded (§6.1.2). Regression test pins native+fallback parity.
- Structural finding (ARCH-001, LOW, DEFERRED): the decimal-equivalence
  precision rule is now duplicated across FOUR native sites (singleton
  source_text path, singleton double fallback, valuesEquivalentState
  lambda, jsonNumbersEquivalent). This duplication is exactly why the
  first fix attempt missed the executing singleton path — recommend
  extracting a shared decimalEquivalencePrecision()/decimalTextsEquivalent()
  helper next time evaluator.cpp is touched in this area. Not fixed this
  launch (minimal-footprint discipline; no behavioral risk now that all
  four sites agree and are parity-tested).
- Extension rebuild+redeploy verified (repo bundle + site-packages +
  /tmp staging); DuckDB extension cache cleared; direct absolute-path
  LOAD re-verified behavior.

## QA Enforcer Gate
QA (SKEPTIC) was NOT lazy: 100+ dual-engine cases across all four
operators, fresh angles (~ whitespace/case/decimal/temporal/quantity
tolerance/year-month, !=/!~ negation-on-empty, incompatible types,
multi-item order-independence), doctrine pins re-verified, spec text
consulted directly (§6.1.2). Reproducers were precise (root cause located
before handoff). No RETRY_QA.

## State
All issues terminal (QA-001 RESOLVED, QA-002 INTENDED, ARCH-001 DEFERRED
LOW). Zero non-terminal CRITICAL/HIGH/MEDIUM at iteration 1 >= min 1.
Recommend CLEAN exit.
