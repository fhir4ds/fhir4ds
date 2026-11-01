# Engineer Handoff - SOF-VD-12/SKEPTIC

Resolved:
- `SOF-VD-12-SKEPTIC-001` MEDIUM.

Root cause:
- Supported ShareableViewDefinition and TabularViewDefinition profile
  validation was only used by strict parser and SQL generator paths.
  `ViewDefinition.to_dict()` could emit invalid profiled official JSON from
  direct dataclasses, and permissive `validate_view_definition()` returned no
  warnings for the same supported profile violations.

Fix:
- `fhir4ds/viewdef/types.py`: `ViewDefinition.to_dict()` now calls
  `validate_supported_view_profiles()` before returning JSON.
- `fhir4ds/viewdef/parser.py`: `validate_view_definition()` now collects
  supported profile constraint warnings when the direct select tree is safe to
  inspect.
- `fhir4ds/viewdef/tests/unit/test_parser.py`: added focused regressions for
  direct serializer rejection and permissive validator warnings.
- `fhir4ds/viewdef/AGENTS.md`: recorded the durable profile-boundary lesson.

Validation:
- Fresh probe: `PYTHONPATH=. python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd12_skeptic_probe.py` PASS.
- Focused regression before fix: 3 failed, 2 passed.
- Focused regression after fix: 5 passed.
- Parser tests: `212 passed`.
- ViewDefinition tests: `982 passed`.
- ViewDefinition conformance: `134/134`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL
  `1706/1706`, DQM `47/47`, overall `2822/2822`.

No new issues were discovered during remediation.
