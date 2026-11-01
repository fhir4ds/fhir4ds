# FP-15 Golden Standard

Scope: FHIRPath §6.3 type operators across Python core, DuckDB Python fallback,
and native C++ DuckDB extension.

## Invariants

1. Type-specifier validation must be model-driven. A type accepted for subtype
   matching must also be accepted by `is`, `is()`, `as`, `as()`, and `ofType()`.
2. Native FHIR resource/datatype type knowledge must not drift across separate
   allowlists; validation and hierarchy checks should share one source or one
   wrapper around the same hierarchy.
3. FHIR primitive names and System primitive names must remain namespace-aware:
   `FHIR.boolean` and `System.Boolean` are distinct where the spec and R4 tests
   require it.
4. Public DuckDB result UDFs must be row-resilient for runtime singleton errors
   and invalid type specifiers while keeping `fhirpath_is_valid()` aligned with
   expression validity.
5. `as` is a singleton type assertion, not a collection filter; `ofType` is the
   collection filter.
6. Choice-type values selected through `value[x]` paths must preserve enough
   type context for downstream `is` and `as` checks in both native and fallback
   registrations.
7. Forced Python fallback and native C++ registrations must match across list,
   text, JSON, Boolean, and scalar public wrappers.
8. Native extension changes must be rebuilt and copied into
   `fhir4ds/fhirpath/duckdb/extensions/`, and hashes must match build,
   repository, and package copies.
9. Regression coverage must include both direct happy paths and known invalid
   boundaries: unknown type specifiers, empty input, and multi-item singleton
   operands.
10. Fixes must generalize to the model metadata category rather than naming only
    the exposed fixture resources.
