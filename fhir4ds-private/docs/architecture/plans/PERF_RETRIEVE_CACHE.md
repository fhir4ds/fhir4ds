# PERF: Retrieve CTE materialization + per-resourceType base scans (Phase 1)

Branch: `perf/retrieve-cache` (off `build/ext2-duckdb2` @ 3e753080).
Evidence: `benchmarks/scaling/SCALING.md` §Optimization candidates 1-2;
rung5000_48g CMS130 EXPLAIN ANALYZE.

## Problem (from the profile)

1. Population SQL emits 38 retrieve CTEs as **non-materialized** CTEs
   (`CTEDefinition.to_sql` → plain `AS (`). DuckDB inlines each reference
   into consuming definition CTEs and pushes definition-level predicates
   (nested `CASE`/`fhirpath_text`/`intervalEnd`/`cqlSameOrBeforeP` chains)
   INTO the base `resources` table scans. Worst operators:
   SEQ_SCAN 2,178,181 ms (rows=0), 506,652 ms (rows=217), 471,324 ms
   (rows=0) — thread-summed. The predicates run over every row of the
   table (6.2M) once per referencing CTE.
2. Each of the 38 retrieve CTEs scans `resources` independently
   (resourceType + in_valueset filter): 42 scan sites, 263M rows read
   from a 6.2M-row table. The ~28s × 38 ≈ 1,083s thread-time band in the
   profile is this in_valueset-per-scan cost.

## Fix

### Change A — MATERIALIZED retrieve CTEs

`CTEDefinition` gains `materialized: bool = False`; `to_sql()` emits
`AS MATERIALIZED (...)` when set. The population path
(`translate_library_to_population_sql`) sets `materialized=True` for all
retrieve CTEs (phase-2 result + included-library retrieve CTEs).

Effect: definition predicates can no longer be pushed into table scans;
they evaluate over the small materialized row sets (≤ a few hundred rows
per valueset). This kills the 2,178s/506s/471s operator class.

### Change B — per-resourceType base CTE (candidate 1)

For each resource type with ≥2 retrieve CTEs, emit ONE base CTE first:

```sql
"_rt_<Type>" AS MATERIALIZED (
    SELECT r.patient_ref AS patient_id, r.resourceType, r.resource
    FROM resources r WHERE r.resourceType = '<Type>'
)
```

Each retrieve CTE of that type is rewritten at AST level to read
`FROM "_rt_<Type>" r` with the resourceType predicate dropped and
`r.patient_ref` → `r.patient_id` (the base projects the alias). The
valueset/negation/profile filters stay in the child.

Effect: 38 table scans → 8 (one per type); child in_valueset filters run
over type-filtered rows (e.g. Observation children evaluate over the
Observation base, not the whole table). Cuts the 1,083s in_valueset band
roughly by table-selectivity.

AST surgery details:
- AND-chain flatten/drop: `build_retrieve_cte` builds a left-deep AND
  chain whose FIRST leaf is the resourceType check
  (`SQLBinaryOp(=, SQLQualifiedIdentifier(["r","resourceType"]),
  SQLLiteral(T))`). Flatten the chain, drop the type leaf, re-chain.
- Applies to BOTH main (phase2) and included-library retrieve CTEs —
  CMS130's 11 Encounter CTEs come from the AdultOutpatientEncounters
  include.
- Base name `_rt_<Type>` registered in `seen_cte_names` to avoid
  collision with definition CTE names.
- Audit `_audit_item` columns reference `r.resourceType`; the base CTE
  projects `resourceType` so those references keep working.

### Out of scope (measured, then re-ranked)

- Candidate 2 as originally framed (substitute precomputed
  `<col>_start/end` columns into definition predicates): with Change A
  the predicates evaluate over ≤ few-hundred-row materialized sets, so
  the residual win is small. Re-rank after measurement.
- Candidates 3-5 (_patients pass, JSON→VARCHAR shadow, DISTINCT keys).

## Risks

- MATERIALIZED forces eager computation of every retrieve CTE, even ones
  upstream filters would have short-circuited. The sets are small
  (valueset-filtered); memory cost is bounded by Σ type-selectivity ×
  resource JSON (~2.5 GB at rung 5k worst case; measure at 100/1000).
- Base CTE materialization duplicates the type's resource JSON in
  memory (DuckDB already holds the table). Watch peak RSS at rung 1000.
- Generated-SQL shape changes: translator unit tests pinning exact SQL
  text will be updated (parity-first doctrine: results must be
  identical; only shape changes).
- DuckDB 1.5 vs 2.0: MATERIALIZED CTEs supported on both lines; the
  dual-support suite runs on both legs as a gate.

## Gates

conformance 2870/2870; dual-support suite on 1.5.5 + 2.0.0 native;
spec-compliance 465/465; fhir4ds/cql + fhir4ds/viewdef suites; DQM 47.
Measure rungs 100/1000 via benchmarks/scaling/run_measures.py
(exec-only, us/resource, scan sites, rows-scanned).
