# QA Handoff — SOF-VD-06 SKEPTIC

Scope: SQL-on-FHIR ViewDefinition `select.forEach` and `select.forEachOrNull`.

Spec anchors consulted directly:
- SQL-on-FHIR v2.1.0-pre ViewDefinition declares nested `select` relative to a parent expression, `forEach` as the FHIRPath expression that retrieves parent elements for the containing select, and `forEachOrNull` as the same behavior with one null-valued row when the collection is empty.
- SQL-on-FHIR v2.1.0-pre `%rowIndex` returns the 0-based index inside `forEach`/`forEachOrNull`/`repeat`, is `0` at top level, and scopes independently per nesting level.
- FHIRPath v3.0.0-ballot special variables define `%context` as the expression starting point, `%resource` as the resource containing the focused element, and `%rootResource` as the top-level FHIR resource.

Hypotheses tested:
- `forEach` row multiplication may fail to repeat parent columns.
- `forEach` may leak one row for empty collections.
- `forEachOrNull` may behave like an inner join for empty collections.
- Nested columns may evaluate against the root resource instead of the iterated element.
- Built-in variables may lose root context once SQL generation switches `resource_var` to the unnested alias.

Findings:
- `QA-001` HIGH OPEN: `%resource` and `%rootResource` are wrong in iterated ViewDefinition contexts. A sandbox probe over Patient `pt-root` with `forEach: name` and columns `%context.family`, `%resource.id`, `%rootResource.id`, `%rowIndex` returned `('Fam1', NULL, NULL, 0)` and `('Fam2', NULL, NULL, 1)` in both normal native registration and forced Python fallback. Expected root ids are `pt-root` for both root-resource variables. Generated SQL calls `fhirpath_text(name_elem_0, '%resource.id')` and `fhirpath_text(name_elem_0, '%rootResource.id')`, so the FHIRPath evaluator sees the iterated name object as the whole resource.

Clean behaviors observed:
- `forEach` multiplied rows and repeated parent columns for `name`.
- `forEach` suppressed rows for empty `identifier`.
- `forEachOrNull` preserved one null row for empty `telecom`.
- `%rowIndex` returned `0, 1` for `forEach` and `0` for the empty `forEachOrNull` null row.

Recommended fix:
- Keep ordinary relative column paths evaluated against the current iterated alias.
- Rewrite or route FHIRPath expressions containing `%resource` or `%rootResource` so those variables resolve against the base root resource while `%context` remains the current expression context.
- Add regression coverage in the ViewDefinition DuckDB integration tests that compares normal/native registration and forced Python fallback.
