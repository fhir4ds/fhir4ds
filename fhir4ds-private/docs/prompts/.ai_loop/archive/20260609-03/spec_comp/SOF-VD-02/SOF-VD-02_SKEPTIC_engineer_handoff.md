# Engineer Handoff - SOF-VD-02 SKEPTIC

## Resolved Issues

All four QA findings are resolved.

- `SOFVD02-SKEPTIC-001`: `parse_view_definition()` now rejects the legacy
  plural `constants` alias and requires the SQL-on-FHIR singular `constant`
  array.
- `SOFVD02-SKEPTIC-002`: `resolve_constants_in_path()` now raises
  `ConstantResolutionError` for undefined user constants while preserving
  built-in FHIRPath variables.
- `SOFVD02-SKEPTIC-003`: duplicate constant names are rejected by parser and
  `ConstantResolver` construction/addition paths.
- `SOFVD02-SKEPTIC-004`: `validate_constant_fields()` centralizes direct
  `Constant` object validation and is reused by `Constant.to_dict()` and
  `SQLGenerator._validate_constants()`.

## Files Changed

- `fhir4ds/viewdef/types.py`
- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/constants.py`
- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/unit/test_constants.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/tests/unit/test_generator.py`
- `fhir4ds/viewdef/tests/unit/test_where.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd02_skeptic_probe.py`

## Validation

- Fresh probe: `.temp/qa/sof_vd02_skeptic_probe.py` PASS
- Focused constants/parser/generator/where/DuckDB pytest: 98 passed
- Full ViewDefinition pytest: 916 passed
- ViewDefinition conformance: 134/134
- Full conformance: 2822/2822

## Notes For Architect

The fix intentionally tightens strict parser/public constructor behavior around
the known legacy alias `constants`. The permissive `validate_view_definition()`
warning API remains unchanged. Constant validation metadata is centralized in
`types.py`; future changes to the SQL-on-FHIR `value[x]` choice set should be
made there first.
