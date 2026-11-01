# QA Handoff - CQL-13 EXPLORER

## Scope

CQL Date/Time Operators Part 1, EXPLORER pass. Fresh testing stressed composed component extraction, query aliases, partial precision date/time values, timezone offsets, duration vs difference uncertainty, invalid precision strings, and native-loaded vs forced Python fallback registration.

## Spec Grounding

The current CQL Reference v1.5.3 Appendix B defines Date and Time Component From for Date, DateTime, and Time values. It returns the specified component of the argument, supports `timezoneoffset`, `date`, and `time` special components, and examples show missing precision produces null rather than an execution error. The same reference defines precision-aware temporal comparison as null when the comparison reaches an unspecified precision, and the CQL-13 SKEPTIC/HISTORIAN fixes established null for unsupported duration/difference units.

## Hypotheses Tested

- Component extraction might mis-handle timezone suffixes when the requested millisecond precision is absent.
- Query aliases and singleton-from paths might lose temporal type evidence for component extraction and duration/difference uncertainty intervals.
- Nested DateTime constructor plus Quantity arithmetic might leak invalid timezone offsets or fail to preserve valid edge offsets.
- Invalid precision strings such as `week`/`bogus` should remain SQL NULL, not a silent day fallback.
- Direct public helpers and translated CQL should agree on Python fallback and native-loaded registrations.

## Finding

`QA-001` HIGH: translated `millisecond from @2024-01-01T10:00:00+05:00` emits substring-based SQL that slices `05:` from the timezone suffix and raises DuckDB `ConversionException`. Expected behavior is SQL NULL because millisecond precision is not present. Direct `dateComponent('2024-01-01T10:00:00+05:00', 'millisecond')` already returns NULL on both Python fallback and native-loaded C++ registrations.

Fresh reproducer: `.temp/qa/cql13_explorer_probe.py`.

## Validation Status

The fresh probe currently fails at `MsOffsetNoMs` with DuckDB `ConversionException`, confirming the defect before remediation.
