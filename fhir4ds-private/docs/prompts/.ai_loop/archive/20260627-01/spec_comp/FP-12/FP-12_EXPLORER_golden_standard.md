# Golden Standard - FP-12 Tree Navigation / Utility Functions

1. `children()` is the single source of truth for immediate-node traversal in
   both Python fallback and native C++; `descendants()` must derive behavior
   from repeated `children()` traversal rather than reimplementing a divergent
   child model.
2. FHIR JSON primitive sibling metadata (`_field`) is model metadata for the
   primitive element, not a root child named `_field`; root `children()` must
   hide the raw underscore field while the primitive element's own
   `children()` may expose `id` and `extension` metadata.
3. Primitive metadata propagation must be structural and generic: code may zip
   `field[i]` with `_field[i]`, but must not special-case `birthDate`,
   `given`, URLs, resource IDs, or fixture values.
4. Native and Python fallback paths must preserve the same logical node model
   for primitive metadata, including nested primitives such as `name.given`.
5. Native FP values may carry non-owning yyjson pointers only while the owning
   document is alive; no primitive metadata pointer may outlive the evaluator
   batch/document lifetime.
6. Tree traversal must preserve existing null-child behavior: JSON null values
   remain visible to `children()` / `descendants()`, while ordinary field
   navigation may still skip null values.
7. `trace(name, projection)` remains identity over the input collection; adding
   primitive metadata must not alter trace scoping, `$index`, or dynamic label
   evaluation.
8. Current-date/time helpers are zero-argument utility functions and must stay
   deterministic within a single expression in both native and fallback paths.
9. Public DuckDB wrappers must remain row-resilient for invalid utility
   signatures: invalid calls return empty/NULL public results and
   `fhirpath_is_valid=false`.
10. The bundled native extension must match the rebuilt extension artifact after
    native source changes.
