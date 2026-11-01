# Engineer Handoff: SOF-VD-01

## Triage

| Issue | Category | Status |
| --- | --- | --- |
| SOF-VD-01-QA-001 | SPEC_VIOLATION | RESOLVED |
| SOF-VD-01-QA-002 | SPEC_VIOLATION | RESOLVED |

## Fixes

- Added `fhir4ds/viewdef/metadata.py` as the shared binding source for root ViewDefinition resource and FHIR version validation.
- Changed `ViewDefinition.resource` to single-string semantics at parser and generator boundaries. Arrays and unknown FHIR resource codes now raise typed errors instead of generating multi-resource SQL.
- Preserved `ViewDefinition.profile` and `ViewDefinition.fhirVersion` on the dataclass and parser output. `profile` must be an array of non-empty strings; `fhirVersion` must be an array of known FHIRVersion codes.
- Added focused parser/generator regression tests and updated the root table pluralization test to use a real FHIR resource type ending in `y`.

## Validation

- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py -q --tb=short`: 71 passed.
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_01_skeptic_probe.py`: invalid resource array and unknown resource now reject; profile/fhirVersion are preserved; shared resources table filter still returns only Patient rows in both available registration paths.
- `python3 -m pytest fhir4ds/viewdef -q --tb=short`: 703 passed.
- `python3 conformance/scripts/run_all.py | grep -E ...`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `python3 -m pytest fhir4ds/ -x --tb=short`: 7240 passed, 5 skipped, 9 warnings.

## Notes

The native FHIRPath extension was not loaded in this environment; both the normal and forced fallback registration attempts returned the Python fallback path. The ViewDefinition behavior under test is SQL generation and DuckDB execution over the registered surface, and the forced fallback path matched the normal path for the checked resource filter.
