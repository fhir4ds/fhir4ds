# Engineer Handoff - CQL-02 HISTORIAN

Resolved `CQL02-HIST-001`.

Changes preserve structured clinical CQL values and metadata:
- `SQLTranslationContext` stores code system versions and code versions.
- Code selectors/named codes emit JSON-shaped Code values with `code`, `system`, optional `version`, and optional `display`.
- Named `ValueSet`/`CodeSystem` references emit structured JSON values for clinical value/type contexts.
- Clinical constructors/selectors/references are inferred as `Code`, `Concept`, `ValueSet`, `CodeSystem`, or `Vocabulary`.
- `ValueSet`, `CodeSystem`, and `Vocabulary` definitions are treated as scalar clinical values rather than FHIR resource rows.
- Clinical `is`/`as` uses preserved `definition_meta.cql_type` before generic FHIR `resourceType` probing.

Membership boundaries now unwrap structured ValueSet JSON to canonical URL:
- General `in`/`contains` placeholder handling routes structured ValueSet parameters to `in_valueset`.
- `hasPrincipalDiagnosisOf` and `hasPrincipalProcedureOf` fluent builders normalize structured `ValueSet` literals before generating `in_valueset(..., url)`.

No C++ native code was changed for this issue, so no CQL/FHIRPath extension rebuild was required.
