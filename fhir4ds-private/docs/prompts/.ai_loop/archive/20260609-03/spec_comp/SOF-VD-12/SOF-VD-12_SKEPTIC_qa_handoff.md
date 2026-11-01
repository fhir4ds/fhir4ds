# QA Handoff - SOF-VD-12/SKEPTIC

Fresh SKEPTIC pass for SQL-on-FHIR ViewDefinition profiling and representations.
I read the current loop rules, ViewDefinition guidance, current source, local
tests, and the current SQL-on-FHIR continuous-build pages for ViewDefinition,
ShareableViewDefinition, and TabularViewDefinition.

Spec anchors:
- ViewDefinition is a CanonicalResource-derived logical model with `resource`
  bound to ResourceType, `profile`/`fhirVersion` arrays, and JSON field names
  such as singular `constant` and `tag`.
- ShareableViewDefinition requires `url`, `name`, `fhirVersion`, and
  `select.column.type`.
- TabularViewDefinition forbids collection columns and limits column `type` to
  primitive FHIR types.

Fresh probe:
- `.ai_loop/.temp/qa/sof_vd12_skeptic_probe.py`

Coverage:
- Valid ShareableViewDefinition with version-suffixed `meta.profile` parsed,
  serialized, reparsed, and generated SQL successfully.
- JSON field-name round trip preserved singular `tag` and omitted unsupported
  top-level `mapping`.
- XML input failed with the explicit unsupported-XML ParseError.
- Strict parser and generator rejected invalid direct Shareable/Tabular
  profile shapes.

Finding:
- `SOF-VD-12-SKEPTIC-001` MEDIUM OPEN.
- Direct `ViewDefinition.to_dict()` emitted official JSON for invalid
  Shareable/Tabular dataclasses that strict parse/generation reject, and
  `validate_view_definition()` returned no warnings for those supported profile
  violations.

Recommended fix:
- Route `ViewDefinition.to_dict()` through `validate_supported_view_profiles()`
  after metadata normalization and before returning JSON.
- Add permissive warnings from `validate_supported_view_profiles()` inside
  `validate_view_definition()`.
- Add focused parser tests for direct serializer and validator behavior.
