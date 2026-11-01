# QA Handoff - FP-08 HISTORIAN

Date: 2026-06-12

## Scope

Fresh HISTORIAN pass for FHIRPath §5.5.7 Quantity Conversion, §5.5.8
String Conversion, and §5.5.9 Time Conversion:

- `toQuantity([unit])`
- `convertsToQuantity([unit])`
- `toString()`
- `convertsToString()`
- `toTime()`
- `convertsToTime()`

Spec source verified: official HL7 FHIRPath continuous-build source,
`input/pages/index.md`, §5.5.7-§5.5.9.

## Test Plan

Hypotheses tested:

- Quantity conversion accepts Integer, Long, Decimal, Boolean, Quantity, and
  regex-compatible String inputs, with default unit `'1'`.
- Optional Quantity `unit` arguments resolve in native and fallback paths,
  including scoped `select(...)` expressions after the FP-08 SKEPTIC fix.
- Quantity conversion to incompatible units returns empty for `toQuantity()`
  and false for `convertsToQuantity()`.
- `toString()` and `convertsToString()` enforce singleton input and reject
  complex/non-primitive values.
- Time conversion preserves partial precision and rejects invalid ranges.
- Native DuckDB/C++ and forced Python fallback public wrappers agree.

Fresh probe artifact:

```bash
python3 .temp/qa/fp08_historian_fresh_probe.py
```

## Findings

`QA-001` - MEDIUM - OPEN

FHIRPath Quantity `toString()` can emit scientific notation, violating the
§5.5.8 Quantity String representation and causing native/fallback drift.

Evidence from fresh probing:

- Native DuckDB:
  `x = "1 'mg'"`, `x.toQuantity('kg').toString()` returned
  `["1e-06 'kg'"]`.
- Native DuckDB:
  `1000000000000000 'g'.toString()` returned `["1e+15 'g'"]`.
- Forced Python fallback:
  `y = "2 'm'"`, `y.toQuantity('cm').toString()` returned
  `["2E+2 'cm'"]`.

Expected:

- Quantity String conversion should use the spec's decimal digit pattern and
  not exponent notation, e.g. `0.000001 'kg'`, `200 'cm'`, and
  `1000000000000000 'g'`.

## Notes

Time strings with timezone offsets were probed because §5.5.9's conversion
format line mentions an offset suffix, but §4.1 Time explicitly says Time
values do not have a timezone or timezone offset. Native and fallback both
reject offset-bearing Time strings. This was not logged as a bug in this pass.
