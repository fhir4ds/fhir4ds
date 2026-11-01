# Golden Standard - FP-08 SKEPTIC

Scope: FHIRPath §5.5.7 Quantity Conversion, §5.5.8 String Conversion, §5.5.9 Time Conversion across native DuckDB/C++ and forced Python fallback paths.

Invariants:
1. FHIRPath conversion function signatures must match the specification exactly; extra, missing, multi-item, or wrong-type singleton arguments must be rejected consistently by native and fallback paths.
2. Single-input conversion functions must preserve FHIRPath empty propagation: empty input returns empty, empty singleton argument returns empty unless the function explicitly documents another result.
3. Ordinary non-scoped function arguments must evaluate in the caller/outer invocation context; only documented scoped functions may introduce special `$this` or `$index` argument scopes.
4. Native DuckDB and forced Python fallback must agree for public wrapper UDFs (`fhirpath`, typed wrappers, and `fhirpath_is_valid`) on conversion success, empty/NULL behavior, and validity classification.
5. Resource-backed FHIR Quantity objects must be materialized as Quantity values before conversion or stringification; invalid Quantity-like JSON must not be silently coerced.
6. Quantity unit conversion must use general UCUM/calendar-duration conversion logic, not per-expression literals or test-specific cases.
7. `toString()` and `convertsToString()` must reject structural JSON/List/Tuple shapes while accepting supported primitive, temporal, and Quantity values.
8. `toTime()` and `convertsToTime()` must preserve authored precision and reject malformed ranges or timezone-suffixed time-only values.
9. Public result UDFs must remain row-resilient for spec errors, returning empty/NULL while `fhirpath_is_valid()` carries validity.
10. Native source changes must be followed by a rebuild and copied bundled extension; build, repository, and package extension hashes must match.
11. Fresh QA probes under `.temp/qa` must explicitly import the repository checkout, not an installed site-packages `fhir4ds`.
12. Regression coverage must include literal arguments, dynamic sibling arguments, scoped `select()` arguments, native sqllogictest assertions, and forced Python fallback parity.
