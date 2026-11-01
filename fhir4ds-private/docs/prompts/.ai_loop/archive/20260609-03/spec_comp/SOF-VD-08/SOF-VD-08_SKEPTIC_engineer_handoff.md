# Engineer Handoff: SOF-VD-08 / SKEPTIC

## Fixed

`SOFVD08-SKEPTIC-001` was reproduced with the fresh probe. Root cause:
`_parse_select()` reused the generic repeating-object parser for `unionAll`, so
an explicitly present empty JSON array became indistinguishable from omitted
`unionAll`.

Implemented a narrow parser fix:
- `parser._parse_object_array()` now accepts a `require_non_empty` flag.
- `_parse_select()` uses it only for `unionAll`, requiring at least one branch
  object when the field is present.
- `ViewDefinition.from_dict()` inherits the same strict boundary because it
  delegates to `parse_view_definition()`.

Direct dataclass `Select.unionAll=[]` remains the absent/default state; the fix
targets official JSON input where field presence is observable.

## Tests

- `.temp/qa/sof_vd08_skeptic_probe.py`: PASS
- Focused parser/generator/union/DuckDB pytest: 339 passed
- ViewDefinition spec pytest: 435 passed
- Full ViewDefinition pytest: 953 passed
- ViewDefinition conformance: 134/134
- Full conformance: 2822/2822

## Files Changed

- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd08_skeptic_probe.py`
- `.ai_loop/evolution.json`
