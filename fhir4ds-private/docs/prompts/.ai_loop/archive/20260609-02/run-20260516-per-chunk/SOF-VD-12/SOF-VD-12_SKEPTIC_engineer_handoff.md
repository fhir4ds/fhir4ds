# Engineer Handoff - SOF-VD-12 SKEPTIC

## Triage
- `QA-001` SPEC_VIOLATION, MEDIUM, resolved.
- `QA-002` SPEC_VIOLATION, MEDIUM, resolved.
- `QA-003` DOCUMENTATION_GAP, LOW, resolved.

## Fixes
- Added parser/model retention for SQL-on-FHIR root metadata fields in scope:
  `resourceType`, `id`, `meta`, `url`, `version`, `status`, `title`, and
  existing `description`.
- Added `ViewDefinition.to_dict()` plus nested serializers using official JSON
  field names (`constant`, `tag`, `fhirVersion`, etc.) so parser/generator
  inputs can round-trip.
- Added supported-profile validation from `meta.profile`:
  ShareableViewDefinition requires `url`, `name`, `fhirVersion`, and every
  column `type`; TabularViewDefinition rejects collection columns and
  non-primitive column types.
- Added explicit XML unsupported parse error and documented the JSON-only public
  parser boundary.

## Validation
- `python3 .temp/qa/sof_vd12_skeptic/probe_sof_vd12.py`: reproducer now shows
  metadata retained, invalid Shareable/Tabular views rejected, XML rejected with
  explicit unsupported message, and official PatientDemographics-style execution
  matching native C++ and forced Python fallback.
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py fhir4ds/viewdef/tests/integration/test_duckdb.py::test_shareable_metadata_does_not_change_execution_native_and_fallback -q`: 202 passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q | tail -n 50`: 894 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2822/2822.
