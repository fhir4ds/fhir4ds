SOF-VD-10/SKEPTIC remediation handoff

Resolved issue:
- `SOF-VD-10-SKEPTIC-001` HIGH, spec violation. Strict parser and `ViewDefinition.from_dict()` accepted present JSON null for optional root metadata.

Root cause:
- `parse_view_definition()` passed `data.get(...)` for optional root metadata into `validate_root_metadata_fields()`, which erased the distinction between absent fields and present JSON null.

Fix:
- Added `_parse_optional_root_metadata()` in `fhir4ds/viewdef/parser.py`.
- Routed `resourceType`, `id`, `meta`, `url`, `version`, `status`, `title`, and `description` through that guard before shared metadata validation.
- Added parser/`from_dict` regression coverage for all affected fields.
- Added a direct dataclass regression proving `None` still serializes as omitted metadata.

Validation:
- `python3 .temp/qa/sof_vd_10_skeptic_probe.py` passed.
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --tb=short` passed: 204/204.
- `python3 -m pytest fhir4ds/viewdef/tests -q --tb=short` passed: 969/969.
- `python3 conformance/scripts/run_viewdef.py` passed: 134/134.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` passed: 2822/2822 overall.

New issues:
- None.
