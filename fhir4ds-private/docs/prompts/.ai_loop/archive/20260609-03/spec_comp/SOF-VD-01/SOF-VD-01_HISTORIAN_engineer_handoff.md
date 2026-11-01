# Engineer Handoff - SOF-VD-01 HISTORIAN

## Issue Resolved

`SOF-VD-01-HISTORIAN-001` (HIGH): `ViewDefinition.to_dict()` could emit invalid
root logical-model JSON for direct dataclass construction. The parser and
SQLGenerator rejected adjacent invalid `resource`, `profile`, `fhirVersion`, and
`meta.profile` values, but the serializer returned invalid official JSON.

## Fix

- Added shared root validators in `fhir4ds/viewdef/types.py`:
  `validate_resource_type()` and `validate_fhir_version_array()`.
- Reused those validators from `parser.py`, `generator.py`, and
  `ViewDefinition.to_dict()`.
- Routed `to_dict()` root metadata through `validate_root_metadata_fields()`,
  so `meta.profile`, `resourceType`, `id`, `url`, `status`, title, and
  description validation now matches parser/generator behavior.
- Added serializer regression coverage in
  `fhir4ds/viewdef/tests/unit/test_parser.py`.
- Updated `fhir4ds/viewdef/AGENTS.md` with the serializer boundary invariant.

## Validation

- `.temp/qa/sof_vd01_historian_probe.py`: PASS.
- Focused parser/generator root validation tests: 14 passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q`: 906 passed.
- `python3 conformance/scripts/run_viewdef.py`: 134/134.
- `python3 conformance/scripts/run_all.py`: 2822/2822.

## Handoff

Proceed to ARCHITECT. No new issues were discovered during remediation.
