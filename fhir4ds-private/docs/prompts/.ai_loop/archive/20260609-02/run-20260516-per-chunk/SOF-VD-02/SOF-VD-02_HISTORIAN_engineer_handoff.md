# Engineer Handoff: SOF-VD-02 HISTORIAN

## Issues Resolved

- `SOF-VD-02-HIST-001`: Removed parser/public-constructor acceptance of non-spec complex constant choices `valueCoding` and `valueCodeableConcept`. These now fail as unsupported `value[x]` fields.
- `SOF-VD-02-HIST-002`: Added centralized FHIR primitive validation for `ViewDefinition.constant.value[x]` values before constants can be substituted into FHIRPath.
- `SOF-VD-02-HIST-003`: Updated `ViewDefinition.from_dict()` to parse the spec singular `constant` element, with `constants` retained as a compatibility alias.

## Files Changed

- `fhir4ds/viewdef/types.py`
- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/tests/unit/test_constants.py`
- `fhir4ds/viewdef/AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`
- `fhir4ds-private/docs/prompts/.ai_loop/qa_handoff.md`
- `fhir4ds-private/docs/prompts/.ai_loop/engineer_handoff.md`

## Validation

- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_constants.py fhir4ds/viewdef/tests/test_spec_compliance.py -q`
  - 546 passed.
- `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py -q`
  - 28 passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q`
  - 735 passed.
- `python3 -m pytest fhir4ds/ -x --tb=short | tail -n 50`
  - 7272 passed, 5 skipped, 9 warnings.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`
  - ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes for Architect

- The fix is centralized in `types.py` so both `parse_view_definition()` and `Constant.from_dict()` share the same field allowlist and primitive value validation.
- `resolve_constant()` still handles manually constructed `Constant(..., value_type="Coding")` objects to avoid unnecessarily breaking low-level helper callers; ViewDefinition JSON parsing no longer accepts those fields.
