# QA Handoff - CQL-06 SKEPTIC

## Scope

Chunk CQL-06: conversion checks for `CanConvertQuantity`, `ConvertQuantity`, `ConvertsToBoolean`, `ConvertsToDate`, `ConvertsToDateTime`, `ConvertsToDecimal`, `ConvertsToLong`, `ConvertsToInteger`, `ConvertsToQuantity`, `ConvertsToRatio`, `ConvertsToString`, and `ConvertsToTime`.

Tested the public DuckDB registration surface with C++ extensions loaded and with Python fallback registration. The outputs matched, but several matched outputs contradicted the CQL v1.5.3 conversion rules.

## Spec Baseline

The CQL reference says each `ConvertsTo*` operator returns true when the argument is or can be converted by the corresponding `To*` operator, returns false for malformed strings, and returns null for null inputs. For this chunk, the relevant strict rules are:

- Boolean strings are exactly `true/t/yes/y/1` and `false/f/no/n/0`, ignoring case.
- Decimal strings use `(+|-)?#0(.0#)?`; Boolean true/false convert to `1.0`/`0.0`.
- `ToDate` accepts DateTime and String; `ToDateTime` accepts Date and String.
- Quantity strings use `(+|-)?#0(.0#)?('<unit>')?`; Ratio is `<quantity>:<quantity>`.

## Findings

1. `ConvertsToBoolean('1.0')` and `ConvertsToBoolean(' 1')` return true, but string inputs must be one of the listed Boolean string representations.
2. `ConvertsToDecimal('1e2')`, `ConvertsToDecimal(' 1')`, `ConvertsToDecimal('1.')`, and `ConvertsToDecimal('.5')` return true despite invalid CQL decimal syntax. `ConvertsToDecimal(true)` returns false despite the Boolean overload.
3. `ConvertsToDate(2024)` and `ConvertsToDateTime(2024)` return true because the helpers stringify integers. Native DuckDB `TIMESTAMP` input is rejected by `ConvertsToDate`/`ToDate`, even though CQL DateTime can convert to Date.
4. `ConvertsToQuantity('.5 ''mg''')` returns true because `toQuantity()` allows no digit before the decimal point. The same grammar feeds `ConvertsToRatio`.

Issues are recorded as `QA-001` through `QA-004` in `evolution.json`.
