# Golden Standard - FP-14 HISTORIAN

Scope: FHIRPath 6.2 Comparison in Python fallback and native DuckDB/C++ public
FHIRPath surfaces.

Architectural invariants:

1. FHIRPath comparison semantics must be type-driven, not transport-string-
   driven; resource-backed primitives must be materialized according to FHIR
   type metadata before ordering.
2. Native DuckDB/C++ and forced Python fallback registrations must return the
   same public results for the same resource and expression wherever both
   backends implement the surface.
3. Comparison operators must preserve FHIRPath collection semantics: empty
   operands return empty, multi-item operands are singleton errors surfaced as
   row-resilient empty/NULL public UDF outputs, and expression validity remains
   separate from sample evaluation emptiness.
4. Numeric, Long, Decimal, JSON numeric, and same-unit Quantity ordering must
   avoid lossy binary floating-point comparison when authored or source JSON
   text can preserve exact decimal ordering.
5. Quantity comparison must respect dimensions and commensurability; unit
   conversion belongs in shared Quantity helpers rather than expression-specific
   hardcoding.
6. Date, DateTime, and Time ordering must route through temporal value types
   (`FP_Date`, `FP_DateTime`, `FP_Time`) so precision and timezone behavior is
   centralized in `FP_TimeBase.compare()`.
7. Fixes must be general over FHIR primitive type metadata such as `date`,
   `dateTime`, `instant`, and `time`; code must not special-case individual
   resource fields such as `Observation.effectiveDateTime`.
8. Public wrapper functions may be row-resilient, but should not silently
   redefine FHIRPath semantics; incompatible comparisons return empty/NULL
   consistently and valid expressions remain `fhirpath_is_valid = true`.
9. Regression tests must include both native-loaded and forced Python fallback
   DuckDB connections when a bug is backend parity-related.
10. Fresh probe scripts under `.temp/qa` must force the workspace root onto
    `sys.path` before importing `fhir4ds`, preventing accidental validation of
    an installed package or stale bundled extension.
