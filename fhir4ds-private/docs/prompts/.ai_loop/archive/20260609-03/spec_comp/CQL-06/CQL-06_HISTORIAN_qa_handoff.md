# QA Handoff: CQL-06 HISTORIAN

Scope: CQL type operator conversion checks for `CanConvertQuantity`,
`ConvertQuantity`, `ConvertsToBoolean`, `ConvertsToDate`,
`ConvertsToDateTime`, `ConvertsToDecimal`, `ConvertsToLong`,
`ConvertsToInteger`, `ConvertsToQuantity`, `ConvertsToRatio`,
`ConvertsToString`, and `ConvertsToTime`.

Spec basis: CQL 1.5.3 Appendix B conversion checks mirror the corresponding
conversion function behavior. Quantity and Ratio conversion inputs must use
valid Quantity decimal values; this implementation's public Decimal boundary is
`DECIMAL(38, 8)`, so conversion checks must reject scale beyond 8 or integer
ranges beyond 30 digits instead of accepting values that `ToDecimal` cannot
represent.

Finding: `QA-001` HIGH. Fresh direct SQL probes showed both forced Python
fallback and native-loaded registrations accepted invalid Quantity/Ratio
conversion inputs:

- `ConvertsToQuantity('1.123456789 ''mg''')` returned true.
- `ToQuantity('1000000000000000000000000000000 ''mg''')` returned Quantity
  JSON with `1e+30`.
- `ConvertsToQuantity('{"value":1e100,"unit":"mg"}')` and
  `ConvertQuantity(..., 'g')` accepted an out-of-range JSON Quantity.
- `ConvertsToRatio` and `ToRatio` accepted equivalent malformed Ratio values.
- `ConvertsToQuantity` returned false for valid Ratio JSON even though
  `ToQuantity(Ratio)` can convert it.

Fresh probe file: `.temp/qa/cql06_historian_probe.py`.
