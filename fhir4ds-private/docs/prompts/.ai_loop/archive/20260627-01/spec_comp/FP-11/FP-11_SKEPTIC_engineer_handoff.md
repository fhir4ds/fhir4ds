# Engineer Handoff - FP-11 SKEPTIC

## Scope

Remediated current FHIRPath §5.7 Math (STU) issues found by fresh QA.

## Issues Resolved

### QA-001 - MEDIUM - RESOLVED

Current §5.7 allows Quantity input for `ceiling()`, `floor()`, `round([precision])`, and `truncate()`, returning a Quantity with the same unit. Both native C++ and forced Python fallback rejected those Quantity inputs.

Fix:

- Added Quantity-preserving branches in `fhir4ds/fhirpath/engine/invocations/math.py`.
- Added matching native branches in `extensions/fhirpath/src/fhirpath/evaluator.cpp`.
- Aligned the direct helper surface in `fhir4ds/fhirpath/duckdb/functions/math.py`.
- Updated integration/unit/native sqllogictest coverage.

### QA-002 - MEDIUM - RESOLVED

Current §5.7 declares `power(exponent : Integer | Decimal) : Decimal`; both native and fallback preserved Integer type for exact integer powers.

Fix:

- Removed Integer-preserving `power()` branches in Python fallback, native C++, and direct helpers.
- Updated parity expectations so `2.power(3)` is Decimal-shaped and type checks return Decimal, not Integer.

## Validation

Passed:

```bash
python3 .temp/qa/fp11_skeptic_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_math.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp11_skeptic_fresh_probe.py
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Full conformance remained 2822/2822.

Bundled extension hash after rebuild/copy:

`9af17dbaa1d988c85f6958b9fd0589fa1e50d67b4518ba38954c15063629b750`

## Notes for Architect

Review that Quantity support is intentionally limited to the §5.7 functions that allow it: `abs()`, `ceiling()`, `floor()`, `round()`, and `truncate()`. `exp()`, `ln()`, `log()`, `power()`, and `sqrt()` remain numeric-only.
