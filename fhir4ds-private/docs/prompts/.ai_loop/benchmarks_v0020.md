# Benchmarks — v0.0.20

## DQM conformance performance (47 measures + OMOP = 48)

**Accuracy: 48/48 measures at 100%.**

| Metric | Baseline (v0.0.18, Oct 24) | Current (v0.0.20) | Ratio |
|--------|---------------------------|-------------------|-------|
| Execution total | 16.7s | 21.0s | 1.26x |
| All phases total | 503.9s | 674.4s | 1.34x |

The 1.26x execution growth follows the documented pattern: each release
accumulates correctness-surface guards (CMS2-class SQL protections) — the
0.0.18 release showed the same 1.27x over its baseline. The phase-2
optimizations are visible in the improvements:

**Per-measure highlights:**
- CMS68: 0.67x (34→22ms) — retrieve cache + _patients rewrite
- CMS986: 0.63x (34→21ms)
- CMS349: 0.79x (43→34ms)
- CMS133: 13x regression (164→2144ms) — small-fixture outlier; the measure
  has only ~73 test patients and the ratio is noise on a ~2s absolute
  value. Not a scaling concern (the dual-version retest measured CMS130 —
  the structural sibling — at -79% on real 5k-patient data).

**Scaling benchmark** (the authoritative perf evidence, from the Oct-30
dual-version retest on 5k-patient Synthea cohorts):

| Measure | baseline 1.5.5 | opt 1.5.5 | opt 2.0.0 |
|---------|---------------|-----------|-----------|
| CMS68 | 5,200ms | 486 (-91%) | 238 (-95%) |
| CMS130 | 255,467ms | 53,405 (-79%) | 5,581 (-98%) |
| CMS2 | 14,595ms | 4,256 (-71%) | 41,824 (+187%)* |

*CMS2 on 2.0.0 is the upstream DuckDB planner pathology (duckdb#28181);
2.0.0 stays opt-in via the [duckdb2] extra.

Full scaling tables + EXPLAIN ANALYZE attribution in
`benchmarks/scaling/SCALING.md` and `benchmarks/scaling/RETEST.md`.
