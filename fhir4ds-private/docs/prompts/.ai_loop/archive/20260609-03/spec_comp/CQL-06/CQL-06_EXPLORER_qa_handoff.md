# QA Handoff: CQL-06 / EXPLORER

## Scope

Fresh EXPLORER pass for CQL-06 conversion checks:
`CanConvertQuantity`, `ConvertQuantity`, `ConvertsToBoolean`, `ConvertsToDate`,
`ConvertsToDateTime`, `ConvertsToDecimal`, `ConvertsToLong`,
`ConvertsToInteger`, `ConvertsToQuantity`, `ConvertsToRatio`,
`ConvertsToString`, and `ConvertsToTime`.

## Spec Anchor

CQL Appendix B says `ConvertsToString(argument Any)` returns true when the
argument is or can be converted to `String`, and points to `ToString`. The
Appendix B conversion table lists String conversions for scalar primitive,
temporal, Quantity, and Ratio values. It does not define List or Tuple to
String conversion.

## Probe

Added fresh probe:

```bash
python3 .temp/qa/cql06_explorer_probe.py
```

The probe covers native-loaded and forced Python fallback registrations,
translated CQL execution, runtime SQL parameters, malformed temporal offsets,
Quantity/Ratio decimal representability, incompatible `ConvertQuantity` units,
null inputs, and the raw no-Python C++ `ToQuantity` surface.

## Finding

`QA-001` HIGH: `ConvertsToString` and `ToString` currently accept structural
List/Tuple values by falling through to DuckDB string casts.

Reproducers:

```sql
SELECT ConvertsToString([1, 2]);
SELECT ConvertsToString({'a': 1});
SELECT ConvertsToString(json_object('a', 1));
SELECT ToString([1, 2]);
SELECT ToString({'a': 1});
SELECT ToString(json_object('a', 1));
```

Translated CQL reproducer:

```cql
define ListStringable: ConvertsToString({1, 2})
define TupleStringable: ConvertsToString(Tuple { a: 1 })
```

Actual: native and forced fallback return true for the conversion checks, and
`ToString` returns cast text.

Expected: conversion checks return false and `ToString` returns null for List
and Tuple values.
