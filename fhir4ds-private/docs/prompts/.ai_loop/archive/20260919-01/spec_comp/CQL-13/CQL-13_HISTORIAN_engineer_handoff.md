# Engineer Handoff — CQL-13 (HISTORIAN), iteration 1

Triage: QA-001 SPEC_VIOLATION (CONFIRMED), QA-002 SPEC_VIOLATION
(CONFIRMED), QA-003 SPEC_VIOLATION (DEFERRED, LOW, null-result lenient
typing — static per-type precision rejection is net-new translator typing
functionality; no wrong non-null value is ever produced).

## QA-001 (HIGH) — sub-day Difference used Duration truncation math
Root cause: `_compute_difference` (Python, fhir4ds/cql/duckdb/udf/
datetime.py) and `ComputeDifferenceBetweenValue` (C++, extensions/cql/
src/cql_extension.cpp) computed hour/minute/second/millisecond Difference
as int(elapsed/unit) — the §8.8 Duration rule — while day/month/year/week
already counted boundaries. Legacy `differenceIn{Hours,Minutes,Seconds}`
UDFs (both engines) shared the defect.

Fix (spec: §8.7 "number of boundaries crossed"): count boundaries as the
difference of floor(epoch-millis/unit-ms) indices (endpoint marks
included, matching the day-precision behavior and the spec example
@2012-01-01 -> @2012-02-01 == 1). Timezone-aware operand pairs are
UTC-normalized before indexing; mixed aware/naive stays null. C++
`FloorDivInt64` added because epoch millis are negative before 1970 and
C++ division truncates toward zero. Python `_subday_boundary_difference`
helper reused by `_compute_difference` and the three legacy helpers.

## QA-002 (MEDIUM) — Time + day-level unit silently no-opped
Root cause: the Time branch of `dateAddQuantity` dispatched on
`_TIMEDELTA_UNITS` which includes week/day (keyword + UCUM), so the
2000-01-01 reference-date shift was invisible at time precision
(`@T12:30 + 1 week` returned the input unchanged). Year/month already
fell through to null; week/day did not.

Fix (spec: §8.1/§8.15 "For Time values, the quantity unit must be one
of: hours, minutes, seconds, or milliseconds"): explicit allowlist guard
in the Python Time branch, and `IsDayLevelUnit` guard in C++
`DateAddQuantityFunc`/`DateSubtractQuantityFunc` (mirrors the Date
sub-day guard from the SKEPTIC launch). dateSubtractQuantity delegates
to dateAddQuantity with the negated value, so Subtract is covered.

## Verification
- Reproducer battery .temp/qa/cql13_hist/probe3.py: all previously
  failing cases now return spec values; py == cpp on all 31 probes.
- New regression test
  `test_datetime_part1_parity.py::test_cql_datetime_part1_subday_difference_boundaries_and_time_unit_restriction`
  (dual-engine, 15 assertions) — parity suite 17/17 green.
- Stale truncation pins in `test_datetime_udfs.py`
  (`differenceIn{Hours,Minutes,Seconds}` expectations -3/0/0 → -4/-1/-1
  per boundary semantics; test renamed to ..._count_boundaries_...).
- Native extension rebuilt and deployed: build/release == repo bundle ==
  site-packages md5 c08b7f98656eff298ade8b4a7379043b; no ~/.duckdb cache
  copy exists.
- Full gate: see architect handoff (fresh conformance run recorded there).

State: QA-001 RESOLVED/VERIFIED, QA-002 RESOLVED/VERIFIED, QA-003
DEFERRED (terminal).
