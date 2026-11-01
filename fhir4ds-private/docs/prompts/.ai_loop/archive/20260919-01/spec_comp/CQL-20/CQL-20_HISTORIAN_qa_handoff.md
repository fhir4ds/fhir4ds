# QA Handoff — CQL-20 Aggregate Functions (HISTORIAN, iteration 1)

Spec source verified: CQL 1.5 Appendix B "Aggregate Functions" (cached at
/tmp/cqlref.md lines 5470–5882). All spec examples walked verbatim.

## What was probed
1. **Probe A** (`.temp/qa/cql20agg_historian/probe_literal.py`) — 86 cases: every
   Appendix B spec example verbatim (AllTrue/AnyTrue null semantics, Avg, Count,
   GeometricMean, Min/Max incl. Long/Date/Time, Median, Mode, Population*,
   Product, StdDev, Sum, Variance, all-null lists), empty-list semantics, null
   elements ignored, single-element stats, even-count medians, Integer/Long/String/
   Time families, exact decimal. **0 failures, 0 py/cpp divergences.**
2. **Probe B** (`.temp/qa/cql20agg_historian/probe_dynamic.py`) — 42 end-to-end
   population-SQL cases over a 3-patient-class fixture (incl. an Observation with
   NO valueQuantity as a null element), 3-engine parity (py/cpp/nopy):
   - SKEPTIC-fix regression subset: Min/Max/Median/Sum/Avg/StdDev/Variance/
     Population*/Product over query-derived Quantity defines, AllTrue/AnyTrue over
     retrieve-backed queries, Mode(Patient.name.given), Min/Max(Dates) — **all
     green, values correct (Median({120,80,100})=100, PopulationVariance exact)**.
   - NEW DQM-sensitive shapes: Count/Sum/Avg/Median over `where`-filtered
     retrieves, aggregates nested inside query `return` clauses, aggregates over
     unions, Conditions, tuple rows, multi-valued counts. All parity OK.
3. **Isolation probes** — dynamic numeric typing (`as Integer`, `+ 0.0` decimal
   derivation) and dynamic non-numeric operands to aggregates.

## Findings (logged in evolution.json)
- **QA-001 HIGH** — Dynamic query-element numeric aggregates lower through
  `SUM(TRY_CAST(_val AS DOUBLE))`: Decimal precision lost
  (Sum of dynamic {0.1, 0.2} = 0.30000000000000004 vs spec Decimal exact 0.3) and
  Integer typing lost (dynamic Sum(Integer) → DOUBLE 120.0 vs Integer 120). The
  CQL-20/SKEPTIC exact-typed dispatcher covers literal/stored lists only.
- **QA-002 MEDIUM** — Dynamic non-numeric operands to aggregates
  (Sum(Dates is null), Sum(Patient.name.given), Median/Mode equivalents) leak raw
  DuckDB BinderExceptions; the literal path raises typed TranslationError
  "Sum requires numeric or Quantity list source". Static validation skips
  dynamic operands.
- **QA-003 LOW INTENDED** — `O.valueQuantity.value as Decimal` nulls JSON
  integers; re-verified against CQL-05 adjudication ("As is not a conversion") —
  spec-correct, no action.

## Confirmed-conformant (no action)
Entire literal/spec-example surface (86/86 incl. spec's own examples); all six
SKEPTIC fixes regression-free on fresh fixtures; DQM-shaped Count/Sum over
filtered retrieves; nested aggregates in query returns; union sources;
per-patient isolation held on the multi-patient fixture (no cross-patient leak).

## Root-cause pointers for Remediation
- QA-001: generic dynamic lowering in `_functions.py` scalar-subquery /
  `_wrap_list_aggregate` path; route dynamic numeric element rows through the
  same exact-typed widths as `_translate_list_aggregate_dispatch`
  (DECIMAL(38,8) exact sum / INTEGER|BIGINT typed per CQL-01 doctrine). Avg may
  stay cqlDivide-exact over an exact DECIMAL sum.
- QA-002: extend `_validate_static_aggregate_argument` (or an equivalent guard at
  the dynamic branch) to raise the same typed TranslationError when the operand's
  inferred element type is Boolean/String/etc.
