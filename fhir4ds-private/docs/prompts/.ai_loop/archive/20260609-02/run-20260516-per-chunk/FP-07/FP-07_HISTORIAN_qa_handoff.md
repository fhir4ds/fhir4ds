# QA Handoff - FP-07 HISTORIAN

Scope: FHIRPath §5.5.4 Date Conversion, §5.5.5 DateTime Conversion, §5.5.6 Decimal Conversion.

Spec source: FHIRPath Normative Release §5.5.4-§5.5.6, https://hl7.org/fhirpath/N1/

Probed native C++ DuckDB UDFs and forced Python fallback for `toDate()`, `convertsToDate()`, `toDateTime()`, `convertsToDateTime()`, `toDecimal()`, and `convertsToDecimal()`. Focused on partial precision, malformed dates, timezone suffixes, decimal lexical boundaries, booleans, empty input, and multi-item singleton behavior.

Finding:
- `QA-001` MEDIUM: native C++ `toDate()` accepts date strings with timezone-like suffixes by truncating after the date portion. Examples: `'2015-02-04Z'.toDate()`, `'2015-02-04+05:00'.toDate()`, `'2015-02-04-05:00'.toDate()`, `'2015Z'.toDate()`, and `'2015-02Z'.toDate()` return a date natively, but forced Python fallback returns empty. The spec says String conversion to Date uses the Date format `YYYY-MM-DD`; `convertsToDate()` also returns false for these same strings.

No other FP-07 issue was found in the sampled DateTime and Decimal conversion matrix. Decimal regex fixes from the previous SKEPTIC run held under native and fallback comparison.
