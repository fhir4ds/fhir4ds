# Engineer Handoff — FP-14 HISTORIAN iteration 1

QA-001, QA-002, QA-003 RESOLVED. QA-004 LOW/UNCONFIRMED left DEFERRED
(spec ambiguity, both engines agree, no fixture — needs human/spec anchor;
spec-gaming a change without an anchor is forbidden).

## QA-001 (HIGH) — native sub-second comparison truncation
- Files: `extensions/fhirpath/src/fhirpath/evaluator.cpp`
  - `DateTimeParts` gains `std::string frac_digits` (untruncated fractional
    second digits; both `parseDateTimeParts` and `parseTimeParts` populate it
    before the existing 3-digit millisecond padding).
  - `compareDateTimes` field loop now stops at whole seconds
    (`second_end = min(cmp_to, 6)`); when both operands are second-level
    precision and equal through seconds, fraction digits are compared as
    decimals (right-padded to equal width → trailing-zero-insensitive,
    lexicographic on digits). `.1234 < .1236` true, `.1 == .100` true,
    `.5 > (no fraction)` true — matching the Python fallback.
- Extension rebuilt (`make fhirpath_loadable_extension`) and redeployed to
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` and the user
  site-packages copy (`~/.local/lib/python3.10/site-packages/...`).
- Spec anchor: §6.2 "the second and millisecond precisions are considered a
  single precision using a decimal, with decimal comparison semantics".

## QA-002 (MEDIUM) — helper Time-vs-Date/DateTime definitive results
- File: `fhir4ds/fhirpath/duckdb/functions/datetime.py` `_engine_compare`:
  type guard — when exactly one operand is a FHIRTime, return None (empty),
  since the implicit-conversion table defines no Time↔Date/DateTime
  conversion and the engine expression path already returns empty
  (`@T12:00:00 < @2014-01-01` → empty).

## QA-003 (MEDIUM) — helper AttributeError crash
- Same file: `to_engine_node` results are None-guarded; FP temporal
  constructors return None for invalid lexical forms (e.g.
  `str(FHIRDate.from_string('2018-03-01+05:00'))`), which now yields None
  (uncertain/empty) instead of crashing.

## Tests
- `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`:
  `test_subsecond_decimal_comparison_parity_fp14_historian` — 19 parametrized
  dual-engine cases (ordering, equality, !=, decimal trailing-zero semantics,
  timezone instants, fixture-precision anchors).
- `fhir4ds/fhirpath/duckdb/tests/unit/test_datetime.py`:
  `test_helper_time_not_ordered_against_dates_fp14_historian`,
  `test_helper_invalid_lexical_operand_is_empty_fp14_historian` (all six
  comparison ops asserted).

## Validation
- Focused: test_datetime.py + test_comparison_parity.py — 178/178 passed.
- Full fhirpath pytest tree: 1896 passed (was 1876 + new tests).
- Full conformance: see architect handoff / conformance_summary.log
  (baseline 2832/2832 verified after redeploy).
- Reproducers (pre-fix): `@2018-03-01T10:30:00.1234 <
  @2018-03-01T10:30:00.1236` native=false vs python=true; helper
  `greater_than(FHIRTime('T12:00:00'), FHIRDateTime(...))` → False;
  `less_than(FHIRDate('2018-03-01+05:00'), ...)` → AttributeError. All now
  spec-correct.
