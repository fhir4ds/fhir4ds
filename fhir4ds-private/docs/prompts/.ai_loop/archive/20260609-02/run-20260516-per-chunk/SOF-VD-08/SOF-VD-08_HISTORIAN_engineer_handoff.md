# Engineer Handoff - SOF-VD-08 HISTORIAN

Issue remediated:
- `QA-001` MEDIUM `RESOLVED`: `fhir4ds.viewdef.union.generate_union_all()` generated union branches by rendering only direct columns against the root resource. Branch `forEach`, `forEachOrNull`, `repeat`, `where`, nested `select`, and nested `unionAll` were therefore skipped by the legacy direct helper even though the main `SQLGenerator` ViewDefinition path handled them.

Fix:
- Reworked the direct helper to expand each branch through `SQLGenerator._expand_select_unions()` and render each expanded branch through `SQLGenerator._process_selects()`.
- Preserved existing public function signatures.
- Tightened helper branch compatibility to compare effective output schema `(name, type, collection)` rather than direct column names only.

Files changed:
- `fhir4ds/viewdef/union.py`
- `fhir4ds/viewdef/tests/unit/test_union.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd_08_historian_fresh_probe.py`

Validation:
- `python3 .temp/qa/sof_vd_08_historian_fresh_probe.py` passed; the probe compares normal native/C++ registration against forced Python fallback for SOF-VD-08 boundaries.
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_union.py fhir4ds/viewdef/tests/integration/test_duckdb.py::TestUnionAll -q --tb=short`: `28 passed`
- `python3 -m pytest fhir4ds/viewdef/tests -q --tb=short`: `852 passed`
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`
- `python3 -m pytest fhir4ds/ -q --tb=short`: `7391 passed, 5 skipped, 9 warnings`
