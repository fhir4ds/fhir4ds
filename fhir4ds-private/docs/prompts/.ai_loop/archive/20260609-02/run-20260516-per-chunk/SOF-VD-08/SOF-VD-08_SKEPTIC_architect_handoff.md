# Architect Handoff — SOF-VD-08 SKEPTIC

Golden standard written: `.temp/architect/golden_standard.md`. The target architecture is that `unionAll` is a rowset-producing select expression: branch rowsets concatenate without deduplication, sibling select/union rowsets cross-join, effective schemas include direct/nested/union output, and execution remains on the public DuckDB FHIRPath UDF surface with native-loaded and forced Python fallback parity.

Audit result: no new blocking architectural findings. The remediation is general rather than fixture-specific: recursive union expansion converts union branches into select alternatives before SQL emission, and schema validation now uses effective output schemas instead of SQL alias-only assumptions. The remaining old `_build_union_all_query`/`_hoist_nested_unions` helpers are no longer on the active generation path; they are cleanup debt, not a behavioral blocker for this workflow.

QA enforcer result: no retry. QA was adequate for SKEPTIC scope: it tested sibling union groups, nested branch unions, branch/root `where` scope, duplicate preservation, and native-vs-forced-fallback execution.

Resolved issue count: 2 HIGH (`QA-001`, `QA-002`). Open issue count: 0.

Validation reviewed:
- Focused unionAll regressions passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q --tb=short`: `851 passed`.
- `python3 conformance/scripts/run_viewdef.py | grep ...`: ViewDefinition `134/134`.
- `python3 conformance/scripts/run_all.py | grep ...`: overall `2822/2822`, all suites 100%.
- `python3 -m pytest fhir4ds/ -q --tb=short`: `7390 passed, 5 skipped, 9 warnings`.
