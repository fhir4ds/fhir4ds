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

## Confirmation: full 4-leg matrix re-run (2026-10-30 evening)

Artifacts: `/mnt/d/scaling-data/rerun-results/` (per-leg JSONs + SQL +
profiles). Protocol: fresh process per leg, exec median of 3 on generated
SQL, EXPLAIN ANALYZE profile per cell, populations parity base<->opt
asserted per cell — **all 18 cells identical**. Both base and opt SQL
executed on the opt-tree runtime (single-runtime caveat: isolates SQL-shape
delta; the baseline tree cannot register on duckdb 2.0 at all — see below).

Exec median (ms):

| Measure | Rung | base15 | opt15 | Δ | base20 | opt20 | Δ |
|---|---|---|---|---|---|---|---|
| CMS68 | 100 | 93 | 52 | -44% | 265 | 47 | -82% |
| CMS68 | 1,000 | 590 | 156 | -74% | 546 | 79 | -86% |
| CMS68 | 5,000 | 4,902 | 586 | -88% | 1,276 | 256 | -80% |
| CMS130 | 100 | 4,664 | 2,212 | -53% | 716 | 738 | +3% |
| CMS130 | 1,000 | 47,684 | 12,945 | -73% | 2,327 | 1,561 | -33% |
| CMS130 | 5,000 | 228,125 | 61,586 | -73% | 6,937 | 5,556 | -20% |
| CMS2 | 100 | 2,152 | 2,084 | -3% | 34,559 | 37,034 | +7% |
| CMS2 | 1,000 | 3,644 | 2,966 | -19% | 38,397 | 40,064 | +4% |
| CMS2 | 5,000 | 7,650 | 4,560 | -40% | 39,652 | 43,913 | +11% |

Plan time (planner+optimizer, s): CMS2-on-2.0 pays ~33-38s on BOTH base and
opt at every rung (CMS130-on-2.0: 0.3-0.4s; everything on 1.5.5: ~0s).
RCA verdict fully confirmed: the CMS2-on-2.0 wall time is the fixed
upstream plan tax, not an optimization regression. Peak RSS @5k:
40.1 GB (base15) -> 15.9 (opt15) / 19.3 (base20) / 19.7 (opt20).

Additional finding: the baseline tree (@12030d89) **cannot register on
duckdb 2.0 at all** — `ResourceInUseException` in `create_function`
(result-lifecycle semantics changed in 2.0; dual-support landed after the
baseline). base20 legs therefore execute baseline SQL files (generated on
1.5.5) against a 2.0-registered runtime — same UDF surface, so exec
comparisons remain valid.

Operational notes: the two initial rung5000 opt failures (1.5.5 segfault,
2.0 surrogate ValueError) were environmental — caused by concurrent 5k legs
from an overly-eager catch-up script competing for memory; sequential
retries clean, corpus-wide unpaired-surrogate scan negative (5,002 files).
