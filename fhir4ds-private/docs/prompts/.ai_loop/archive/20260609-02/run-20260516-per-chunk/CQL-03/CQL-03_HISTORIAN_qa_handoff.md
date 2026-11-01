# QA Handoff - CQL-03 HISTORIAN

## Scope

Fresh independent audit of CQL temporal and complex types: Date, DateTime, Time, Quantity, and Ratio. Archived `spec_comp/**` workflow outputs were not inspected.

## Spec Basis

Verified against HL7 CQL v1.5.3 Appendix B. Relevant requirements:
- Date, DateTime, and Time are partial-precision values with strict lexical/range validation.
- Quantity requires a present Decimal `value`; numeric ToQuantity overloads produce unit `'1'`.
- Ratio requires present numerator and denominator Quantities.
- ToQuantity(Ratio) is equivalent to dividing numerator by denominator.
- ToRatio accepts `<quantity>:<quantity>` strings.

## Probes

Compared native-loaded DuckDB registration and forced Python fallback registration for focused public SQL calls in `.temp/qa/cql03_historian_probe.log`.

## Findings

1. `CQL03-HIST-001` (MEDIUM): `ToQuantity(5)` and `ToQuantity(0.1)` fail binding in both backends despite CQL numeric overloads, while `ConvertsToQuantity(5)` returns true. `ConvertsToQuantity('{"value":"abc","unit":"mg"}')` also returns true for an invalid Quantity value.
2. `CQL03-HIST-002` (LOW): `ToQuantity(ToRatio(...))` returns null for JSON-shaped internal Ratio values instead of dividing numerator by denominator.

## Non-Findings

Temporal string validation for invalid calendar values, invalid times, malformed timezone offsets, and ToTime timezone suffix stripping matched between native-loaded and forced Python fallback in the focused probes and existing parity tests.
