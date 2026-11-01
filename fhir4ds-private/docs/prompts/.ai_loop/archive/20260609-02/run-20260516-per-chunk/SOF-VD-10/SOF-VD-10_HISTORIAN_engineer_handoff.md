# Engineer Handoff - SOF-VD-10 HISTORIAN

## Triage

| Issue | Category | Severity | Status |
|---|---|---:|---|
| QA-001 | API_CONTRACT | MEDIUM | RESOLVED |

## Fix

`validate_view_definition()` is the permissive warning API, while
`parse_view_definition()` and `SQLGenerator.generate()` are strict execution
boundaries. The bug was that `_validate_selects()` raised `ValidationError` for
the SQL-on-FHIR `sql-expressions` constraint before returning warnings.

Changed `_validate_selects()` to append the mutual-exclusion warning and
continue. Strict parser and generator paths still reject combined `forEach`,
`forEachOrNull`, and `repeat`.

## Files Changed

- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd10_historian_probe.py`
- `.ai_loop` state and handoff files

## Verification

- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/sof_vd10_historian_probe.py`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py -q`
  - 194 passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_viewdef.py | grep -E "FAILED|PASSED|Summary|passed|ERROR|FAIL"`
  - Summary: 134/134 tests passed (100.0%)
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef -q`
  - 884 passed
