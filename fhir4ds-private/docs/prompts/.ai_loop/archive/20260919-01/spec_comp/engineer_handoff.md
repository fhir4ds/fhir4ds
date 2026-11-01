# Engineer Handoff — CQL-13 (EXPLORER), iteration 1

Triage: QA-001/002 CONFIRMED and fixed; QA-003 CONFIRMED and fixed.

## QA-001 (HIGH) — year/month duration with month-precision operand crisp
Root cause (two parts):
1. `fhir4ds/cql/duckdb/udf/datetime.py::_duration_between_with_uncertainty`
   used `s_idx > unit_idx` for sufficiency, so month-precision operands were
   "certain" for year/month targets even though the unknown day-of-month
   changes the whole-year/month count. Month-duration already correctly
   required day precision; year did not.
2. The uncertainty path's start high boundary carried 23:59:59.999, which
   flipped exact anniversary boundaries (Jun 1 2012 + 19mo = Jan 1 2014
   was computed as 18; years between @1975-03 and @2020-03-31 → [44,45]).
Fix: certainty requires day precision on both operands for year/month
durations; date-only start high boundaries use the midnight convention
(consistent with the crisp date-only day-precision path and the official
`months between @2012-01-02 and @2012 // [0,10]` convention). Mirrored in
C++ `CqlDurationBetweenString` (extensions/cql/src/cql_extension.cpp).
Note: the pre-existing pinned expectation 18 in
test_datetime_part1_explorer_year_target_duration_uncertainty was
arithmetically wrong (Jun 2012 → Jan 2014 is 19 whole months); updated 18→19
with rationale — the phantom-time bug had produced the miscount.

## QA-002 (HIGH) — py null for years/months duration with tz-aware end
Root cause: `_duration_in_calendar_years/_months` mixed offset-naive vs
offset-aware comparison → TypeError → swallowed to null. C++ compares wall
components. Fix: `_wall_clock()` strips tzinfo in both helpers (Python and
legacy yearsBetween/monthsBetween UDFs inherit it). No C++ change needed.

## QA-003 (MEDIUM) — constructor trailing nulls + timezoneOffset
Root cause: Date ctor had no trailing-null stripping; DateTime ctor's
trailing-null pop was blocked when a timezoneOffset sat at index 7.
Fix in translator `expressions/_temporal_components.py`: strip trailing
static nulls in both ctors, carry timezoneOffset separately (static-null tz
= unspecified), and reject a static null ABOVE a specified component — the
spec §22.5 DateInvalid form `DateTime(2012,1,1,12,null,0,0,-7)` — at
translation time. `DateTime(null)` (all null) still evaluates to null per
the official DateTimeNull fixture. Dynamic-null components still follow the
established dynamic-null → SQL NULL convention.

## Verification
- New dual-engine regression tests:
  test_datetime_part1_parity.py::test_cql_datetime_part1_explorer2_year_month_uncertainty_and_tz_and_ctor_nulls
  and ::test_cql_datetime_part1_explorer2_interior_null_component_rejected.
- Parity suite 19/19; temporal_complex 24/24; datetime_part2 + unit v2 155/155;
  test_datetime_udfs + test_age_udfs green.
- Native extension rebuilt and deployed: build == repo bundle ==
  site-packages md5 57039cb04d003f65c3553d8f56fe8125 (no ~/.duckdb cache copy).
- Full conformance gate: ViewDef 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, OVERALL 2832/2832 — baseline held (one intermediate 1704/1706
  from DateTime(null) over-rejection was fixed before final gate).

Follow-up noted (not this chunk): AgeInYearsAt/CalculateAge* UDFs keep the
documented day-1 partial-birthDate convention (crisp minimum-day age); the
uncertainty propagation from cqlDurationBetween into the age operator
surface belongs to the age-functions chunk owner.

State: QA-001, QA-002, QA-003 RESOLVED/VERIFIED.
