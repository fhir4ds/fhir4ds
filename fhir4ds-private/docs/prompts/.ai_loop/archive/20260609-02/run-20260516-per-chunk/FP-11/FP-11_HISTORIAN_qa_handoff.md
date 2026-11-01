# QA Handoff — FP-11 HISTORIAN

## Scope
- Chunk: FP-11
- Spec: FHIRPath Normative Release v2.0.0 §5.7 Math (STU)
- Items walked: `abs()`, `ceiling()`, `exp()`, `floor()`, `ln()`, `log(base)`, `power(exponent)`, `round([precision])`, `sqrt()`, `truncate()`
- Personality: HISTORIAN

## Spec Anchor
The §5.7 math section says these functions operate on singleton collections and error on multiple items or incompatible types unless noted. For `round([precision])`, the precision must be an Integer >= 0, and the normative example is `3.14159.round(3) // 3.142`.

## Probes Run
- Source review:
  - `fhir4ds/fhirpath/engine/invocations/math.py`
  - `fhir4ds/fhirpath/duckdb/functions/math.py`
  - `extensions/fhirpath/src/fhirpath/evaluator.cpp`
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py`
- Scratch probe:
  - `.temp/qa/fp11_historian_math_probe.py`
  - `.temp/qa/fp11_historian_math_probe.log`
- Focused existing parity:
  - `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py -q` => 3 passed

## Findings
1. `QA-FP11-HIST-001` — HIGH — native C++ DuckDB `round(precision)` serializes rounded decimal output with binary floating artifacts. Reproducer: `3.14159.round(3)` returns `3.1419999999999999` from `fhirpath`, `fhirpath_text`, and `fhirpath_json` on the native path, while forced Python fallback returns `3.142`.
2. `QA-FP11-HIST-002` — MEDIUM — exported direct Python helper `round_fn` uses Python's built-in `round`, causing bankers rounding and accepting invalid precision. Reproducers: `round_fn(2.5) -> [2]`, `round_fn(-2.5) -> [-2]`, `round_fn(123, -1) -> [120]`, `round_fn(2.5, 1.5) -> [2.5]`.

## Non-Findings
- Existing native/forced fallback math parity tests pass for the previously covered argument-guard and quantity-rejection cases.
- Native and forced fallback agree for representative `abs`, `ceiling`, `floor`, `exp`, `ln`, `log`, `power`, `sqrt`, and `truncate` examples, except the new `round(precision)` textual/json serialization case.
