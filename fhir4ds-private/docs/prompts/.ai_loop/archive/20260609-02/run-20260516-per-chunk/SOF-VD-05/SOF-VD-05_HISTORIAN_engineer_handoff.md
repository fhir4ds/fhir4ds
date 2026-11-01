# Engineer Handoff - SOF-VD-05 HISTORIAN

## Triage
| Issue | Severity | Category | Status |
|---|---|---|---|
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fix
`QA-001` reproduced: a child `select` containing `unionAll` under a default
`$this` wrapper was ignored by SQL generation. Parent-only SQL was emitted, and
deeper wrappers produced `SELECT NULL WHERE FALSE`.

Root cause was in `SQLGenerator._hoist_nested_unions()`: nested `unionAll`
hoisting was limited to parent selects with `forEach`, `forEachOrNull`, or
`repeat`. SQL-on-FHIR models both `select.select` and `select.unionAll` as
recursive references to `ViewDefinition.select`, so the implicit default
`$this` parent context must inherit union branches too.

Changed `fhir4ds/viewdef/generator.py` to hoist a nested `unionAll` child from
any parent select while preserving explicit iterator context and implicit
default `$this` context.

## Tests Added
Added
`TestSimplePatientView.test_nested_unionall_default_context_matches_fallback`
in `fhir4ds/viewdef/tests/integration/test_duckdb.py`.

The test covers:
- parent columns combined with nested union branch columns;
- deeper recursive default-`$this` select wrappers;
- normal DuckDB registration and forced Python fallback registration. If a
  bundled native C++ extension is available, the normal path exercises it; in
  this environment normal registration used the Python fallback because the
  bundled extension did not load for the active DuckDB runtime.

## Validation
- `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_nested_unionall_default_context_matches_fallback -q`
  - `1 passed`
- `python3 -m pytest fhir4ds/viewdef -q`
  - `822 passed`
- `python3 conformance/scripts/run_viewdef.py`
  - `134/134 tests passed`
- `python3 conformance/scripts/run_all.py`
  - `OVERALL COMPLIANCE 2822/2822 100.0%`
- `python3 -m pytest fhir4ds/ --tb=short`
  - `7360 passed, 5 skipped, 9 warnings`
