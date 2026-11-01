# QA Handoff: SOF-VD-01 SKEPTIC

## Scope

SQL-on-FHIR ViewDefinition logical-model root fields for `resource`, `profile`, and `fhirVersion`, plus shared root resource table filtering and zero-or-more row behavior.

## Spec Basis

Official SQL-on-FHIR ViewDefinition logical model defines `ViewDefinition.resource` as 1..1 `code` with required `ResourceType` binding, `profile` as 0..* canonical StructureDefinition declarations, and `fhirVersion` as 0..* `code` with required FHIRVersion binding. The model describes a ViewDefinition as a tabular projection of one FHIR resource type that produces zero or more rows per resource instance.

## Probes

- `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_01_skeptic_probe.py`
- Output saved to `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_01_skeptic_probe_before.json`

## Findings

- `SOF-VD-01-QA-001` HIGH: parser accepts `resource` arrays and generator emits multi-resource `UNION ALL`; parser also accepts unknown ResourceType codes with only a warning.
- `SOF-VD-01-QA-002` MEDIUM: parser silently drops `profile` and `fhirVersion` declarations instead of preserving and validating them.

## Non-Issue Checked

`SQLGenerator(source_table="resources")` correctly filters `resources` by `resourceType = 'Patient'`, returning only patient rows from a mixed Patient/Observation table in both available native-loaded registration attempt and forced Python fallback registration. In this environment both registration calls returned the Python fallback path.
