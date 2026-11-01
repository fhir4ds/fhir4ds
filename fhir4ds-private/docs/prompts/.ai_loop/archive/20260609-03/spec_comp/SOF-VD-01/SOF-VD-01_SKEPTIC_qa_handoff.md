# QA Handoff: SOF-VD-01 SKEPTIC

Scope: SQL-on-FHIR ViewDefinition root logical-model fields `resource`, `profile`, and `fhirVersion`, plus shared-table resource filtering and zero-or-more output rows.

Spec anchors consulted:
- SQL-on-FHIR v2.1.0-pre ViewDefinition definitions: `ViewDefinition` is a tabular projection of a FHIR resource; `resource` is 1..1 code with required ResourceType binding; `profile` is 0..* canonical(StructureDefinition); `fhirVersion` is 0..* code with required FHIRVersion binding; `select` is 1..*.
- SQL-on-FHIR v2.0.0 key elements: each ViewDefinition is tied to one FHIR resource type and creates zero or more rows per resource instance.
- FHIR R5 JSON representation: repeating elements are arrays, primitive canonical values are JSON strings matching canonical/URI syntax.

Fresh probes:
- Verified parser rejects missing/unknown/non-string `resource`, malformed `fhirVersion`, null optional arrays, and non-array `profile`.
- Verified generated SQL with `SQLGenerator(source_table="resources")` adds a root `resourceType` filter for mixed-resource physical tables.
- Found one HIGH issue: `profile` values are accepted as any non-empty string rather than canonical strings, and direct `ViewDefinition(..., profile='not a list')` bypasses the 0..* array shape during SQL generation.

Issue logged:
- `SOF-VD-01-SKEPTIC-001` OPEN: parser/direct-generator boundary accepts malformed ViewDefinition.profile declarations.
