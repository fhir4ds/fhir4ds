# Engineer Handoff — FP-11 EXPLORER

## Fixed

`QA-001` is resolved.

Native C++ `fn_round()` now rounds Decimal values with available `source_text` using decimal-string half-up logic instead of formatting via binary `double`. This fixes the class of cases where high precision or tie values exposed binary artifacts:

- `1.23456789.round(20)` -> `1.23456789`
- `1.2300.round(20)` -> `1.23`
- `1.005.round(2)` -> `1.01`
- `(-1.005).round(2)` -> `-1.01`

Spec grounding: HL7 FHIRPath Normative Release §5.7.8 declares `round([precision : Integer]) : Decimal`, uses traditional 0.5-up rounding, and says precision determines the decimal place. §4.1.4 defines Decimal as a decimal value and recommends fixed-precision Decimal representation.

## Validation

- Fresh QA probe after fix: 56 cases, 0 native/fallback mismatches, 0 expectation failures.
- Focused pytest: `test_math_parity.py` 6 passed.
- Native extension sqllogictest: 514 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Files

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

