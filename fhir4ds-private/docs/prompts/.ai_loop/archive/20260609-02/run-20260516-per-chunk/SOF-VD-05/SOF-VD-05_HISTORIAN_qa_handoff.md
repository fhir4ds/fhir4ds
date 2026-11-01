# QA Handoff - SOF-VD-05 HISTORIAN

## Scope
SQL-on-FHIR ViewDefinition nested select/contentReference. Tested parser validation, SQL generation, DuckDB execution, and official spec fixture coverage around nested selects, parent iterator context, default `$this` context, row composition, duplicate/collision validation, and empty nested select behavior.

## Spec anchors verified
- `ViewDefinition.select.select` is a recursive `contentReference` back to `ViewDefinition.select` and is relative to the parent expression.
- If the parent select has `forEach` or `forEachOrNull`, the child select applies to each item in that parent expression.
- `forEach` defaults effectively to `$this` when absent.
- `unionAll` is also a recursive `contentReference` to `ViewDefinition.select`; each branch produces its own row and branch schemas must match.
- Output column names must not contain duplicates.

## Probes run
- Deep default-`$this` nested selects without row generators.
- Nested selects under parent `forEach`/`forEachOrNull` contexts.
- Parent column plus child columns row combination.
- Duplicate/collision validation through parser/generator surfaces.
- Official spec fixture review: `combinations.json`, `foreach.json`, and `union.json`.
- Manual DuckDB execution via normal `register_fhirpath()`; the active environment registered Python fallback rather than a distinct native C++ extension because the bundled extension only loads for DuckDB 1.5.x-compatible runtime.

## Findings
- `QA-001` HIGH OPEN: Nested `unionAll` inside a default-`$this` child `select` is ignored by SQL generation. Parent-only output is returned or `SELECT NULL WHERE FALSE` is emitted for deeper nested wrappers, silently dropping recursive contentReference branch rows.

## Requested remediation
Extend nested union hoisting/processing so a child `select` containing `unionAll` is handled at any recursive depth, not only beneath `forEach`/`forEachOrNull`/`repeat`. Add regression tests for default-`$this` nested union with parent columns and deeper recursive wrappers, then run focused ViewDefinition tests plus conformance.
