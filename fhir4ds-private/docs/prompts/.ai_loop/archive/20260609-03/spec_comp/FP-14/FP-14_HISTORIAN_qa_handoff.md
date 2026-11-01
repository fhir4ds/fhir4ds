# QA Handoff - FP-14 HISTORIAN

Personality: HISTORIAN
Spec: FHIRPath Normative Release Section 6.2 Comparison
Source: https://hl7.org/fhirpath/N1/#comparison

## Spec Grounding

Section 6.2 defines comparison for strings, integers, decimals, quantities, dates, datetimes, and times. Empty operands propagate empty. Both operands must be singleton collections and same-type or implicitly convertible, otherwise evaluation errors. Quantity dimensions must match, calendar duration keywords and UCUM durations above seconds are un-comparable, partial temporal precision uncertainty returns empty, and string ordering is lexical by Unicode character value.

## Fresh Probe

Created and ran `.temp/qa/fp14_historian_probe.py` against the workspace package, comparing bundled native C++ DuckDB extension results with forced Python fallback results.

Coverage included:
- Numeric Integer/Decimal comparisons and implicit numeric conversion.
- Quantity conversion, resource-backed FHIR Quantity paths, dimension mismatch, and calendar-vs-UCUM duration boundaries.
- Date, DateTime, Time precision uncertainty and timezone examples.
- String lexical ordering, empty propagation, Boolean unsupported operands, mixed-type comparisons, singleton errors, and comparison inside filters.

Final QA probe before remediation:
- Cases: 44
- Native/fallback mismatches: 1
- Expectation failures: 0

## Finding

`QA-001` MEDIUM: forced Python fallback compares Date/DateTime values against Time values instead of treating them as incompatible for Section 6.2 ordering. Native C++ returns empty as expected.

Reproducer:

```sql
SELECT fhirpath('{}'::JSON, '@2018-01-01 < @T10:00:00');
```

Native C++: `[]`
Forced Python fallback: `['false']`

The same issue reproduces with `@2018-01-01T00:00:00 < @T10:00:00`, where fallback returned `['true']`.
