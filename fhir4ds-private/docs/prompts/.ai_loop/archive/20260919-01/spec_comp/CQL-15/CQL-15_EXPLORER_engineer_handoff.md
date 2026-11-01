# Engineer Handoff — CQL-15 EXPLORER iteration 1 (FIX, resumed 2026-08-22)

Resumed after interruption. The interrupted attempt had already applied most
source edits; this pass completed the fixes, rebuilt/deployed the native
extension, added regression tests, and re-ran the full gate.

## QA-001 (HIGH) — LIST_EXTRACT interval operands — RESOLVED
- Fix: `_is_fhir_interval_expression`
  (fhir4ds/cql/translator/expressions/_temporal_intervals.py) now recognizes
  `LIST_EXTRACT`/`list_extract` whose source is interval-producing
  (SQLList/SQLArray of `intervalFromBounds`, `from_json(collapse_intervals[_per])`,
  or direct interval-UDF calls). `_translate_expand`
  (fhir4ds/cql/translator/expressions/_functions.py) routes interval-typed
  LIST_EXTRACT operands to the single-interval `expand_points` overload.
- Result: contains/in/includes/after/before/=/~/ends/starts/except/start/end/
  expand all correct for `First({Interval[4,6]})`, `Last(...)`,
  `(collapse ...)[i]` on py, cpp, and no-py engines.
- NOTE on QA evidence: the `(collapse { Interval[1,2], Interval[4,6] } per 2)[1]`
  reproducer expectations were miscalibrated — `per 2` spec-merges the two
  intervals into one `Interval[1,6]` (gap 1 ≤ per), so index `[1]` is correctly
  null. Indexing the non-per collapse output behaves as expected. Documented,
  not a defect.

## QA-002 (MEDIUM) — Expand temporal boundary truncation — RESOLVED
- Fix (both engines):
  - Boundaries MORE precise than per are truncated to per precision — but only
    the LOW boundary moves to the per grid; grid starts compare against the
    ORIGINAL high bound (official fixture `expand Interval[@T10:00, @T12:30)
    per hour` → {T10, T11, T12}). Predecessor (`_sub_step`/SubtractExpandStep)
    applies only when the high is at/coarser than per.
  - Boundaries LESS precise than per contribute nothing for Date/Time
    (`Interval[@2024-01, @2024-01] per day` → {}; `Interval[@T10,@T10] per
    minute` → {}).
  - Numeric behavior preserved (DBCG Java reference: `expand Interval[1.2,3.0]
    per 1` → [1.2, 2.2] — grid from start, no numeric truncation).
- Files: fhir4ds/cql/duckdb/udf/interval.py (`_expand_temporal` rank/truncate,
  `_expand_time` millis-floor of low only); extensions/cql/src/cql_extension.cpp
  (ExpandTemporalInterval truncate-start-only + high_more_precise guard,
  ExpandTimeInterval low-only floor). Extension rebuilt and md5-deployed
  (98a8c8583ed41359edfe929c03869d83).
- Regression caught during validation: truncating the HIGH bound broke official
  fixtures ExpandPerHourOpen / ExpandPerHourOpenIntervalOverload (1704/1706);
  root-caused and fixed by the low-only truncation above (gate restored).

## Regression tests
fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py — two new
dual-engine (py/cpp/no_py) tests:
- test_cql_interval_part1_explorer3_list_extract_interval_operands_route_as_intervals
- test_cql_interval_part1_explorer3_expand_temporal_boundary_truncation
File total 21/21 passing. (Known accepted nit: pure-C++ intervalExcept JSON
quotes numeric lows as "6" vs py 6 — pre-existing transport convention,
normalized in the test.)

## Validation
- CQL conformance: 1706/1706 (CqlIntervalOperatorsTest 412/412).
- Full master gate + integration battery: see architect_handoff (fresh run
  after final edit).
