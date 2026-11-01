# Engineer Handoff - SOF-VD-07 SKEPTIC

## Triage
| Issue | Severity | Category | Result |
|---|---:|---|---|
| SOFVD07-SKEPTIC-001 | HIGH | SPEC_VIOLATION / DATA_HANDLING | RESOLVED |

## Fix
`validate_repeat_paths()` now rejects a present empty `Select.repeat` array. The shared helper already sits on all relevant boundaries, so the fix covers strict parser input, `ViewDefinition.from_dict()`, `Select.to_dict()`, and direct `SQLGenerator.generate()` preflight without adding branch-specific checks.

## Root Cause
The validator accepted `[]`; later SQL generation checked `if select.repeat`, so an empty present repeat was falsey and skipped `fhirpath_repeat`. That made invalid official JSON behave like repeat absence/default `$this` and could evaluate columns against the root resource.

## Changed Files
- `fhir4ds/viewdef/types.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/tests/unit/test_generator.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd07_skeptic_probe.py`

## Validation
- Fresh probe: `python3 .temp/qa/sof_vd07_skeptic_probe.py` -> PASS
- Focused pytest: parser/generator/`TestRepeat` -> 259 passed
- Full ViewDefinition pytest: 952 passed
- ViewDefinition conformance: 134/134
- Full conformance: 2822/2822

## Notes for Architect
The fix is intentionally narrow: it does not attempt to validate FHIRPath syntax for every repeat expression, because that would be a wider ViewDefinition/FHIRPath validation policy change and existing parity tests cover runtime repeat expression behavior. Please audit that the central repeat validator remains the only policy change and that no schedule/archive files were touched.
