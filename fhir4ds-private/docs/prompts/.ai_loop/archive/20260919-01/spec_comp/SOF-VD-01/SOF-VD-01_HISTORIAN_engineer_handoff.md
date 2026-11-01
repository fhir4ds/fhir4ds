# Engineer Handoff — SOF-VD-01, iteration 1

## Triage
- QA-001 MEDIUM SPEC_VIOLATION CONFIRMED → fixed.
- QA-002 LOW SPEC_NOTE → INTENDED (cross-version R4-R6 superset; documented in AGENTS.md).

## QA-001 fix
- Root cause: fhir4ds/viewdef/metadata.py:KNOWN_FHIR_RESOURCE_TYPES predates R6's DeviceAlert; the required binding (http://hl7.org/fhir/ValueSet/resource-types, verified live: 120 codes incl. DeviceAlert) therefore rejected a valid ViewDefinition.resource.
- Change: added "DeviceAlert" to the frozenset (single choke point used by both ViewDefinition.resource and Join.resource validation).
- Test: fhir4ds/viewdef/tests/unit/test_parser.py::TestViewDefinitionParsing::test_new_r6_resource_type_device_alert_accepted.

## Validation (fresh, final tree)
- ViewDef pytest: 1128/1128 passed (was 1127 + 1 new).
- run_viewdef.py: 144/144.
- run_all.py master gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
- Binary md5s unchanged (pure-Python fix): cql.duckdb_extension c5b22d58310c1eb7bafa17ce7877f989 (repo == site-packages); fhirpath.duckdb_extension repo == site-packages 57d0634b6ee6eddee9fc06a1355bef5a.
