# Engineer Handoff — CQL-16 HISTORIAN iteration 1 (2026-08-22)

## Triage

| Issue | Category | Action |
|---|---|---|
| QA-001 MEDIUM Long null-bound sentinels at int32 | SPEC_VIOLATION | FIXED (py + native) |
| QA-002 MEDIUM Quantity null-bound sentinels missing | SPEC_VIOLATION | FIXED (py + native) |
| (new, found in fix) meets-before successor-overflow py(None)/native(False) divergence | PARITY_GAP | FIXED (py aligned to native isMax convention) |

## Fixes

**QA-001** — `fhir4ds/cql/duckdb/udf/interval.py`:
- new `_is_long_peer` (peer magnitude beyond int32; authored `L`-ness is erased
  at translation, so magnitude is the only Long signal — documented boundary:
  int32-range Long peers keep Integer sentinels, unpinned by fixtures);
  `_cql_minimum_for_peer_bound` / `_cql_maximum_for_peer_bound` return
  int64 min/max (reference Constants.MIN_LONG/MAX_LONG) for Long peers.
- `_successor` / `_predecessor` gained int64 max/min Appendix C guards
  (mirroring native successor_bound/predecessor_bound).
- native `extensions/cql/src/cql/interval.cpp` sentinel_start_bound /
  sentinel_end_bound Integer branches select int64 sentinels for
  beyond-int32 peers; `extensions/cql/src/cql_extension.cpp`
  Minimum/MaximumForIntervalPointType mirror (separate sentinel table used
  by intervalStart/intervalEnd).

**QA-002** — quantity sentinels Quantity(MIN_DECIMAL/MAX_DECIMAL, unit) per
reference Interval.kt start/end getters, unit preserved from the peer bound:
Python `_quantity_unit_for_sentinel` + quantity branches in the two peer-bound
helpers; native quantity JSON sentinels at both sites. `start of`/`end of` on
quantity null-bound intervals now return `{"value":-1e+20,"unit":"g"}` /
`{"value":1e+20,"unit":"g"}` on all engines.

**Parity fix** — Python `intervalMeetsBefore` returned None on successor
overflow where native `meets_before_nullable` returns False (reference isMax
guard, pinned CQL-16 SKEPTIC convention); pre-existing for temporal max
sentinel, newly reachable for Long max. Python now returns False.

Extension rebuilt and deployed:
**md5 3c0cebec785fb36d8030d37d71c65de4** across build output, repo bundle
(`fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`), and
`~/.local/lib/python3.10/site-packages/fhir4ds/...`; `~/.duckdb` stale cache
entries removed; binary mtime > source mtime; re-verified via reloaded
no-Python connection.

## Regression coverage

New test
`test_interval_part2_parity.py::test_cql_interval_part2_long_and_quantity_sentinels_cql16_historian_2026_08`
(16 defines x 3 engines: py-fallback, native-loaded, no-Python C++) incl.
meets-before overflow parity cases.

## Validation

- test_interval_part{1,2,3}_parity.py: 39/39
- test_wasm_cpp_surface.py + test_v2_expressions.py: 152/152
- Reproducers probe3/probe4: all match reference expectations on both engines
- Master conformance gate: see architect handoff (run against final tree state)
