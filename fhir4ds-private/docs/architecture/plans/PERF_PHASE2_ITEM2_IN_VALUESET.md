# Phase 2 Item 2: JSON→VARCHAR re-serialization investigation & in_valueset contention fix

Branch `perf/phase2-opt`, item 2 of the Phase 2 dispatch ("JSON->VARCHAR
re-serialization per UDF call ... Carry the resource natively (VARCHAR/JSON
from load) or extract needed fields once at the retrieve").

## Dispatch hypothesis DISPROVEN (evidence)

The dispatch evidence read `fhirpath_text(CAST(resource AS VARCHAR), ...)` in
EXPLAIN plans as a per-call JSON→VARCHAR re-serialization cost. Measurement
shows the CAST is DuckDB's *rendering* of an implicit JSON→VARCHAR argument
conversion that is metadata-only (JSON logical type is VARCHAR-backed):

| A/B (whole `resources` table swap, JSON col vs pre-cast VARCHAR col) | rung100 | rung1000 |
|---|---|---|
| CMS130 | 2536 → 2369 ms | 15698 → 15942 ms |
| CMS68  | 56 → 57 ms | 395 → 381 ms |

No material difference at either scale; populations row-identical. Additional
micro-probes: repeated `fhirpath_text(x,'status')` chains in WHERE (5x) cost
the same as a hoisted single evaluation (26 vs 26 ms); hoisting the 48-copy
`from_json(fhirpath(...,'dosageInstruction'))` singleton CASEs in CMS130's
AIFrail definition into one lateral changed nothing (2557 → 2553 ms).
DuckDB already evaluates these per-thread without re-parsing the transport.

## Real cost found: in_valueset global-mutex serialization

Operator attribution (PRAGMA profiling JSON, CMS130 rung100): FILTER
expression evaluation = 3.1 s exclusive of a 2.4 s-wall query, cpu_time ==
exclusive time (fully serialized). The dominant single FILTER (2.2 s) is ONE
`in_valueset(resource,'code',VS)` call over 47k Observations.

Root cause: `InValuesetFunc` (extensions/cql/src/cql_extension.cpp) acquired
the global `g_valueset_cache_mutex` (a `std::mutex`) TWICE PER ROW — once for
the loaded-check, once for the per-code lookup loop. With 32 threads all
workers serialized on one core:

| threads | in_valueset (501k rows) | extractCodes alone |
|---|---|---|
| 1 | 573 ms | 554 ms |
| 4 | 774 ms | 184 ms |
| 32 | 1079 ms | 121 ms |
| 32 (post-fix) | **130 ms** | 129 ms |

## Fix

`g_valueset_cache_mutex` is now a `std::shared_mutex`:
- `InValuesetFunc` takes ONE shared (read) lock per vector chunk
  (2048 rows), not per row.
- Cache mutation paths (`ValuesetCacheAddFunc` load, `ValuesetCacheClearFunc`,
  `ValuesetCacheSizeFunc`) take the unique lock; they run at valueset-load /
  admin time, never concurrently with query execution on this UDF.

Build notes:
- duckdb's `extension/CMakeLists.txt` pins `CMAKE_CXX_STANDARD=11` and re2
  adds a directory-scoped `-std=c++11`; the cql extension CMakeLists now
  re-asserts `-std=c++17` on both extension targets (needed for
  `<shared_mutex>`; duckdb itself requires C++17 since 1.9).
- `<shared_mutex>` must be included OUTSIDE `namespace duckdb` (top of file)
  — inside the namespace the libc++ headers define `duckdb::std::` shims and
  compilation fails.
- Both bundles rebuilt: 1.5.5 (build/release, from the pre-ext2 1.5.5-API
  source + this fix) and 2.0 (build/ext2, from HEAD 2.0-API source + this
  fix, `OVERRIDE_GIT_DESCRIBE=v2.0.0`).

## Results (medians, populations row-identical to committed baselines)

rung1000 (vs Item 1 numbers):
- CMS68 382 → 147 ms (-61%; cumulative -81% vs pre-Phase-1 baseline)
- CMS130 16,726 → 13,199 ms (-21%; cumulative -74%)
- CMS2 3,436 → 2,708 ms (-21%; cumulative -35%)

rung100: CMS130 flat (2288 ms), CMS68 51 → 57 ms, CMS2 1978 → 2136 ms
(small-rung noise band; both compile-time-dominated at this scale).

## Evaluated and deferred (with numbers)

Base-CTE membership columns (the dispatch's "extract once at the retrieve"
clause): precomputing `in_valueset` booleans into `_rt_<Type>` base CTEs.
Post-fix the per-row evaluation is already at the `extractCodes` floor and
parallel; the only remaining win is duplicate-filter sharing, measured at
~4 ms (two separate 14 ms vs shared 10 ms scans). Not worth the child-SQL
shape churn.

## Gates

- New regression: `fhir4ds/cql/duckdb/tests/test_in_valueset_thread_scaling.py`
  (asserts 4-thread runs are not slower than 1-thread; fails on the pre-fix
  binary).
- Full-measure parity vs committed baseline SQL at rung 100: CMS68/CMS130/CMS2
  row-identical.
- valueset suites: test_cpp_valueset_cache.py + test_valueset_udf.py +
  test_clinical_operator_parity.py + test_clinical_type_parity.py all green
  (43 + 45 passed).

## Independent review (Qwen3.8-Max, 2026-10-30) — hardening addendum

Review verdict: REQUEST CHANGES (1 HIGH, 1 MEDIUM). Both addressed in the
hardening commit:

1. (HIGH, FIXED) `_patients` duplicate-Patient fanout: with demographics
   projected, duplicate Patient rows (same id, different JSON — a state the
   resources table sanctions: no unique index) kept N rows per id after the
   Item-1 rewrite, and downstream LEFT JOINs multiplied them n² per patient.
   Verified repro: 1 patient duplicated once → 4 output rows (plus the
   orphan). Fix: `SQLSelect.distinct_on` (new AST field, rendered as DuckDB
   `DISTINCT ON (p.id)`), used in both literal and target_table scopes when
   demographics are projected (matching the old LIMIT-1 one-row-per-id
   contract); `distinct_on` passthrough added to ALL 14 SQLSelect rebuild
   sites across the translator (audited programmatically; 0 missing).
2. (MEDIUM, FIXED) test_in_valueset_thread_scaling.py previously registered
   a pure-Python closure UDF and never exercised the C++ extension path.
   Reworked to LOAD the built extension and populate g_valueset_cache via
   cql_valueset_cache_add (mirrors test_cpp_valueset_cache.py fixture).
3. (LOW, FIXED) ValuesetCacheSizeFunc unique→shared lock (pure read).
4. (LOW, RELEASE-NOTED) Orphan-Patient inclusion: on NONCONFORMANT sources
   where Patient rows do NOT carry patient_ref = id (none of the built-in
   adapters; possible via existing-table/CSV passthrough), the new single
   Patient scan includes every Patient id, while the old patient_ref
   enumeration included only ids referenced by some row's patient_ref.
   For conformant sources the sets are identical. Behavior change is
   intentional (full Patient denominator) — carry in release notes.
   New regression: TestPatientsDuplicateCollapse (3 tests incl. end-to-end
   fanout repro asserting exactly one row per patient id).
5. (declined, rationale) Tightening the _rt_ collision guard to reject
   retrieve CTEs literally named `_rt_<T>`: the existing guard already
   raises on any non-retrieve CTE collision; a retrieve named `_rt_X` for
   type X would share the base name with itself — DuckDB would surface a
   duplicate-CTE catalog error at emission, which is a loud failure, not a
   silent wrong result. Not worth special-casing.
6. (declined, rationale) Documenting the single-to_sql()-per-fragment
   assumption: added as a comment in _resolve_materialization instead
   (cheaper than restructuring; no call path double-renders today).
