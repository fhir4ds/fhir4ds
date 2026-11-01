# Architect Handoff — CQL-20 Aggregate Functions (iteration 1, final)

## Golden standard applied
1. Aggregate semantics live in ONE translator layer, AST-only (no SQLRaw /
   to_sql mid-pipeline) — held: all fixes build SQLExpression ASTs.
2. No resource/measure-specific branching — held: dispatch keyed on static
   element TYPES (Quantity/Integer/Decimal/DateTime...), never resource names.
3. No silent fallbacks — mostly held: `_translate_list_aggregate_dispatch`
   returns None only for names outside its family so callers fall through to
   LEGACY paths (documented pattern from CQL-19); broad `except Exception`
   guards on static type inference are conservative-inference, not masking.
4. Patient-correlation isolation must be structural — held: the CTE-backed
   inline gate prevents cross-patient leakage (leak was caught and gated
   during testing).
5. Dual-path parity (py/cpp/nopy) enforced by tests — held: 21 new e2e
   population tests assert three-engine equality.

## Findings (no fixes applied during audit)
- ARCH-1 (LOW, logged, DEFERRED): typed Sum/Avg/Product lowering now exists in
  two places (literal path in `_translate_aggregate_pre` and the new
  dispatcher). Semantics are identical today; consolidate into the dispatcher
  in a future hygiene pass to avoid dual-source-of-truth drift.
- ARCH-2 (LOW, DEFERRED): `_is_scalar_aggregate_select` sniffs SQL function
  names; the `_from_is_derived` guard is the more general invariant. If the
  name-set heuristic ever misfires, prefer widening the structural guard.
- Observation (informational): `_wrap_definition_cte`'s UNKNOWN branch
  remains the highest-complexity area in the writer; the new guard narrows
  its blast radius but the branch should eventually be split by
  "scalar-subquery vs rows" intent rather than shape post-hoc repair.

## QA Enforcer Gate
QA was NOT lazy: 3-engine probes across literals, empty/all-null/null-operand,
single-element stats, Integer/Long overflow, exact decimals, dynamic
multi-valued fields, alias chains, rows defines, retrieves, unions, filtered
queries, Quantity/date query lists, plus end-to-end multi-patient population
SQL with per-patient value assertions. Spec verified against fetched CQL 1.5
Appendix B text. RETRY_QA = false.

## Empirical validation (final tree)
Master gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47/47).
aggregate parity 30/30, list part1+2 74/74, v2 unit 147/147. Binaries
unchanged (cql 3e7d4167143e01907fdd8561db43b7d7, fhirpath
57d0634b6ee6eddee9fc06a1355bef5a; repo == site-packages).

Verdict: exit CLEAN at iteration 1 (min_iterations=1, zero non-terminal
CRITICAL/HIGH/MEDIUM issues).
