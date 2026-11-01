# Engineer Handoff - FP-01 EXPLORER

## Issue Summary

- `QA-001` MEDIUM `SPEC_VIOLATION`: resolved.

## Root Cause

The native DuckDB extension already rejected invalid FP-01 partial DateTime
literal shapes such as `@2014T14` and returned row-resilient empty/NULL public
UDF results. The forced Python fallback SQL path reached `_get_compiled_evaluator()`
before classifying that literal class as invalid, so fhirpath-py raised
`FHIRPathSyntaxError` through DuckDB for the same SQL query.

## Spec Reference

FHIRPath §4.1 DateTime literals allow a bare trailing `T` after a year,
year-month, or full date to mark a partial DateTime. Time components are the
`Time` part of the DateTime literal and require a full date before `T`.

Spec source consulted:
https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

## Fix

- Added `_has_invalid_partial_datetime_time_literal()` in
  `fhir4ds/fhirpath/duckdb/evaluator.py`.
- Wired the guard into forced fallback `fhirpath_is_valid()` and public SQL UDF
  row-resilient entry points in `fhir4ds/fhirpath/duckdb/udf.py`.
- Added permanent native/fallback coverage in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py`.
- Updated `fhir4ds/fhirpath/AGENTS.md` with the fragile area and fix note.

## Validation

```bash
python3 .temp/qa/fp01_explorer_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py -q
python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py::test_parser_rejects_trailing_unconsumed_tokens -q
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > .temp/qa/fp01_explorer_validation_summary.log && cat .temp/qa/fp01_explorer_validation_summary.log
```

Results:

- Fresh probe passed.
- Literal parity: 20/20 passed.
- Parser trailing-token regression: 1/1 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

## New Issues

None.
