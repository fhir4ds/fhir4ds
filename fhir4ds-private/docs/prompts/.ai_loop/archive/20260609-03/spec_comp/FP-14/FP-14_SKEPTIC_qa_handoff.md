# QA Handoff - FP-14 SKEPTIC

Spec focus: FHIRPath N1 Section 6.2 Comparison (`>`, `<`, `<=`, `>=`).

Spec language verified directly from https://hl7.org/fhirpath/N1/#comparison:
- Comparison operators are defined for String, Integer, Decimal, Quantity, Date, DateTime, and Time.
- Empty operands propagate empty.
- Both operands must be singleton collections; multi-item operands are evaluation errors.
- Integer/Decimal comparisons use Decimal-compatible comparison.
- String ordering is lexical by Unicode character value.
- Quantity comparison requires compatible dimensions; invalid/incompatible quantity units return empty.
- Calendar durations and UCUM definite durations above seconds are incomparable for comparison.
- Partial Date/DateTime/Time precision mismatch returns empty.

SKEPTIC source-read hypotheses before testing:
- Boolean comparisons may have been implemented via host-language numeric truthiness.
- Multi-item comparison may return empty instead of raising internally, causing `fhirpath_is_valid()` to report true.
- Quantity conversion tables may compare calendar duration keywords to UCUM duration codes even when Section 6.2 says they are incomparable above seconds.
- Native and fallback comparison paths may diverge for resource-backed Quantity and temporal precision cases.
- Lexical string ordering and DateTime timezone comparisons may accidentally use locale or raw text ordering.

Fresh probe:
- Created `.temp/qa/fp14_skeptic_probe.py`.
- Ran native DuckDB C++ extension and forced Python fallback in one probe.
- Covered numeric, string Unicode lexical ordering, empty propagation, mixed types, multi-item operands, Boolean operands, Quantity unit conversion and dimension mismatch, calendar/UCUM duration boundaries, Date/DateTime/Time precision and timezone examples, and comparison inside filters.

Findings:
- `QA-001` MEDIUM: Both backends treat Boolean values as ordered (`true > false` returns true), but Section 6.2 does not define comparison for Boolean.
- `QA-002` MEDIUM: Both backends return row-resilient empty for multi-item comparison operands, but `fhirpath_is_valid('(1 | 2) < 3')`, `fhirpath_is_valid('1 < (2 | 3)')`, and `fhirpath_is_valid('arr < b')` return true even though Section 6.2 requires a singleton error.
- `QA-003` MEDIUM: Both backends compare calendar duration keywords with UCUM duration codes above seconds (`1 year > 1 'a'`, `1 month <= 1 'mo'`, `1 week > 1 'wk'`, etc.) instead of returning empty. Seconds and milliseconds remained comparable as expected.

Non-findings:
- Numeric comparisons, string lexical ordering, empty propagation, mixed-type empty results, compatible Quantity conversion, incompatible Quantity dimensions, literal temporal precision mismatch, timezone-aware DateTime literals, and comparison inside valid filters matched expected behavior.
- An early native/fallback mismatch involving `value > component.where(...).value` was caused by invalid synthetic FHIR containing both `valueInteger` and `valueQuantity`; not logged.
