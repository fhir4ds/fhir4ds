# SOF-VD-01 EXPLORER QA Handoff

## Scope

SQL-on-FHIR ViewDefinition root logical-model fields for chunk SOF-VD-01:
`ViewDefinition.resource`, `profile`, and `fhirVersion`; root resource table
selection and shared-table resourceType filtering; zero-or-more output rows per
root resource instance.

## Spec Basis

Verified against the SQL-on-FHIR ViewDefinition logical model. The current
2.1.0-pre page defines `resource` as 1..1 with required ResourceType binding,
`profile` as 0..* canonical StructureDefinition declarations based on the root
resource, and `fhirVersion` as 0..* FHIRVersion-bound code. The published
2.0.0 page defines ViewDefinition as a tabular projection of a FHIR resource and
documents `forEachOrNull` preserving a row with null nested values when empty.

## Probes

- Parser abuse: missing `resource`, array-valued `resource`, unknown
  ResourceType text, scalar `profile`, and invalid `fhirVersion`.
- Generated SQL abuse: `SQLGenerator(source_table="resources")` over a mixed
  `resources` table containing Observation and Patient resources.
- DuckDB execution: a root Patient view with nested `forEachOrNull` over
  `telecom` produced two rows for a Patient with two telecom entries and one
  null nested row for a Patient with no telecom; the Observation row was
  filtered out.
- Backend parity: native C++ FHIRPath registration and forced Python fallback
  registration returned identical ViewDefinition rows.

## Findings

No new issues. Current code correctly rejects invalid root metadata, preserves
`profile`/`fhirVersion`, emits the shared-table resourceType filter, and
preserves `forEachOrNull` rows.

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/sof_vd_01_explorer_probe.py`
  passed with identical native/fallback results.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/integration/test_duckdb.py fhir4ds/viewdef/tests/test_spec_compliance.py -q`
  passed 505/505.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_viewdef.py`
  reported 134/134 passing.
