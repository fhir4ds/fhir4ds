# FP-14 EXPLORER Golden Standard

Scope: FHIRPath §6.2 Comparison in `fhir4ds.fhirpath` and the native
DuckDB extension.

1. Public DuckDB FHIRPath comparison behavior must match between the bundled
   native C++ extension and forced Python fallback for `fhirpath`,
   `fhirpath_json`, `fhirpath_bool`, and `fhirpath_is_valid` wherever both
   registrations exist.
2. Comparison operators must preserve FHIRPath collection semantics: empty
   operands return empty, multi-item operands are row-resilient at public UDF
   boundaries, and deterministic invalid literal expressions may make
   `fhirpath_is_valid` false.
3. Numeric comparison must not pass exact Integer, Long, Decimal, or JSON
   numeric path values through binary floating point when doing so can collapse
   adjacent values.
4. Quantity comparison must first materialize FHIR Quantity JSON/path values
   as Quantity values, respect units, reject non-commensurable dimensions with
   empty results, and avoid precision loss for same-unit source-text values.
5. Mixed calendar-vs-UCUM year/month duration comparisons must remain
   incomparable unless explicit conversion intentionally moves both operands
   into the same code system.
6. Date, DateTime, and Time comparison must use typed temporal values rather
   than raw String ordering, including resource-backed FHIR primitive paths and
   timezone-offset normalization.
7. Partial Date, DateTime, and Time precision mismatches that are equal at
   shared precision must return empty rather than an arbitrary Boolean.
8. String comparison must remain strict lexical ordering by Unicode scalar
   value and must not inherit String equivalence normalization rules.
9. Python fallback, direct Python evaluator, native C++ evaluator, parser, and
   bundled extension binaries must move together when comparison logic changes.
10. Fresh QA probes under `.temp` must import the repository checkout, not any
    installed `fhir4ds` package, or they can produce false native/fallback
    comparison findings.
