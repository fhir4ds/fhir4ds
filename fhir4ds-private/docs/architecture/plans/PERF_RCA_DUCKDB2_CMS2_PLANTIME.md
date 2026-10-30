# RCA: DuckDB 2.0.0 Plan-Time Tax on CMS2-Class SQL

*Date: 2026-10-30. Investigator: playground session. Trigger: dual-version retest
(report-fhir4ds-20261030150610) showed CMS2 opt-on-2.0 at +1696%/+841%/+187% vs
baseline-on-1.5.5 and attributed it to "MATERIALIZED shared-retrieve CTEs with
many consumers triggering quadratic-ish optimizer passes".*

## Verdict

The retest attribution is **wrong**. The ~30-40s CMS2 tax on DuckDB 2.0.0 is a
**plan-time pathology that the BASELINE pays identically** — it is not caused by
the retrieve-cache/materialization optimization. It was invisible in the retest
because the matrix had no **baseline-on-2.0** leg; the headline compared
opt-2.0 against base-**1.5.5**.

## Discriminating experiment (rung100, duckdb 2.0.0, native extensions, one DB)

| Leg | SQL | wall | planner | optimizer | worst pass |
|-----|-----|------|---------|-----------|------------|
| A | baseline CMS2.sql (@12030d89) | 32.7s | 5.95s | 26.2s | projection_pullup 14.0s |
| B | optimized CMS2.sql (@67c52da) | 34.1s | 5.92s | 25.5s | projection_pullup 13.5s |
| C | optimized, every `AS MATERIALIZED` stripped | 34.3s | 5.8s | 26.7s | projection_pullup 14.7s |

Populations identical across all legs (IP 38 / Denom 38 / others 0).
MATERIALIZED is exonerated: C ≈ B ≈ A. Scripts:
`/tmp/opencode/rca_cms2_20.py`, results `/tmp/opencode/rca_cms2_results.json`.

## Root cause

DuckDB 2.0.0 optimizer passes scale **super-linearly with expression-tree
size**; CMS2's generated SQL is the widest tree we ship.

- CMS2.sql is 1.34MB, ~96% of it TWO structurally-identical ~650KB subqueries
  (AdolescentMed / AdultMed "Most Recent Depression Medication" defines):
  `EXISTS` + 9 `CROSS JOIN LATERAL` chains each, ~700 `fhirpath_text` calls,
  451 `CASE`s, 14k parens per subquery.
- Scaling evidence: CMS68 (9KB SQL) plans in ~0s; CMS130 (250KB) in ~0.3s;
  CMS2 (1.34MB = 5.3x CMS130) in ~32s (~100x) — quadratic-to-cubic behavior.
- 1.5.5 plans the same SQL in ~2s; the tax is corpus-size independent
  (rung100 ≈ rung5000 ≈ 30-40s), confirming plan-time, not data, dependence.
- Passes most affected on 2.0: `projection_pullup` (14s), `deliminator` (3.9s),
  `unnest_rewriter` (3.4s), `expression_rewriter` (2.5s), `join_order` (1.6s).

## Consequences

1. Any CMS2-class measure (huge expression trees) pays a FIXED ~30-40s plan tax
   on DuckDB 2.0.0 regardless of cohort size. Execution itself is excellent
   (exec CPU ~0.4s at rung100). The optimization work remains a pure win on
   2.0 for CMS68/CMS130 and on 1.5.5 for all three.
2. Ranking inversion on 2.0 (CMS2 slowest despite cheapest execution) is an
   upstream DuckDB planner issue, not a translation defect.

## Options (ranked)

- **(a) Upstream report** to DuckDB: `projection_pullup` et al. quadratic on
  wide expression trees (1MB+ single statements with deep scalar subqueries +
  lateral chains). 2.0.0 is fresh; likely fixable pass-side.
- **(b) Translator-level expression dedup**: the two 650KB Denominator
  subqueries differ only by alias/valueset strings. A shared-shape CTE (or
  emitting one parameterized define reused twice) would halve SQL size →
  ~4x plan-time reduction under quadratic scaling. Medium effort, benefits
  both duckdb versions.
- **(c) Accept + document**: fixed tax amortizes at 5k rungs; 1.5.5 default
   for CMS2-class SQL until upstream fixes.

## Corrections to the record

- RETEST.md's divergence section should be amended: the pathology is
  **pre-existing on 2.0** (baseline equally affected), not introduced by
  MATERIALIZED CTEs. The +31% CMS2 opt-1.5 regression at rung100 remains a
  separate, small plan-time effect on 1.5.5 and inverts to -71% at 5k.
- Future dual-version matrices MUST include a baseline-on-new-version leg
  before attributing version-divergent behavior to the optimization delta.
