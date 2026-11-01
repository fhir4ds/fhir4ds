# Engineer Handoff — FP-19 EXPLORER

Resolved:

- `QA-001` MEDIUM `SPEC_VIOLATION`: native C++ aggregate calls now enforce the
  FHIRPath N1 Section 7.1 signature `aggregate(aggregator [, init])`.
  `Evaluator::evalFunction()` throws `FHIRPathSpecError` unless `aggregate()`
  has exactly one or two arguments. This makes public result UDFs return
  empty/NULL for invalid aggregate arity and makes native `fhirpath_is_valid()`
  return false, matching the forced Python fallback.

Changed product/test files:

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

Validation:

- `python3 .temp/qa/fp19_explorer_probe.py`: OK, 30 parity cases and 25
  validity cases.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py -q`:
  7 passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath`:
  650 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
