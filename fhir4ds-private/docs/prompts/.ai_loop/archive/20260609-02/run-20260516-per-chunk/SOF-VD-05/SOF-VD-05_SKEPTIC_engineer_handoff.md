# Engineer Handoff — SOF-VD-05 SKEPTIC

Phase: FIX
Issue triage:
- QA-001 HIGH was reproduced with the synthetic expectation from QA, but the first production fix attempt regressed official SQL-on-FHIR `foreach.json` unionAll cases.
- Deep research showed the current behavior is intended: a child `forEach` nested under an enclosing `forEachOrNull` keeps its own inner-flattening semantics. The outer `forEachOrNull` may create an empty parent row, but the later child `forEach` can still produce no child branch rows.

Changes made:
- Reverted the attempted production change in `generator.py`/`unnest.py`; production SQL generation is unchanged.
- Added an integration test documenting the intended nested `forEach` under `forEachOrNull` boundary.
- Added a NOT A BUG entry to `fhir4ds/viewdef/AGENTS.md`.
- Wrote `state/deep_research_findings.md` for the failed first attempt and final classification.

Issue status:
- QA-001: INTENDED.

Validation:
- `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py::TestForeachParentColumns::test_nested_foreach_under_foreachornull_keeps_inner_semantics -q --tb=short` -> 1 passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q --tb=short` -> 821 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Next phase:
- Architect should confirm the INTENDED classification and check whether the new boundary test/AGENTS note are sufficient without production changes.
