# QA Handoff - CQL-06 HISTORIAN

## Scope

Systematic CQL-06 spec walk across all conversion-check items, including null behavior, valid and invalid Boolean/Decimal/Integer/Long/Quantity/Ratio/Date/DateTime/Time strings, native DuckDB temporal values, `CanConvertQuantity`, `ConvertQuantity`, and native-loaded versus forced Python fallback registration.

## Finding

`ConvertsToDecimal` still returned true for decimal strings that the actual DuckDB `ToDecimal` macro cannot represent, such as `1000000000000000000000000000000`. The same surface rounded `ToDecimal('1.123456789')` to `1.12345679` rather than rejecting the string for exceeding the CQL scale-8 decimal representation.

This violates the CQL rule that conversion checks are tied to the corresponding `To*` conversion and malformed or non-representable decimal strings do not convert. Recorded as `QA-001` in `evolution.json`.

All other CQL-06 HISTORIAN matrix cases matched expected native-loaded and forced Python fallback outputs.
