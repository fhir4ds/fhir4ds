# QA Handoff - SOF-VD-01 / SKEPTIC
Chunk: SOF-VD-01 (SQL-on-FHIR ViewDefinition)
Sections: Logical Model: View Definition, Key Elements: Resource, ViewDefinition.resource/profile/fhirVersion
Items: ViewDefinition represents a tabular projection of one FHIR resource type, resource 1..1 required FHIR ResourceType binding, profile 0..* canonical profile declarations, fhirVersion 0..* FHIRVersion binding, root resource table selection and resourceType filtering, zero-or-more output rows per resource instance
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (214 passed, 0 failed, 0 errors)

No issues found.
