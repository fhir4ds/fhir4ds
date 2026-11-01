# Milestone 9 Code Review — chunks CQL-21..SOF-VD-03

## Verdict: MILESTONE PASS

Standing suites re-verified FRESH: 94 passed (143.35s) — test_cql01_primitive_types +
test_arithmetic_operator_parity + test_arithmetic_part2_parity + test_comparison_operator_parity.
Log: .temp/qa/speccomp2/m9_suites.log.

## Evidence audit (5 chunks)
- CQL-21 (clinical age/codes): SKEPTIC probe + bisection; 1 finding CQL-21-F01
  (ToConcept equality: native False spec-correct vs fallback UDF TypeError crash —
  findings-only, fix direction recorded, NOT patched). H/E combined fresh battery green.
- CQL-22 (Message): SKEPTIC 6 libs + H/E combined battery, all green; Message
  passthrough/fold/raise doctrines pinned.
- SOF-VD-01/02/03 (ViewDefinition basics/constants/select): SKEPTIC probes + H/E
  combined batteries all green; cardinal ParseErrors enforced both engines; constants
  doctrine set (20 primitives, builtin precedence, typed rejections).

## Caveat ledger
CQL-05/11/12/15/16/17 H/E closures were written from SKEPTIC evidence w/o fresh
probe files (prior-window caveat, carried in milestones 6-8 reviews). CQL-13/14/18/
19/20/21/22 + SOF-VD-01/02/03 H/E are fresh-battery-backed. Recommendation stands:
combined-battery pattern preferred.

## Findings ledger (open, findings-only)
FP-10-F01, FP-14-F01, FP-18-F01 (FHIRPath native/fallback divergences; prior
milestones) + CQL-21-F01 (this window). 0 bugs found/fixed entire sweep.
