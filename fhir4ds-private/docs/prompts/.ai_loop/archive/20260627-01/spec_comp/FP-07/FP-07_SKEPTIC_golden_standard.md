# Golden Standard: FP-07 FHIRPath Date, DateTime, and Decimal Conversion

1. Public DuckDB FHIRPath behavior must match between the bundled native C++
   extension and the forced Python fallback for every supported FP-07 surface.
2. `toDate()` and `convertsToDate()` must implement the current FHIRPath
   signature `([format : string])`; the optional argument is allowed only as a
   singleton String and is ignored for non-String Date inputs.
3. `toDateTime()` and `convertsToDateTime()` must implement the current
   FHIRPath signature `([format : string])`; the optional argument is allowed
   only as a singleton String and is ignored for non-String DateTime inputs.
4. Date and DateTime format parsing must be general token-based behavior, not
   a list of probe-specific literals. Required current tokens include year,
   month, day, hour, minute, second, fractional second, AM/PM marker, and
   numeric timezone offset.
5. Date conversion from formatted DateTime-like strings must validate the full
   formatted value before projecting the date portion; invalid trailing time
   components cannot be silently ignored.
6. Conversion predicates such as `convertsToDate()` and
   `convertsToDateTime()` must share the same parser and input rules as their
   corresponding conversion functions, returning Boolean success/failure
   rather than drifting into a separate loose implementation.
7. `toDecimal()` and `convertsToDecimal()` remain exact zero-argument
   conversion functions; Date/DateTime optional format support must not relax
   Decimal arity.
8. Decimal conversion must accept spec-defined numeric inputs, including
   current STU Long literals, without routing through display string
   comparison or arbitrary host-language truthiness.
9. Long literal support must be parser-level in both Python and native paths.
   Uppercase `L` suffixes on integer digits are valid; malformed suffixes such
   as doubled, lowercase, or decimal Long suffixes remain invalid expressions.
10. Public result UDFs must remain row-resilient for invalid arity, invalid
    format argument shapes, invalid Long suffixes, and failed conversions;
    `fhirpath_is_valid()` is the expression-validity signal.
11. Native evaluator, packaged extension binary, Python fallback metadata, and
    focused parity tests must move together when an FP-07 signature or literal
    grammar boundary changes.
