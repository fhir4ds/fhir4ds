# Engineer Handoff: SOF-VD-03 EXPLORER

## Fixed

- `SOFVD03-EXPLORER-001` resolved. `parse_view_definition()` now rejects a
  present JSON null `ViewDefinition.select.column.description` instead of
  treating it as absent metadata. The fix is intentionally parser-scoped:
  direct dataclass `Column(description=None)` still represents an omitted
  optional description and remains valid for `to_dict()`/`SQLGenerator`.

## Changed Files

- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd03_explorer_probe.py`
- `.ai_loop/qa_handoff.md`
- `.ai_loop/engineer_handoff.md`

## Validation

- Fresh probe: `python3 .temp/qa/sof_vd03_explorer_probe.py` PASS
- Parser unit tests: `180 passed`
- Select/context integration slice: `6 passed`
- Official combinations/spec execution slice: `138 passed`
- Full ViewDefinition pytest: `941 passed`
- ViewDefinition conformance: `134/134`
- Full conformance: `2822/2822`

## Notes

The spec boundary is the JSON parser/public-constructor input path. The
dataclass API cannot distinguish omitted optional metadata from a caller
assigning `None`, so serializer/generator paths continue to treat `None` as
absent and validate non-`None` description values as markdown strings.
