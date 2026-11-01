# CQL-10 SKEPTIC QA Handoff

## Scope

- Chunk: CQL-10, Arithmetic Operators Part 1.
- Items: Abs, Add, Ceiling, Divide, Floor, Exp, HighBoundary, Log, Ln, LowBoundary.
- Evidence base: current source, current tests, official CQL XML fixtures, active guardrails, native-loaded DuckDB execution, and forced Python fallback DuckDB execution.
- Exclusion honored: did not use archived CQL-10 workflow outputs.

## Spec Anchors

- Official `CqlArithmeticFunctionsTest.xml` confirms overflow/domain boundaries such as `Exp(1000)`, `Ln(0)`, `Ln(-1)`, divide by zero, boundary precision, and Quantity arithmetic cases.
- Official `CqlDateTimeOperatorsTest.xml` was used as regression protection after Quantity/date arithmetic dispatch changed.

## Findings

- `QA-CQL10-SKEPTIC-001`: Dynamic FHIR `value[x]` arithmetic used text coercion. `Observation.value + 1` concatenated text, `Observation.value / 2` accepted `valueString`, and untyped `valueQuantity / 2` lost units.
- `QA-CQL10-SKEPTIC-002`: Unsupported Quantity plus scalar lowered to `dateAddQuantity`, producing binder errors for expressions such as `10 'mg' + 2` and `2 + 10 'mg'`.

## Regression Trap Caught

- The first Quantity/date guard was too broad and regressed `Today() +/- Quantity` plus aggregate interval expressions. Official CQL conformance dropped to 1702/1706, then to 1705/1706 after the temporal repair exposed `TimeOfDay() = TimeOfDay()`. Both regressions were fixed before archiving.

## Required Coverage Added

- Dynamic FHIR arithmetic regression test covers native C++ registration and forced Python fallback registration for numeric choice, string choice, Quantity choice, explicit Quantity division, and invalid Quantity/scalar addition.
- `TimeOfDay() = TimeOfDay()` regression test covers native C++ registration and forced Python fallback registration.
