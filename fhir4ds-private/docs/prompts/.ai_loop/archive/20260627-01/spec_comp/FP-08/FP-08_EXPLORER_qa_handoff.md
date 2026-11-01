# QA Handoff - FP-08 EXPLORER

## Scope

Fresh launch for SPEC COMPLIANCE CHUNK FP-08 with `qa_personality` set to
`EXPLORER`. I used the current source tree and current `evolution.json` only,
and anchored behavior to the current HL7 FHIRPath continuous-build text for
§5.5.7 Quantity Conversion, §5.5.8 String Conversion, and §5.5.9 Time
Conversion.

## Spec Notes

- §5.5.7: `toQuantity([unit])` accepts Integer, Long, Decimal, Quantity,
  convertible Quantity strings, and Boolean singleton inputs; optional unit
  conversion returns empty on non-convertible units, and
  `convertsToQuantity([unit])` returns false for those empty conversion results.
- §5.5.8: `toString()` accepts singleton String, Integer, Long, Decimal, Date,
  Time, DateTime, Quantity, and Boolean inputs. Decimal and Quantity string
  representations are decimal digit forms, not exponent notation.
- §5.5.9: `toTime()` accepts Time or convertible String singleton inputs and
  preserves partial time precision; invalid or multi-item inputs return
  empty/error through the public row-resilient wrappers.

## Probe

Created `.temp/qa/fp08_explorer_fresh_probe.py`. It compares native DuckDB
extension and forced Python fallback outputs for dynamic quantity units, empty
optional quantity unit arguments, resource-backed Quantity values,
resource-backed JSON Decimal values, Long conversion/stringification, multi-item
singleton violations, partial time strings, invalid time strings, and current
offset-bearing time rejection behavior.

## Findings

- `QA-001` MEDIUM OPEN: Resource-backed JSON Decimal `toString()` can emit
  scientific notation. `smallDecimal.toString()` returned `1e-06` in both
  native and fallback; `largeDecimal.toString()` returned native `1e+15`.
  Expected output is decimal digit notation such as `0.000001` and
  `1000000000000000.0` per §5.5.8.

## Handoff

Proceed to FIX. The fresh probe currently fails on `smallDecimal.toString()`
and should pass after remediation.
