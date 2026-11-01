# QA Handoff — CQL-03 HISTORIAN

## Scope

CQL-03 temporal and complex types: Date, DateTime, Time, Quantity, and Ratio,
with native-loaded DuckDB registration compared against forced Python fallback.

## Spec Anchors

- CQL DateTime construction accepts a Decimal timezoneOffset component and
  DateTime lexical offsets are ISO-style `(+|-)hh:mm` within `+/-14:00`.
- Date/DateTime/Time conversion helpers return false/NULL for malformed
  calendar/time values.
- Quantity and Ratio JSON internals require valid Quantity components with
  JSON-numeric Decimal `value` fields.

## Fresh Probe

Created and ran `.temp/qa/cql03_historian_probe.py`.

The probe covered:
- Direct public conversion/helper surfaces for Date, DateTime, Time, Quantity,
  and Ratio.
- Translated CQL constructor execution on forced Python fallback and
  native-loaded DuckDB connections.
- Boundary DateTime timezone offsets, invalid static constructor argument
  types, leap-day Date construction, Time precision, Quantity/Ratio `is`
  assertions, malformed JSON numeric strings, and Ratio conversion shape.

## Finding

`QA-001` HIGH: translated static `DateTime(..., timezoneOffset)` could emit
invalid ISO timezone text or coerce invalid static offset types.

Evidence before the fix:
- `DateTime(2024, 1, 1, 0, 0, 0, 0, 13.999)` emitted
  `2024-01-01T00:00:00.000+13:60`.
- `DateTime(2024, 1, 1, 0, 0, 0, 0, true)` emitted
  `2024-01-01T00:00:00.000+01:00`.
- `DateTime(2024, 1, 1, 0, 0, 0, 0, '1')` silently dropped the offset.

No other CQL-03 HISTORIAN issues were found.
