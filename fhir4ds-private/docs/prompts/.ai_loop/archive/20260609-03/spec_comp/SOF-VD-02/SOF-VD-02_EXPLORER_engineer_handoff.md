# Engineer Handoff: SOF-VD-02 EXPLORER

Iteration: 1
Issue: `SOF-VD-02-EXPLORER-001`
Status: RESOLVED

## Triage

| Issue | Category | Severity | Result |
| --- | --- | --- | --- |
| `SOF-VD-02-EXPLORER-001` | SPEC_VIOLATION | HIGH | Fixed and validated |

## Root Cause

`fhir4ds/viewdef/types.py` used one permissive dateTime regex for both `dateTime` and `instant`. The follow-up validation checked calendar validity, and for `instant` checked only that time and timezone were present. That let invalid partial-date time forms through, including `2024T00:00:00Z` and `2024-01T00:00:00Z`.

## Fix

Updated `_validate_primitive_value()`:
- `valueDateTime` with a time component now requires a complete `YYYY-MM-DD` date and timezone.
- `valueInstant` now requires a complete `YYYY-MM-DD` date, time component, and timezone.

Regression coverage added:
- Parser rejection in `test_parser.py`.
- Direct dataclass/generator preflight rejection in `test_generator.py`.
- `Constant.to_dict()` serializer-boundary rejection in `test_constants.py`.

Also refreshed the constants resolver module docstring so it no longer describes unsupported Coding/CodeableConcept constants as part of the current ViewDefinition constant choice list.

## Validation

- Fresh probe: `python3 .temp/qa/sof_vd02_explorer_probe.py` -> PASS
- Focused invalid-boundary tests: 23 passed
- Direct generator constant validation: 6 passed
- Parser/constants/generator unit set: 276 passed
- ViewDefinition DuckDB integration: 58 passed
- Full ViewDefinition pytest: 922 passed
- ViewDefinition conformance: 134/134
- Full conformance: 2822/2822

No additional issues were found.
