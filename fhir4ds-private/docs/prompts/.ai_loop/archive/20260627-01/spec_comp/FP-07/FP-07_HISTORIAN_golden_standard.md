# Golden Standard: FP-07 HISTORIAN FHIRPath Date, DateTime, and Decimal Conversion

1. Public DuckDB FHIRPath behavior must match between the bundled native C++
   extension and the forced Python fallback for all FP-07 conversion surfaces.
2. `toDate([format : string])` and `convertsToDate([format : string])` must
   accept at most one singleton String format argument, use it only for String
   input, and ignore it for Date/DateTime inputs.
3. `toDateTime([format : string])` and
   `convertsToDateTime([format : string])` must accept at most one singleton
   String format argument, use it only for String input, and ignore it for
   Date/DateTime inputs.
4. Date and DateTime format parsing must be token-based and reusable, not a
   list of probe-specific literals. Required current tokens include four-digit
   year, two-digit month/day, hour/minute/second, fractional second, AM/PM,
   and numeric timezone offset.
5. Formatted Date conversion from DateTime-like strings must validate the full
   formatted temporal shape before projecting the date; invalid time,
   fraction, or timezone components must not be silently truncated.
6. Conversion predicates must share the same accepted input grammar as their
   corresponding conversion functions, returning Boolean success/failure
   rather than drifting into a separate permissive parser.
7. `toDecimal()` and `convertsToDecimal()` must remain exact zero-argument
   conversion functions; Date/DateTime format support must not relax Decimal
   arity.
8. Decimal conversion must accept all spec-defined singleton numeric sources:
   Integer, Long, Decimal, Boolean, plain Decimal strings, and the current
   §5.5.6 string Long example form such as `'42L'`.
9. String Long Decimal support must be a general grammar class: optional sign,
   digits, uppercase `L`. It must not admit malformed suffixes such as `1LL`,
   `1.0L`, lowercase `1l`, exponent notation, or whitespace-padded strings.
10. Long literal support must remain parser-level in both Python and native
    paths. Literal suffix validity and String conversion suffix validity are
    adjacent but separate boundaries.
11. Public result UDFs must remain row-resilient for invalid arity, invalid
    format argument shapes, invalid literal suffixes, multi-item singleton
    errors, and failed conversions; `fhirpath_is_valid()` remains the
    expression-validity signal.
12. Native evaluator code, bundled extension binary, Python fallback logic,
    native sqllogictest coverage, and focused native/fallback parity tests
    must move together whenever an FP-07 conversion grammar changes.
