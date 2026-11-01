# Golden Standard - FP-08 HISTORIAN

Date: 2026-06-12

Scope: FHIRPath §5.5.7-§5.5.9 Quantity, String, and Time conversion behavior
across `fhir4ds.fhirpath`, the DuckDB Python fallback, and the native DuckDB
C++ extension.

## Invariants

1. FHIRPath conversion semantics must be spec-grounded at the core evaluator
   boundary, not encoded only in DuckDB wrapper behavior.
2. Native DuckDB/C++ and forced Python fallback public UDFs must return the same
   values for supported FHIRPath conversion expressions.
3. Public result wrappers must stay row-resilient: invalid singleton conversion
   errors return empty/NULL public results while `fhirpath_is_valid()` remains
   the validity signal.
4. `toQuantity([unit])` and `convertsToQuantity([unit])` must treat `unit` as a
   normal FHIRPath expression evaluated in the caller's current focus.
5. Quantity conversion must not coerce incompatible units silently; incompatible
   unit conversion returns empty for `toQuantity()` and false for
   `convertsToQuantity()`.
6. Quantity `toString()` must render with decimal digit notation and must not
   emit host-language scientific notation.
7. Python Decimal scale preservation must remain intact for official FHIRPath
   conformance cases; avoiding exponent notation must not strip meaningful
   trailing zeros.
8. Native C++ Quantity formatting must avoid default stream exponent output
   without changing semantic equality or using string output for comparisons.
9. Time conversion must preserve partial precision and reject invalid ranges in
   both native and fallback paths.
10. Native evaluator changes require sqllogictest coverage, rebuild, copied
    bundled extension, and hash freshness verification.
11. Focused tests must cover both native-loaded DuckDB registration and forced
    Python fallback registration for DuckDB-backed FHIRPath behavior.
12. Loop state must archive enough evidence for resumed agents without requiring
    prior chat context or stale artifacts.
