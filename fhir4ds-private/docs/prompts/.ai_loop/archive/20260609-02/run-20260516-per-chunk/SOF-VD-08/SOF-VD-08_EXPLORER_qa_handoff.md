# QA Handoff: SOF-VD-08 EXPLORER

## Scope
- SQL-on-FHIR ViewDefinition `select.unionAll`.
- Fresh probes only; no archived workflow outputs used as evidence.
- Compared normal DuckDB registration with forced Python fallback for executable ViewDefinition cases.

## Spec Anchor
- Official SQL-on-FHIR ViewDefinition `select.unionAll` states that `unionAll` creates a union of rows from nested selection structures, that branches must produce matching column count/name/order/types, and that UNION ALL semantics preserve duplicate rows.

## Exploration Performed
- Duplicate row preservation with two identical branches.
- Nested `unionAll` recursion under branches with `forEach`.
- Branch-local and parent `where` filter scope.
- `repeat` combined with `unionAll`.
- Missing-column, FHIR type mismatch, and collection-cardinality mismatch rejection.
- Legacy/importable `UnionGenerator.validate_union_columns()` schema validation behavior.

## Findings
- `QA-001` MEDIUM OPEN: `UnionGenerator.validate_union_columns()` only compares branch column names. It returns no warning for branches with matching names but different declared FHIR types or collection cardinality, despite the official `unionAll` branch schema compatibility requirement and the stricter behavior of the main generator.

## Evidence
- Probe command: `python3 .temp/qa/sof_vd_08_explorer_probe.py`
- Passing portions: duplicate preservation, nested iterators, where scope, repeat interaction, and main generator schema rejections all passed on normal C++ registration and forced Python fallback.
- Failure: `AssertionError: UnionGenerator.validate_union_columns missed type/schema mismatch`

## Handoff
- Move to FIX. Update the legacy validator to compare the same effective schema used by `generate_union_all()`, then add focused regression coverage.
