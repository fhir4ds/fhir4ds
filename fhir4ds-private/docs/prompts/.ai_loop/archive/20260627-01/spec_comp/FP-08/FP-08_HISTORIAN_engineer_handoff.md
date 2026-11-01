# Engineer Handoff - FP-08 HISTORIAN

Date: 2026-06-12

## Issue Status

- `QA-001` MEDIUM `RESOLVED`

## Fix

Fixed Quantity `toString()` scientific notation in both execution paths.

Root cause:

- Python fallback `FP_Quantity.__str__` built `asStr` with `str(value)`, so
  converted Decimals such as `Decimal("2E+2")` rendered as `2E+2`.
- Native C++ `Evaluator::toString(FPValue::Quantity)` streamed `double` values
  with default formatting, so small/large values could render as `1e-06` or
  `1e+15`.

Spec basis:

- Current HL7 FHIRPath §5.5.8 defines Quantity `toString()` output using a
  decimal digit pattern, not scientific notation.
- §5.5.7 conversion output feeds this String conversion path after
  `toQuantity([unit])`.

Files changed:

- `fhir4ds/fhirpath/engine/nodes.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp08_historian_fresh_probe.py`

## Validation

```bash
python3 .temp/qa/fp08_historian_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_empty_quantity_unit_parity.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
python3 conformance/scripts/run_fhirpath_r4.py
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp08_historian_fresh_probe.py
```

Results:

- Fresh probe passed, 37 asserted expressions.
- Focused parity tests passed, 23/23.
- Native C++ FHIRPath tests passed, 800 assertions.
- FHIRPath R4 conformance passed, 935/935.
- Full conformance passed, 2822/2822.
- Extension hashes match across build, repository, and Python package bundle.

## Notes For Architect

The first full conformance run exposed an over-stripping mistake in the
initial Python formatter. That was corrected before terminal classification:
Python now uses fixed Decimal notation without removing trailing Decimal scale,
preserving official FHIRPath expected values such as `1.58650000 'cm'` while
still rendering `Decimal("2E+2")` as `200`.
