# Engineer Handoff — FP-14 iteration 1 (SKEPTIC fixes)

All 3 issues RESOLVED. Python-only changes (exported helper module); engines
were already correct; no extension rebuild required.

## Changes
- `fhir4ds/fhirpath/duckdb/functions/datetime.py`
  - `DateTimeComparisons` ordering (`less_than`/`less_or_equal`/`greater_than`/
    `greater_or_equal`) and `equals`/`not_equals` now delegate to the canonical
    engine `FP_Date`/`FP_DateTime`/`FP_Time` `compare()` via a new
    `_engine_compare` helper (renders helper value back to lexical form).
    Fixes: precision-mismatch ordering returns None (empty) instead of a
    definitive boolean (QA-001, fixtures testLessThan23-25); timezone offsets
    honored with instant semantics and Z == +00:00 (QA-002).
    This is the delegate-to-engine pattern recommended by the REV-002/FP-11
    doctrine (no third hand-maintained comparison table).
  - `TIME_PATTERN`/`DATETIME_PATTERN` fractional seconds `\d{3}` → `\d{1,9}`
    with scale-aware microsecond conversion (QA-003 — fixtures use `.0`).
- `fhir4ds/fhirpath/duckdb/tests/unit/test_datetime.py`
  - Stale doctrine pin updated: `equals(@2019, @2019-06-15)` is None (§6.1/§6.2
    precision uncertainty), not False.
  - Added `test_ordering_spec_semantics_fp14_skeptic` (12 assertions:
    precision-mismatch None across Date/DateTime/Time, timezone instant
    ordering, Z=+00:00, trailing-zero fractional seconds, Date-vs-DateTime
    uncertain) and `test_fractional_seconds_one_digit_parse_fp14_skeptic`.

## Validation (Recovery Gate)
- `test_datetime.py`: 82/82 passed.
- Full fhirpath pytest tree: 1876 passed.
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47 — OVERALL 2832/2832 (baseline held).

## Reproducers (pre-fix)
- `DateTimeComparisons.less_than(FHIRDate('2018-03'), FHIRDate('2018-03-01'))`
  returned False; now None.
- `less_than(FHIRDateTime('2014-01-01T00:00:00+02:00'), FHIRDateTime('2014-01-01T00:00:00Z'))`
  returned False; now True (instant semantics).
- `DateTimeLiteral.parse_datetime('2018-03-01T10:30:00.0')` raised ValueError;
  now parses (microsecond==0).
