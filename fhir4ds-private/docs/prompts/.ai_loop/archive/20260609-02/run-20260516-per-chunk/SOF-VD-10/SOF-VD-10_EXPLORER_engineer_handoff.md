# Engineer Handoff - SOF-VD-10 EXPLORER

## Issue Resolved
- `QA-EXPLORER-001` (`MEDIUM`, `SPEC_VIOLATION`): strict ViewDefinition parsing accepted present JSON null for `constant` and `fhirVersion` as if the fields were absent.

## Root Cause
- `parser._parse_string_array()` used `data.get(field_name, [])` and returned `[]` for `None`, so `profile: null` and `fhirVersion: null` were silently accepted.
- `parse_view_definition()` used `data.get('constant', data.get('constants', []))` and only rejected truthy non-list values, so `constant: null` was silently accepted.

## Fix
- `fhir4ds/viewdef/parser.py`
  - Distinguish absent optional 0..* string fields from present JSON null.
  - Reject present null for `profile`/`fhirVersion` with `ParseError`.
  - Reject present null for `constant` with `ParseError`.
- `fhir4ds/viewdef/tests/unit/test_parser.py`
  - Added regression tests for `constant: null`, `profile: null`, and `fhirVersion: null`.
- `fhir4ds/viewdef/AGENTS.md`
  - Added durable SOF-VD-10 EXPLORER note on strict JSON null handling.

## Validation
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --tb=short`: `145 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests -q --tb=short`: `886 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_viewdef.py`: `134/134`
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py`: `2822/2822`

## Notes
- Native C++ FHIRPath registration returned `False` in this environment during QA execution probes, so the executable ViewDefinition comparison covered normal registration fallback versus forced Python fallback.
