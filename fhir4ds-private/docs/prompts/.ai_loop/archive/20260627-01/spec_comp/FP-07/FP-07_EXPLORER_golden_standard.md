# Golden Standard: SOF-VD-12 / EXPLORER

1. Supported SQL-on-FHIR logical-model profiles are activated only through canonical URLs in `ViewDefinition.meta.profile`, with version suffixes ignored for profile identity.
2. ShareableViewDefinition constraints must be enforced consistently at strict parse, public `from_dict()`, direct `to_dict()`, SQL generation, and permissive validation boundaries.
3. TabularViewDefinition constraints must reject collection columns and non-primitive column types before SQL generation can coerce or mask invalid output.
4. Root canonical metadata that is supported by this implementation must validate as FHIR JSON primitives and must round-trip without altering generated SQL semantics.
5. Official JSON field names are the only emitted serializer surface: singular `constant` and `tag` are valid, while legacy plural aliases are rejected on strict input.
6. Unsupported XML representation must fail explicitly and early; XML input must not be misreported as generic malformed JSON.
7. Unsupported top-level mapping fields are intentionally ignored and omitted unless the logical model adds a supported mapping element.
8. Profile metadata must not change the current resource filter or FHIRPath execution context for valid views.
9. Native-loaded DuckDB FHIRPath and forced Python fallback must agree for metadata-heavy ViewDefinition execution.
10. Scratch probes under `.ai_loop/.temp` must prepend the repository root, not `fhir4ds-private`, to avoid importing stale installed packages.
