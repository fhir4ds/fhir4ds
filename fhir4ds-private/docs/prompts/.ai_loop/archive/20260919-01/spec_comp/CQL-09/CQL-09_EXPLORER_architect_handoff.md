# Architect Handoff — CQL-09 Comparison Operators (EXPLORER, iteration 1)

## Summary
QA (EXPLORER) probed ~110 dual-path cases across the full CQL-09 mandate
(equivalent on temporals/quantities/composites, null propagation, Between
mixed types/null bounds, converted values, 28-digit decimals, string and
Code/Concept ordering, chains in where-clauses, E2E DuckDB) with zero
native-vs-Python divergence and found 2 genuine MEDIUM spec violations of
the same root-cause family: bare-numeric vs Quantity comparisons dropped
units (definite booleans where CQL 1.5 Table 9-E + §9.5 require unit-aware
nulls) and crashed (~ BinderException) where §9.7 requires false. The
engineer fixed both by promoting static numeric literals to unit-'1'
quantities through the existing `_quantity_operand_for_arithmetic` helper
in `_operators.py` (ordered ops + equivalence). A first global variant
regressed DQM to 45/47 (CMS72/CMS190, one patient each — fixture quantities
carry non-UCUM display units); the engineer root-caused it via A/B SQL
diff, narrowed the fix to static Quantity literals, and documented the
dynamic-quantity fixture doctrine. Final gate 2832/2832; new 18-case
dual-backend regression test; stale `5 'mg' = 5 → True` doctrine corrected
in AGENTS.md. QA-003 (LOW, DEFERRED) records the future dual-engine
quantity_compare unit-validity fallback.

## Issue counts
SPEC_VIOLATION: 2 (both VERIFIED). SPEC_AMBIGUITY: 1 (DEFERRED).
Architecture drift: 0 — golden standard at
`.temp/architect/golden_standard_cql09_explorer.md`; fix composes existing
AST helpers, no fixture hacks, doctrine registry updated in-change.

## QA quality gate
Sufficient — no veto (RETRY_QA false). EXPLORER covered every mandate
surface on both engine paths, verified spec text by fetch before logging,
and self-corrected its own false-positive expectations (Between day-precision,
count-of-null, Long literals).

## Validation evidence
Parity suite 15/15; CMS190/CMS72 100% targeted; full conformance 2832/2832
(ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — baseline held.

## Recommended fix order
None — no open CRITICAL/HIGH/MEDIUM issues remain. Clean exit at
min_iterations=1.
