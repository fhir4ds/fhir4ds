# QA Handoff — Iteration 10 / Domain 9 / SKEPTIC (v0.0.14)

**Status: PASSED — 0 new issues; 1 pre-existing translator gap flagged (out of campaign scope).**

## Findings

- **H1 resolve() in DQM where-clauses**: population SQL attributes correctly
  (resolve(O.subject).gender = 'male' → exactly the 5 male patients, Count=1
  per patient). The iter-2 macro fix holds under translated-CQL usage.
- **H2 coding_matches_exact (C++ port) in population SQL**: 10/10 exact
  code+system+display matches.
- **H3 one-row-per-patient** multi-definition output contract holds.
- **H4 PRE-EXISTING (flagged, not campaign-caused)**: `Avg((from [Observation]
  O return O.valueQuantity.value as Decimal))` returns NULL for JSON-**integer**
  values — the element-rows Avg lowering probes `type().name == 'decimal'`;
  JSON integers classify as 'integer' → NULL arm. Decimal-valued quantities
  work exactly (`117.5 → 117.50000000` via cqlDivide). Verified translator
  unchanged vs HEAD except my whitelist line. CQL-20 element-rows type-probe
  family — suggested owner: next CQL chunk (loosen probe to accept
  integer/decimal numerics for Decimal-typed elements).
- **H5 MeasureEvaluator full DQM path**: IPP=10 / DENOM=10 / NUM=10 through
  the ported coding_matches_exact surface.

## Probe-harness lessons

1. FHIR CQM attribution: numerator counts only inside denominator — a
   measure without a denominator population reports NUM=0 by design.
2. Reusing the SAME define expression for two populations creates duplicate
   CTE aliases (Binder error) — use distinct defines.
3. `MeasureEvaluator(conn).evaluate(measure_bundle=..., cql_library_path=...)`;
   `summary_report(result)` takes the result argument.

Probes: `.temp/qa/v14_it10_d9_skeptic/probe.py`
