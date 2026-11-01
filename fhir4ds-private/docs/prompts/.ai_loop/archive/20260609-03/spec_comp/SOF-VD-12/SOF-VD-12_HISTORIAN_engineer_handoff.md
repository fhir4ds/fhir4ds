# Engineer Handoff — SOF-VD-12/HISTORIAN

## Issue Resolved
`SOF-VD-12-HISTORIAN-001` — supported Shareable/Tabular profile validation missed required `ViewDefinition.status`.

## Root Cause
`validate_supported_view_profiles()` was the shared enforcement point for supported profile constraints, but it only checked:
- Shareable: `url`, `name`, `fhirVersion`, and `Column.type`
- Tabular: scalar primitive column constraints

It did not enforce the inherited CanonicalResource `status` cardinality for supported ShareableViewDefinition and TabularViewDefinition profile declarations.

## Fix
Updated `fhir4ds/viewdef/types.py` so supported Shareable/Tabular profiles require `ViewDefinition.status`.

This shared validator is already used by strict parser, direct `to_dict()`, direct SQL generator preflight, and permissive `validate_view_definition()`, so the fix covers all intended boundaries without duplicating checks.

## Tests Added/Updated
- `fhir4ds/viewdef/tests/unit/test_parser.py`
  - Parse rejection for Shareable/Tabular missing `status`
  - `to_dict()` rejection for direct dataclasses missing `status`
  - `validate_view_definition()` warning coverage
  - Existing profile tests updated with `status: active` when testing other constraints
- `fhir4ds/viewdef/tests/unit/test_generator.py`
  - Direct generator preflight coverage for missing profile `status`
  - Existing fixtures updated to reach the intended Column.type/primitive branches
- `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd12_historian_probe.py`
  - Fresh QA/reproducer probe covering profile status, JSON round-trip, XML unsupported behavior, and native/fallback execution parity

## Validation
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd12_historian_probe.py` — PASS
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q` — 214 passed
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_generator.py::TestFullQueryGeneration::test_direct_view_definition_supported_profiles_are_validated -q` — 1 passed
- `python3 -m pytest fhir4ds/viewdef/tests -q` — 984 passed
- `python3 conformance/scripts/run_viewdef.py` — 134/134
- `python3 conformance/scripts/run_all.py` — 2822/2822

## Changed Files
- `fhir4ds/viewdef/types.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/tests/unit/test_generator.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.ai_loop/evolution.json`
- `.ai_loop/qa_handoff.md`
- `.ai_loop/engineer_handoff.md`
- `.ai_loop/.temp/qa/sof_vd12_historian_probe.py`
