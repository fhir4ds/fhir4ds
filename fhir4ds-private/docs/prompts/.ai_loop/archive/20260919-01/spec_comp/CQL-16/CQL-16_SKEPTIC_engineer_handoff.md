# Engineer Handoff — CQL-16 SKEPTIC iteration 1 (2026-08-22)

## Triage

| Issue | Category | Action |
|---|---|---|
| QA-001 HIGH `in` interval-interval BinderException | SPEC_VIOLATION | FIXED |
| QA-002 MEDIUM intersect null-low bound | probe-expectation error | INTENDED (matches reference) |
| QA-003 MEDIUM null-bound meets/on-or determination + temporal overflow crash | SPEC_VIOLATION | FIXED (py + native mirror) |
| QA-004 MEDIUM Quantity meets integer step | probe-expectation error | INTENDED (reference + fixtures say false/decimal-step) |

## Fixes

**QA-001** — `fhir4ds/cql/translator/expressions/_operators.py::_translate_in_op`:
interval-valued left operand (incl. LIST_EXTRACT-derived intervals) with an
interval right operand (incl. `precision of` wrapper) now lowers to
`intervalIncludedIn` / `intervalIncludedInPrecise`, mirroring the `included in`
branch. Previously it fell into the point-in-interval BETWEEN lowering and the
engine raised `Binder Error: Cannot mix values of type VARCHAR and INTEGER_LITERAL
in BETWEEN clause` on BOTH engines.

**QA-003** — Python `fhir4ds/cql/duckdb/udf/interval.py`:
- new `_sentinel_effective_start` / `_sentinel_effective_end` (reusing the
  existing `_cql_minimum_for_peer_bound` / `_cql_maximum_for_peer_bound`
  sentinels) wired into `intervalMeets`, `intervalMeetsBefore`,
  `intervalOnOrAfter`, `intervalOnOrBefore`. Closed null bounds now resolve to
  the min/max of the point type (CQL 1.5 §9.14 Start / §9.15 End) producing
  determined results instead of null.
- `_successor_for_bound` / `_predecessor_for_bound` catch `OverflowError` /
  `ValueError` and return None (Appendix C overflow rule). This also fixes a
  new crash surfaced during remediation: `Interval[@2024-01-01, null] meets
  Interval[@2025-01-01, ...]` raised `OverflowError: date value out of range`
  once the max temporal sentinel fed the +1ms successor.

Native mirror — `extensions/cql/src/cql/interval.cpp`: static
`sentinel_start_bound` / `sentinel_end_bound` used by
`meets_before_nullable`, `on_or_after`, `on_or_before`; `meets_before_nullable`
returns **false** (not NullOpt) when `successor_bound` overflows at the max
sentinel (reference isMax guard). Extension rebuilt and deployed:
**md5 b9164ff5254bc5944d86109dd5e2cf94** across repo bundle
(`fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`) and
`~/.local/lib/python3.10/site-packages/fhir4ds/...`; `~/.duckdb` stale cache
entries removed.

## Regression coverage

New test
`fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py::test_cql_interval_part2_null_bound_sentinels_and_in_keyword_cql16_skeptic_2026_08`
(13 cases × 3 engines: py-fallback, native-loaded, no-Python C++).

## Validation

- test_interval_part2_parity.py: 10/10
- test_interval_part1_parity + part3: 28/28
- test_wasm_cpp_surface.py + test_v2_expressions.py: 152/152
- Full conformance gate: see architect handoff / report (DQM run against final
  tree state per GATE DISCIPLINE).
