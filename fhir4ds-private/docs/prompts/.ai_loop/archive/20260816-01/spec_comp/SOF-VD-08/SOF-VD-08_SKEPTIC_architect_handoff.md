# Architect Handoff — SOF-VD-08 / SKEPTIC (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-08 — `select.unionAll`.
**Iteration**: 1.
**Open issues**: 0.

## Audit Summary

- **Golden Standard**: unionAll concatenates branch rowsets preserving
  duplicates; branch schemas must match by name/order/type/collection;
  branch-local where stays branch-scoped; nested unionAll recurses;
  present-empty/null rejected; sibling unionAll groups compose via
  Cartesian.
- **Implementation review**: `fhir4ds/viewdef/generator.py` rowset
  expansion + `_hoist_nested_unions` + `_collect_select_output_schema`
  and `fhir4ds/viewdef/union.py` + `parser.py`/`types.py` validators.
  All 10 hypotheses empirically rejected.
- **SKEPTIC QA quality**: 10 falsifiable hypotheses covering all 6 chunk
  items. **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- No new entry required. unionAll semantics remain aligned.
