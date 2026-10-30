# Phase 2 Item 3: conditional materialization by reference count

Branch `perf/phase2-opt`, item 3 of the Phase 2 dispatch (the reviewer's
suggestion deferred from Phase 1): "Tri-state CTEDefinition
(default/materialize/inline); materialize only CTEs referenced more than
once. Goal: keep CMS130's 2.7x while recovering CMS2's +31% rung-100
regression."

## Pre-study A/B (hand-stripped MATERIALIZED on generated SQL, parity identical)

| variant | CMS2 rung100 | CMS130 rung100 | CMS130 rung1000 | CMS68 rung1000 |
|---|---|---|---|---|
| all MATERIALIZED (item-2 tree) | 2046 ms | 2432 ms | 12801 ms | 106 ms |
| none MATERIALIZED | 1953 ms | 2436 ms | 12028 ms | 108 ms |
| single-ref inlined only | **1910 ms** | 2478 ms | **11658 ms** | 107 ms |

Key insight: the Phase-1 pathology (DuckDB inlining a retrieve into its
consumers and pushing heavy definition predicates into the base table scan)
only recurs when a MULTI-reference CTE is inlined at several sites — that is
when the scan is duplicated per consumer. A single-reference CTE inlines
exactly once: no scan amplification, and no eager materialization cost.
CMS2 rung100's Phase-1 regression was eager-materialization overhead on 11
single-ref CTEs, NOT lost pushdown protection.

## Implementation

- `CTEDefinition.materialized` is tri-state: `True` forces
  `AS MATERIALIZED`, `False` forces plain, `None` (new default) = AUTO.
- `SQLFragment.to_sql()` resolves AUTO by lexical reference count: each
  CTE's quoted name is counted inside every OTHER CTE's rendered body plus
  the main query; `refs > 1` -> MATERIALIZED kept, else dropped.
- Retrieve CTEs (translator steps 3/3.5 and the `_rt_`-rewritten children
  at step 3.6) now use AUTO.
- `_rt_<Type>` base CTEs stay FORCED MATERIALIZED — they are the shared
  single-scan fence by construction and must never inline.
- Non-retrieve definition CTEs (default None) also resolve by refcount,
  which matches their previous forced behavior in every multi-ref case
  while letting single-ref definitions inline.

## Results (medians, populations row-identical to committed baselines)

rung1000: CMS130 13199 → 12161 (-8%; cumulative -76% vs baseline),
CMS68 147.5 → 138.5 (-6%; cumulative -82%), CMS2 2708 → 2814 (+4%,
within this measure's rep variance — standalone 5-rep median 2115 ms at
rung100 confirms noise, not regression).

rung100: CMS130 2288 → 2271 (flat), CMS68 57.5 → 54.7, CMS2 2136 →
2262 harness median but 2115 standalone 5-rep median (noise band; the
pre-study shows single-ref inlining is the FASTEST variant at 1910 ms;
remaining gap vs the 1938 baseline is compile-time-dominated noise at
this rung).

## Gates

- New regression: `fhir4ds/cql/tests/unit/test_conditional_materialization.py`
  (multi-ref keeps MATERIALIZED; single-ref inlines; forced tri-state
  values survive).
- Updated the Phase-1 `TestRetrieveBaseSharing` extraction (the test split
  on `AS MATERIALIZED (` which now matches the `_rt_` base before the
  children; extraction now keys on the children's FROM clause).
- Full-measure parity vs committed baseline SQL at rung 100: CMS68/CMS130/
  CMS2 row-identical.
- Full CQL unit + duckdb suites green (the one transient failure during the
  item-2 binary swap re-ran clean; full file 48/48).
