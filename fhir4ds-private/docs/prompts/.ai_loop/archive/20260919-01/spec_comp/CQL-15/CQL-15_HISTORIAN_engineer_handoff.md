# Engineer Handoff — CQL-15 iteration 1 (HISTORIAN), 2026-08-21

All fixes at root cause; dual-engine (Python + native) lockstep; no shims.

## QA-001 (HIGH) collapse temporal per 0/1 precision meets
Reference CollapseEvaluator.kt keeps the interval unextended for a temporal per of
exactly 0 or 1 and passes `precision = per.unit` to Overlaps/Meets.
- Python `fhir4ds/cql/duckdb/udf/interval.py`: `_extend_bound_by_per` now returns the
  sentinel "PRECISION_MEETS" for temporal per of 0/1 (weeks instead extend by 7 days
  per unit); new `_temporal_precision_meets_or_overlaps` truncates both bounds to the
  per-unit precision and merges iff truncated low <= successor-at-precision of
  truncated high. `collapse_intervals` consumes the sentinel in the merge decision.
- Native `extensions/cql/src/cql_extension.cpp`: new `TemporalUnitPrecision` +
  `TemporalPrecisionMeetsOrOverlaps` (year/month field math, julian-day for day,
  epoch-delta at truncated hour/minute/second/ms); `CollapseIntervalsPerFunc` routes
  temporal per 0/1 DateTime bounds through it (week → numeric 7-day extension).
- Also fixed a serialization parity gap this exposed: Python collapse output now
  preserves AUTHORED temporal precision for bounds (raw strings), matching native
  DateTimeValue::to_string ("2024-01" stays month-precision, "2024-01-15T10" stays
  hour-precision) instead of normalizing to day/full strings.
- Rebuilt + deployed `cql.duckdb_extension` (md5 74a3a9d63c2f5e9263f8125976ea258f) to
  `fhir4ds/cql/duckdb/extensions/`; no site-packages or ~/.duckdb cache copies exist.
  Note: on mixed connections `collapse_intervals_per` is Python-preferred
  (_PYTHON_PREFERRED_CPP_CONFLICTS), so native behavior is exercised via the
  no-python runtime in tests.

## QA-002 (MEDIUM) includes [precision] (interval-interval)
`fhir4ds/cql/translator/expressions/_operators.py` `includes` branch now detects the
`precision of` wrapper around an interval right operand (mirroring the existing
`included in` handling) and emits `intervalIncludesPrecise(l, r, precision)` instead
of letting the generic precision-of translation truncate the right bounds and compare
at mixed precision. Point-interval includes [precision] path untouched.

## QA-003 (MEDIUM) expand null-bound engine divergence
- Python `_expand_impl`: single interval with exactly one null bound → OPEN null
  bound returns "[]" (spec-mandated: open null "will not contribute any results");
  CLOSED null bound returns None (implementation choice, aligned with native).
- Native `ExpandIntervalUnits`: open null bound now returns an empty expansion
  (was NULL in all null-bound cases); closed null bound stays NULL.

## QA-004 (LOW) `per -1` parse error → DEFERRED
CQL grammar's quantity literal is unsigned; spec examples are all positive per and
negative-per semantics are undefined (reference would subtract, shrinking the merge
window — arguably meaningless). No spec mandate to support it; deferred.

## Validation
- New regression test `test_cql_interval_part1_historian_collapse_per_precision_and_includes_expand`
  (test_interval_part1_parity.py): 14 defines across collapse per 0/1 (month/year/
  hour/week), includes [precision] true/false/point, expand null-bound overloads —
  triple-engine parity (python / cpp+python / no-python native).
- test_interval_part1_parity 19/19; interval part2/part3, list part1/part2,
  temporal_complex: 62/62. CQL unit tests (interval-filtered): 50/50.
- Master gate: see final report (2832/2832 held).

## QA-005 (HIGH, found at the recovery gate) CMS128 regression from SKEPTIC's collapse-per lowering
The first master-gate run this launch dropped to 2831/2832: CMS128 failed with
"Binder Error: WHERE clause cannot contain aggregates!". Reproduced with the
HISTORIAN translator hunk reverted → pre-existing breakage from the CQL-15
SKEPTIC `collapse_intervals_per` lowering (its handoff's 2832/2832 claim did not
hold for the final tree). Root cause: the new UDF name was absent from every
translator site that recognizes `collapse_intervals` as a JSON-array-string list
source, so `Sum((collapse X per) Y return ...)` emitted a bare SQL `SUM(...)`
instead of `list_sum(list_transform(...))` — illegal when the enclosing boolean
define lands in a WHERE clause. Fixed by adding `collapse_intervals_per` to:
- `_functions.py` `_JSON_LIST_FUNCS`
- `_query.py` known-list-source set + from_json wrap for list_transform
- `_lists.py` First/Last JSON wrap
CMS128 PASSED; fresh master gate: ViewDef 144, FHIRPath 935, CQL 1706, DQM 47 —
2832/2832 (baseline held). Interval part1 + list part1 parity re-run after the
fix: 28/28.
