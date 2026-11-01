# Engineer Handoff: SOF-VD-10 EXPLORER

Issue resolved:
- `SOF-VD-10-EXPLORER-001` MEDIUM, RESOLVED.

Fix:
- Extended permissive `validate_view_definition()` in
  `fhir4ds/viewdef/parser.py` so it reports warnings for direct-dataclass
  SOF-VD-10 violations that strict parser/generator paths already reject:
  ResourceType binding, FHIRVersion binding, root `ViewDefinition.name`,
  `Column.name`, `Constant.name`, root metadata, profile, constant field, and
  select iterator shape validation.
- Added focused unit coverage in `fhir4ds/viewdef/tests/unit/test_parser.py`.
- Updated `fhir4ds/viewdef/AGENTS.md` with the validator boundary lesson.

Validation:
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd10_explorer_probe.py`
  -> PASS.
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q`
  -> 209 passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q`
  -> 974 passed.
- `python3 conformance/scripts/run_viewdef.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|passed|Passed|Total"`
  -> 134/134.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`
  -> 2822/2822.

Notes for Architect:
- Strict parse/generation behavior was already correct; the defect was limited
  to the public permissive warning API returning false negatives.
- No new open issues remain in this pass.
