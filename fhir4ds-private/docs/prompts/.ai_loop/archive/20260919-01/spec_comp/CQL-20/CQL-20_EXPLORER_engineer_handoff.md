# CQL-20 EXPLORER Engineer Handoff (iteration 1)

## QA-001 MEDIUM — statistical aggregates lose decimal precision (RESOLVED)
**Reproducer:** `Variance({100000000000.01, 100000000000.03})` → 0.00020024
(exact 0.0002); `Median` of large decimals off by 9e-6; same for
PopulationVariance/StdDev/PopulationStdDev. All 3 engine modes.

**Root cause:** DOUBLE-cast lowering of DECIMAL list elements at two sites:
1. translator `expressions/_functions.py` static-literal statistical branch
   (`TRY_CAST(_v AS DOUBLE)` → `list_aggregate(...,'var_samp')`), and
2. the `Variance`/`StdDev`/`Median`/... SQL macros in
   `fhir4ds/cql/duckdb/macros/aggregate.py` (`numeric_list` DOUBLE transform).
   DOUBLE holds ~16 significant digits; DECIMAL(38,8) values ≥ 1e10 lose their
   sub-centesimal digits on cast, so deviations vanish/corrupt.

**Fix (shifted exact-decimal formulation, CQL 1.5 Appendix B Decimal ≥28
digits + §2.3 exactness doctrine):** Variance/StdDev are shift-invariant, so
subtract the first non-null element (exact DECIMAL arithmetic) and run the
DOUBLE aggregate on the small exact deviations; Median recomposes as
`anchor + TRY_CAST(median(deviations) AS DECIMAL(38,8))` (exact DECIMAL add).
Applied at both sites:
- `_functions.py` static branch: guard `Decimal in numeric_elements` and
  `_list_agg in {median,stddev_samp,stddev_pop,var_samp,var_pop}`;
- `_translate_list_aggregate_dispatch`: same form but **only for SQLArray**
  static lists — dynamic subquery lists must not embed the anchor in the
  deviations lambda (DuckDB forbids subqueries in lambda bodies; SKEPTIC
  QA-002 lambda-hoist doctrine). Dynamic sources keep the DOUBLE path.
- `macros/aggregate.py`: `Median/StdDev/PopulationStdDev/StdDevPop/Variance/
  PopulationVariance/VarPop` macros take a DECIMAL-list branch with the same
  shifted form (covers the direct SQL surface, all 3 modes, no extension
  rebuild).
- `_static_list_element_types`: unary `-`/`+` numerics now keep their element
  type (negative literals previously fell to the untyped DOUBLE path).

**Verified:** Variance/PopVariance/StdDev/Median exact at 1e11–1e14 magnitudes
incl. negative pairs, all-equal (0), single-element (null), empty/all-null
(null), Integer lists unchanged; parity py == cpp == no-python. New tests:
`test_cql20_statistical_aggregates_are_exact_at_large_decimal_magnitudes`,
`test_cql20_statistical_macro_direct_surface_is_exact_for_decimal_lists` in
`fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py` (suite 35/35).

## QA-002 LOW — GeometricMean double artifact at 1e13+ (DEFERRED)
exp(avg(ln)) amplification (~30·1e-16 rel) exceeds 8dp at 14-digit
magnitudes; exact fix needs decimal ln/exp/sqrt. Low regime, spec examples
small-magnitude. DEFERRED with analysis.

## QA-003 MEDIUM — aggregates over query-as-query-source (DEFERRED)
`Sum((from (from {3,1,2} A return A) B return B))` fails: scalar-subquery
lowering of nested query sources. CQL-05 QA-107 row-shape family; dedicated
query-plumbing chunk owner.

## Observations (not filed)
- 2 pre-existing failures in `fhir4ds/cql/tests/unit/test_audit_mode.py`
  TestMinMaxAttribution (arg_min/arg_max SQL shape) — present WITHOUT my
  change (3 fail without it); pre-dates this launch on the dev tree.
- GeometricMean zeros → 0.0, negatives → null (INTENDED, SKEPTIC doctrine).

## Validation
- aggregate parity suite: 35/35.
- CQL unit: 1610/1612 (2 pre-existing audit-mode failures, verified
  pre-existing via stash).
- Full conformance gate (final tree state): see architect handoff.
- Extension binaries untouched; md5 repo == site-packages:
  cql 3e7d4167143e01907fdd8561db43b7d7,
  fhirpath 57d0634b6ee6eddee9fc06a1355bef5a.
