# SOF-VD-01 HISTORIAN QA Handoff

## Scope

SQL-on-FHIR ViewDefinition root fields for chunk SOF-VD-01:
`ViewDefinition.resource`, `profile`, `fhirVersion`, root resource table
selection/resourceType filtering, and zero-or-more output rows per resource
instance.

## Spec Basis

SQL-on-FHIR v2.0.0 ViewDefinition says a ViewDefinition is a tabular
projection of a FHIR resource. The Resource key element ties each
ViewDefinition instance to a single FHIR resource type and may create zero or
more rows for each resource instance. The detailed logical model defines
`ViewDefinition.resource` as `1..1 code` with required ResourceType binding,
`ViewDefinition.fhirVersion` as `0..* code` with required FHIRVersion binding,
and `profile` as repeatable canonical profile declarations.

## Probes

- Parser rejection: missing `resource`, array-valued `resource`, unknown
  ResourceType, scalar `profile`, non-string `profile` item, and unknown
  `fhirVersion` code.
- Parser preservation: repeatable `profile` and `fhirVersion` survive parsing.
- SQL generation: `SQLGenerator(source_table="resources")` emits a
  `json_extract_string(t.resource, '$.resourceType') = 'Patient'` filter.
- DuckDB execution: mixed `resources` table with two Patients and one
  Observation. A Patient ViewDefinition using `forEach: "name"` produced two
  rows for one Patient, zero rows for the Patient with no names, and zero rows
  for the Observation.
- Backend parity: same ViewDefinition output compared on native C++ extension
  registration and forced Python fallback registration.

## Result

No issues found. Focused validation passed:

- Custom SOF-VD-01 HISTORIAN probe: all checks passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py fhir4ds/viewdef/tests/integration/test_duckdb.py fhir4ds/viewdef/tests/test_spec_compliance.py -q`
  passed 534/534.
