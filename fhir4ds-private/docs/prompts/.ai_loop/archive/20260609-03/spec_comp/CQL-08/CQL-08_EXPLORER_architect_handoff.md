# Architect Handoff - CQL-08 EXPLORER

Architectural result: pass, no additional open findings.

Golden standard used: CQL nullological translation must preserve the CQL value type `T` across scalar, list, query-list, public DuckDB helper, and dynamic FHIR-path boundaries. Boolean truth helpers must remain Boolean-only. Quantity values must stay whole Quantity values until a Quantity comparison or explicit `.value` property asks for Decimal. Native-loaded and forced Python fallback registrations must expose equivalent behavior.

Audit summary:

- The Boolean public helper fix stays at the DuckDB UDF/macro boundary and does not add type-specific translator hacks.
- The Quantity comparison fix extends existing semantic type inference and reuses the established `quantity_compare` path.
- The dynamic FHIR Boolean fix is type-directed by Boolean Coalesce peers and uses the existing `fhirpath_bool` UDF rather than SQL truthiness.
- The CMS832 regression was caused by an over-broad inference rule and was corrected by preserving the type boundary between Quantity and Quantity.value.

No `RETRY_QA` is needed. QA covered direct helpers, translated scalar/list/query compositions, clinical/Quantity/temporal values, dynamic Patient Boolean paths, native-loaded vs forced Python fallback registrations, CMS832 DQM, adjacent parity, and full conformance.

Recommended fix order: complete. All three issues are `VERIFIED`.
