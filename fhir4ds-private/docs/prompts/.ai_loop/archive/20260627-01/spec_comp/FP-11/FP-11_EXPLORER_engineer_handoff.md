# Engineer Handoff - FP-11 EXPLORER

## Issue Status

`QA-001` MEDIUM `SPEC_VIOLATION` is `RESOLVED`.

Root cause: native C++ Math STU functions used `getNumericValue()` as `double`
for Long-sized inputs before producing integral or Decimal-shaped outputs.
That erased exact source text, rounded nearby Longs, and caused `int64_t`
casts to wrap.

## Fix

Changed `extensions/fhirpath/src/fhirpath/evaluator.cpp` to:

- Derive `ceiling()`, `floor()`, and `truncate()` integral results from
  preserved numeric `source_text` where available.
- Return exact native `Integer` values when the integral result fits in
  `int64_t`; preserve text on Decimal fallback for larger valid Decimal
  integral results.
- Route native `round()` through `source_text` for Integer/Long values, not
  only Decimal literals.
- Preserve exact Decimal-shaped text for native `power(..., 0)` and
  `power(..., 1)`, fixing max-Long identity powers.

Added regression coverage in:

- `.temp/qa/fp11_explorer_fresh_probe.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`

Rebuilt and copied the bundled extension:

`44adf11bff42a53cad7c501070d05d01c9c94556d5f303cdb30ea7fecb8c09f7`

## Validation

Passed:

```bash
python3 .temp/qa/fp11_explorer_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_math.py fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
git diff --check -- .temp/qa/fp11_explorer_fresh_probe.py fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py extensions/fhirpath/src/fhirpath/evaluator.cpp extensions/fhirpath/test/sql/fhirpath.test fhir4ds/fhirpath/AGENTS.md extensions/fhirpath/AGENTS.md fhir4ds-private/docs/prompts/.ai_loop
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Full conformance remained 2822/2822.
