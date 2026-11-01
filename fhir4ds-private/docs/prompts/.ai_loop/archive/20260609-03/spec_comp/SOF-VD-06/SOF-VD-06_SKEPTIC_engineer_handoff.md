# Engineer Handoff: SOF-VD-06/SKEPTIC

Resolved:
- `SOFVD06-SKEPTIC-001` HIGH.

Root cause:
- `fhir4ds/viewdef/parser.py` used `select_data.get("forEach")` and `select_data.get("forEachOrNull")`. That collapsed present JSON `null` into the same value as an absent optional field.

Fix:
- Added `_parse_optional_fhirpath_string()` in `parser.py` for official JSON input.
- The parser now distinguishes field absence from present `null`; absent remains valid, present `null` raises `ParseError`.
- Added null cases to `test_select_iteration_fields_must_be_non_empty_strings()`.

Spec basis:
- SQL-on-FHIR v2.0.0 defines both `ViewDefinition.select.forEach` and `ViewDefinition.select.forEachOrNull` as optional `0..1 string` fields. `forEach` produces one row per selected element; `forEachOrNull` preserves one row with null nested values when the selected collection is empty.

Validation:
- `python3 .temp/qa/sof_vd06_skeptic_probe.py`: PASS across native/default and forced Python fallback.
- Targeted pytest: `268 passed`.
- Full ViewDefinition pytest: `950 passed`.
- ViewDefinition conformance: `134/134`.
- Full conformance: `2822/2822`.

Changed files:
- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd06_skeptic_probe.py`
- `.ai_loop/evolution.json`
- `.ai_loop/qa_handoff.md`
- `.ai_loop/engineer_handoff.md`

