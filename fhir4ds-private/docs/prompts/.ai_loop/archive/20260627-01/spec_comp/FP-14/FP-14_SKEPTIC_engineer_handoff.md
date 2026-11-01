# Engineer Handoff - FP-14 SKEPTIC

## Issue Status

- `QA-001` MEDIUM `SPEC_VIOLATION`: `RESOLVED`

## Fix Summary

FHIRPath §6.2 comparison defines ordering for numeric values, `Long`,
`Decimal`, and `Quantity`. Native/C++ comparison was ordering numeric and
Quantity operands through binary `double`, collapsing adjacent values above
2^53.

Implemented native exact ordering for the affected §6.2 paths:

- Added canonical decimal-text ordering helpers in
  `extensions/fhirpath/src/fhirpath/evaluator.cpp`.
- Routed native numeric comparison through canonical decimal text when
  available.
- Routed same-unit Quantity comparison through canonical decimal text.
- Preserved Integer Quantity literal source text in
  `extensions/fhirpath/src/fhirpath/parser.cpp`.
- Changed comparison-local JSON Quantity materialization to reuse
  `fpValueAsQuantity()` so resource-backed Quantity values retain numeric
  source text.
- Added parity coverage in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`.
- Added native sqllogictest coverage in
  `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied the bundled extension:
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

The first fix attempt resolved exact numeric/JSON ordering but not Quantity
ordering. Per recovery-gate protocol, a focused deep-research report was
written at `.ai_loop/state/deep_research_findings.md` before the source-text
propagation patch.

## Validation

Passed:

```bash
python3 .temp/qa/fp14_skeptic_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:

- Fresh probe passed: 22 expressions.
- Comparison parity passed: 11/11.
- Native FHIRPath sqllogictest/unittest passed: 1012 assertions.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Built and bundled extension hashes matched:
  `3406b09e60d11447578a5c8b445e058199776b93f96124d3ae3ede9f85d9cb49`.

## Architect Notes

Audit focus should be whether canonical decimal-text comparison is safely
limited to native §6.2 numeric and same-unit Quantity ordering, and whether
existing UCUM unit-conversion, temporal precision, Boolean, empty, and
multi-item behavior remains unchanged.
