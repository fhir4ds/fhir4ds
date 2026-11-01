# QA Handoff: CQL-13 HISTORIAN

Scope: CQL Date/Time Operators Part 1. Personality: HISTORIAN.

Spec anchor: CQL Reference 1.5.3 Appendix B Date/Time operators. Duration and
difference between use supported temporal precisions/units; unsupported unit
strings must not silently default to another precision.

Fresh probe: `.temp/qa/cql13_historian_probe.py`.

What I tested:
- Translated CQL Date and DateTime constructors with dynamic integer
  components, null/missing components, timezone offsets, and quantity addition.
- `before/after <precision> of` over partial Date values.
- Component extraction from partial Date, Time, and DateTime values.
- Public `dateAddQuantity`, `dateComponent`, `cqlTimezoneOffset`,
  `cqlDurationBetween`, and `cqlDifferenceBetween` across forced Python
  fallback, native-loaded, and no-Python/browser-style C++ surfaces.
- SKEPTIC duration fix: `months between @2012-01-02 and @2012` remains
  `Interval[0,10]` while `difference in months` remains `Interval[0,11]`.

Finding:
- `QA-001` HIGH: `cqlDurationBetween('2024','2025','bogus')` returned a
  day-based uncertainty interval instead of SQL NULL. Root hypothesis:
  helper code falls back to day precision for unknown unit strings.

Next phase: FIX.
