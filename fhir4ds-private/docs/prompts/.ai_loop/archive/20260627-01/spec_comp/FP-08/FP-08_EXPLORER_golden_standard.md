# Golden Standard - FP-08 EXPLORER

Scope: FHIRPath §5.5.7 Quantity Conversion, §5.5.8 String Conversion, and
§5.5.9 Time Conversion across Python fallback and native DuckDB/C++ surfaces.

## Invariants

1. Public `toString()` output for Decimal and Quantity values must use
   FHIRPath decimal digit notation, never host-language exponent notation.
2. String formatting must be presentation-only; semantic equality and set
   behavior must continue to use typed numeric/Quantity comparison paths.
3. Python fallback and native DuckDB extension registrations must agree for
   every public result wrapper: list, text, JSON, bool, quantity, and validity.
4. Resource-backed FHIR Quantity JSON must materialize as Quantity input for
   `toQuantity()`, `convertsToQuantity()`, `toString()`, and
   `convertsToString()`, not as opaque object text.
5. Resource-backed primitive JSON numbers must retain Decimal semantics at
   conversion/string boundaries, including small and large values.
6. Long values converted to Quantity must preserve exact public integer text
   for string output and must not lose a unit in `double` formatting.
7. Optional `toQuantity([unit])` and `convertsToQuantity([unit])` arguments are
   ordinary FHIRPath expressions evaluated against the caller focus, with empty
   and multi-item arguments preserving the established singleton behavior.
8. Time conversion must preserve partial precision, reject invalid ranges, and
   stay row-resilient through public DuckDB wrappers.
9. Native C++ changes must be rebuilt and copied into the package bundle before
   package-level validation; extension hashes must match build, repository, and
   bundled locations.
10. Focused tests must cover both native-loaded and forced Python fallback
    registrations before full conformance is trusted.

## Audit Result

The FP-08 EXPLORER fix satisfies these invariants. No new architectural finding
was opened.
