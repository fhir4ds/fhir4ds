# Engineer Handoff — CQL-13 (SKEPTIC), iteration 1

Both issues fixed at the root, dual-engine, no workarounds.

## QA-001 (HIGH) — difference in weeks Sunday boundary rule (CQL 1.5 §8.7)
- Root cause: both engines computed week difference as truncated
  day-span/7 (duration semantics) instead of counting Sunday-first-day
  week boundaries.
- Fix:
  - fhir4ds/cql/duckdb/udf/datetime.py `_compute_difference`: Sunday-based
    week index via ordinal // 7 (proleptic Gregorian ordinal 7 =
    0001-01-07 is a Sunday, so Sunday ordinals are ≡ 0 mod 7).
  - extensions/cql/src/cql_extension.cpp `ComputeDifferenceBetweenValue`:
    week index (jdn + 1) / 7 (Julian Day Number 0 is a Monday, so Sunday
    JDNs ≡ 6 mod 7). Uncertainty-interval paths in both engines reuse
    these compute helpers and inherit the fix.
- Native extension rebuilt and deployed:
  fhir4ds/cql/duckdb/extensions/cql.duckdb_extension,
  md5 be8c0ba575df910c4e01f8459a47b32a (build/release/extension == repo
  bundle; no site-packages or ~/.duckdb cache copies exist).

## QA-002 (MEDIUM) — Date + sub-day quantity silently no-ops (§8.1/§8.15)
- Root cause: dateAddQuantity converts finer-than-input quantities by
  truncating toward the input precision, so `@2024-01-01 + 1 hour`
  converted to 0 days and returned the input unchanged.
- Fix: date-only values (no 'T' marker, not Time values) with sub-day
  units (hour/minute/second/millisecond, incl. UCUM h/min/s/ms) now
  return NULL, in Python `dateAddQuantity` (dateSubtractQuantity
  delegates via negation) and C++ `DateAddQuantityFunc` /
  `DateSubtractQuantityFunc`.

## Regression coverage
- fhir4ds/cql/duckdb/tests/integration/test_datetime_part1_parity.py:
  new `test_cql_datetime_part1_week_difference_and_date_unit_restriction`
  (16 dual-engine expectations: 8 week-boundary cases incl. backward and
  time-of-day crossing, 5 null-unit cases, 3 still-works guards).
- probe batteries re-run: only spec-conformant outputs remain (uncertainty
  intervals, timezone-correct negatives, Z preservation).

## Validation
- Focused parity suite: 16/16 on Python and C++ engines.
- Full conformance gate: 2832/2832 (ViewDefinition 144/144, FHIRPath
  935/935, CQL 1706/1706, DQM 47/47) — baseline held, no regressions.
- pytest fhir4ds/cql: 5754 passed, 9 skipped.

Both issues RESOLVED. No new issues discovered during remediation.
