# Engineer Handoff - SPEC FP-02 HISTORIAN

Iteration: 1
Phase: FIX

## Issue Status

- `QA-001` MEDIUM `SPEC_VIOLATION`: RESOLVED

## Fix Summary

HL7 FHIRPath defines the string function signature as `trim() : String`.
Argument-bearing invocations such as `s.trim(1)` and `s.trim({})` are invalid.

Root cause:

- Native C++ `Evaluator::evalFunction()` handled `trim()` but omitted it from
  the exact-zero-argument guard cluster, so native execution ignored supplied
  arguments and returned the same result as `s.trim()`.
- Python fallback public result UDFs were row-resilient, but fallback
  `fhirpath_is_valid()` did not include `trim` in static arity validation, so
  invalid `trim(...)` calls still reported valid.

Implemented:

- Added `trim` to native zero-argument and singleton-enforcement guard lists in
  `extensions/fhirpath/src/fhirpath/evaluator.cpp`.
- Added `trim` to fallback static string-function arity metadata in
  `fhir4ds/fhirpath/duckdb/udf.py`.
- Added permanent native/fallback regression coverage for `s.trim(1)` and
  `s.trim({})`.
- Rebuilt and copied the bundled `fhirpath.duckdb_extension`.

## Validation

```bash
python3 .temp/qa/fp02_historian_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py::test_string_transform_invalid_signatures_and_regex_validation_match_fallback -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py -q
./build/release/test/unittest "*fhirpath*"
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:

- Fresh probe passed: 24/24 cases.
- Focused string-transform regression passed.
- Operator parity passed: 9/9.
- String-transform parity passed: 4/4.
- Native C++ tests passed: 718 assertions.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, overall 2822/2822.

No new issues discovered.
