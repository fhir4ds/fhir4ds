# Engineer Handoff — FP-11 HISTORIAN

Phase: FIX
Issue: `QA-001` MEDIUM, resolved
Spec source: FHIRPath Normative Release §5.7.8

## Triage

| Issue | Category | Status | Notes |
| --- | --- | --- | --- |
| `QA-001` | `SPEC_VIOLATION` | `RESOLVED` | Reproduced in native C++ and forced Python fallback. |

## Root Cause

Both backends special-cased omitted `round()` precision as an Integer result.
FHIRPath §5.7.8 defines `round([precision : Integer]) : Decimal`, and omitted
precision defaults to 0, so `round()` must have the same Decimal result type as
`round(0)`.

## Fix

- Updated `fhir4ds/fhirpath/engine/invocations/math.py::rround()` to return a
  Decimal for omitted precision.
- Updated native `extensions/fhirpath/src/fhirpath/evaluator.cpp::fn_round()`
  to remove the Integer-only omitted-precision branch.
- Added native/fallback parity tests for `1.round()`, `type().name`, and
  `is Decimal` / `is Integer`.
- Added native sqllogictest assertions for omitted-precision `round()` type
  behavior.
- Rebuilt and copied the bundled `fhirpath.duckdb_extension`.

## Validation

- `python3 .temp/qa/fp11_historian_probe.py`: 0 failures
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py -q`: 5 passed
- `./build/release/test/unittest "*fhirpath*"`: 508 assertions passed
- `python3 conformance/scripts/run_all.py`: 2822/2822 overall

No new issues were discovered.
