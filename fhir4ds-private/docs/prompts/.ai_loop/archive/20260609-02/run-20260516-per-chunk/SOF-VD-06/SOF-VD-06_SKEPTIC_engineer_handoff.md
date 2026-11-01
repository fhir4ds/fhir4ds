# Engineer Handoff — SOF-VD-06 SKEPTIC

Issue status:
- `QA-001` RESOLVED: built-in FHIRPath resource variables were losing root context inside ViewDefinition iterator scopes.

Root cause:
- `SQLGenerator._process_selects()` correctly switched ordinary relative column evaluation to the current `forEach`/`forEachOrNull` alias, but `generate_column_expr()` treated every FHIRPath path the same way. As a result, `%resource.id` and `%rootResource.id` were evaluated with the unnested element as the whole FHIRPath input instead of with the root Patient resource.

Fix:
- Added `SQLGenerator._resolve_environment_path_context()` to route simple built-in-variable paths before SQL emission.
- `%context` remains on the current iterator focus and `%context` itself normalizes to `$this`, which also fixes primitive iterated values.
- `%resource` and `%rootResource` route to the base/root resource alias, with the variable prefix stripped for the existing `fhirpath_*` UDF surface.
- Applied the same routing to simple `forEach`/`forEachOrNull` and `where` paths while leaving mixed-context expressions untouched rather than rewriting them incorrectly.

Changed files:
- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.ai_loop/evolution.json`
- `.ai_loop/qa_handoff.md`

Validation:
- Reproducer failed before the fix and passed after the fix.
- `python3 -m py_compile fhir4ds/viewdef/generator.py fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_foreach_builtin_variables_match_native_and_fallback -q --tb=short` — 1 passed
- `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_foreach_builtin_variables_match_native_and_fallback fhir4ds/viewdef/tests/integration/test_duckdb.py::TestForEach fhir4ds/viewdef/tests/integration/test_duckdb.py::TestForEachOrNull fhir4ds/viewdef/tests/unit/test_foreach.py -q --tb=short` — 27 passed
- `python3 conformance/scripts/run_viewdef.py | grep -E "FAIL|ERROR|ViewDefinition|Passed|passed|Total|134|100"` — 134/134
- `python3 -m pytest fhir4ds/viewdef -q --tb=short | tail -n 60` — 831 passed
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` — overall 2822/2822
- `python3 -m pytest fhir4ds/ -q --tb=short | tail -n 70` — 7369 passed, 5 skipped, 9 warnings
