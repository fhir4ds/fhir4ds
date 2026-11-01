# Engineer Handoff: FP-19 SKEPTIC

## Issues Resolved

- `QA-001` HIGH: fixed native aggregate `init` scoping by passing the outer
  invocation focus into `fn_aggregate()` and evaluating `init` against that
  context.
- `QA-002` MEDIUM: fixed native parser keyword alternatives so bare `div` and
  `mod` are invalid identifiers while delimited forms still work.
- `QA-003` MEDIUM: fixed native lexer whitespace to accept only FHIRPath
  whitespace: space, tab, LF, and CR.

## Files Changed

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/src/fhirpath/evaluator.hpp`
- `extensions/fhirpath/src/fhirpath/parser.cpp`
- `extensions/fhirpath/src/fhirpath/lexer.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.temp/qa/fp19_skeptic_probe.py`

## Validation

- `python3 .temp/qa/fp19_skeptic_probe.py`: mismatches=0
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py -q`: 6 passed
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath`: 642 assertions passed
- `python3 conformance/scripts/run_all.py | grep -E ...`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822

## Notes For Architect

The fix is intentionally native-only for product code. The fallback already
had the correct aggregate init behavior, strict WS grammar, and `div`/`mod`
rejection. The formal grammar treats `in` as an identifier alternative, so the
probe preserves bare `in` behavior even though the prose keyword table is easy
to misread.
