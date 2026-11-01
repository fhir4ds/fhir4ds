# Engineer Handoff - SOF-VD-02 EXPLORER

## Issues Resolved

### QA-001 HIGH

Fixed ViewDefinition constant resolution so it respects FHIRPath lexical
boundaries. `%name` references are now discovered and substituted only outside
FHIRPath string literals, delimited identifiers, and comments. Primitive string
constants now serialize as FHIRPath string literals using FHIRPath backslash
escapes, then the generated expression is SQL-escaped by the generator.

Touched:
- `fhir4ds/viewdef/constants.py`
- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/unit/test_constants.py`
- `fhir4ds/viewdef/tests/unit/test_generator.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`

### QA-002 MEDIUM

Fixed `valueInteger64` validation to require the FHIR JSON representation
(JSON string), while preserving numeric FHIRPath substitution for validated
integer64 constants.

Touched:
- `fhir4ds/viewdef/types.py`
- `fhir4ds/viewdef/tests/unit/test_constants.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`

## Verification

- `PYTHONPATH=/mnt/d/fhir4ds python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_02_explorer_constants_probe.py`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_constants.py fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py -q` -> 147 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_constant_literal_boundaries_match_native_and_fallback -q` -> 1 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests -q` -> 743 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_viewdef.py | grep -E "FAIL|ERROR|ViewDefinition|Passed|Total|OVERALL|Suite|passed|failed|SUCCESS"` -> ViewDefinition 134/134
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM|Summary|passed"` -> overall 2822/2822
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/ -x --tb=short | tail -n 50` -> 7280 passed, 5 skipped

## Notes For Architect

No new issues were discovered during remediation. The main audit point is
whether `iter_constant_references()` is the right shared boundary for both
substitution and validation, and whether any future support for FHIRPath
`%'quoted external'` constants should remain intentionally out of scope for
SQL-on-FHIR `constant.name` because `constant.name` is constrained to sql-name.
