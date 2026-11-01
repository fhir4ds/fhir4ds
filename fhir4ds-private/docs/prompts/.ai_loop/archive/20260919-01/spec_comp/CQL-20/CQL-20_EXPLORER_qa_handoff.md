# CQL-20 EXPLORER QA Handoff (iteration 1)

## Spec verification
CQL 1.5 Appendix B (cql.hl7.org/09-b-cqlreference.html) fetched and cached at
`.temp/qa/cql20_explorer/agg_spec.txt` BEFORE judging. Key normative facts:
AllTrue null/empty/all-null → **true**; AnyTrue → **false**; Count null/empty/all-null → **0**;
all other aggregates null/empty/all-null → **null**; Decimal ≥ 28 significant digits.

## Probes (all 3 engine modes: python-only, cpp extension, no-python/native)
- probe1.py: full null/empty/all-null matrix for all 15 aggregates; single-element
  StdDev/Variance (null) and Population* (0); GeometricMean zero (0.0) / negative (null,
  INTENDED per SKEPTIC); Min/Max equal dates; Sum Integer/Long overflow → null;
  Min(...)+1 nesting; union sources; exact decimal Sum. **All conform.**
- probe2.py: Quantity statistical family (avg/median/variance/PopStdDev, equal-value
  Min/Max), Long overflow, Product negative/zero, Mode triple/tie, nested aggregates,
  union dates, boolean nesting. **All conform** (Mode tie → null is pinned intended).
- Multi-patient retrieve probe (population SQL, 3 patients incl. empty): Count/Sum/Max/
  AnyTrue/AllTrue over retrieves with where clauses — per-patient isolation exact on
  py + cpp.
- Statistical precision at DECIMAL(38,8) boundaries: **defects found**.

## Findings
- **QA-001 MEDIUM OPEN** — decimal statistical aggregates (Median, StdDev,
  PopulationStdDev, Variance, PopulationVariance) lose precision at large magnitudes:
  `Variance({100000000000.01, 100000000000.03})` → 0.00020024 (exact 0.0002);
  Median of 3 large decimals off by 9e-6. Root cause: `numeric_list` in
  `fhir4ds/cql/duckdb/macros/aggregate.py` casts to DOUBLE before list_aggregate.
  Suggested fix: shifted formulation — subtract first non-null element (exact DECIMAL
  subtraction), run the double aggregate on the small deviations, then re-add for
  Median (variance/StdDev are shift-invariant, deviations alone suffice). Pure SQL
  macro → fixes all 3 modes without extension rebuild. Avg is already exact
  (cqlDivide varchar path).
- **QA-002 LOW DEFERRED** — GeometricMean exp(avg(ln)) double artifact at 1e13+.
- **QA-003 MEDIUM DEFERRED** — aggregates over query-as-query-source fail (QA-107
  row-shape family; query-plumbing owner chunk).

## NOT-A-BUG / doctrine confirmations
- `iif(...)` is FHIRPath, not CQL; pass-through catalog error is prior doctrine (CQL-06).
- Scientific-notation literals rejected; 28-integer-digit decimal limit enforced (§2.3).
- Mode ties / all-unique → null (pinned in test_aggregate_parity.py).
- GeometricMean negatives → null (SKEPTIC INTENDED).

Baseline untouched; no code modified during QA.
