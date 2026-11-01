# QA Handoff - CQL-06 SKEPTIC

## Scope

SPEC COMPLIANCE CHUNK CQL-06: CQL Type Operators - Conversion Checks.

Covered direct public DuckDB helper surfaces on native-loaded and forced Python
fallback registrations for:

- `CanConvertQuantity`
- `ConvertQuantity`
- `ConvertsToBoolean`
- `ConvertsToDate`
- `ConvertsToDateTime`
- `ConvertsToDecimal`
- `ConvertsToLong`
- `ConvertsToInteger`
- `ConvertsToQuantity`
- `ConvertsToRatio`
- `ConvertsToString`
- `ConvertsToTime`

## Spec Basis

CQL 1.5.3 Appendix B conversion/check operators require malformed lexical
conversion inputs to return false/null rather than hidden host-language
coercions or delayed runtime catalog failures. Public conversion macros must
therefore have their private implementation helpers registered visibly.

## Probe

Fresh probe: `.temp/qa/cql06_skeptic_probe.py`.

The probe checks native/fallback parity for Boolean, Integer, Long, Decimal,
Date, DateTime, Time, Quantity, Ratio, string, and Quantity unit-conversion
boundaries. It also simulates an unexpected private conversion helper
registration failure.

## Findings

### QA-001 - MEDIUM - OPEN

`fhir4ds/cql/duckdb/macros/conversion.py::_create_private_function` catches all
`Exception` values and silently returns. A synthetic `RuntimeError` raised while
registering a private conversion helper was swallowed.

Impact: `ToDate`, `ToDateTime`, and `ToTime` macros can be created pointing at
missing private helpers after unexpected registration failures, masking
conversion-surface setup defects until later execution.

Evidence:

```text
python3 .temp/qa/cql06_skeptic_probe.py
AssertionError: unexpected private conversion helper registration failure was swallowed
```

## Non-Issues Confirmed

With the repo root forced onto `sys.path`, current native-loaded and forced
Python fallback registrations agree on the conversion boundary matrix,
including timezone `+14:01`, JSON Quantity string-valued `value`, Decimal
scale-8 limits, malformed Quantity/Ratio strings, and incompatible
`ConvertQuantity` unit dimensions.
