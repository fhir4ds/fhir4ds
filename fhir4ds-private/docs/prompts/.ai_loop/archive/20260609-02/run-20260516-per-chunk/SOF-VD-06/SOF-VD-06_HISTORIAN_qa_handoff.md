# QA Handoff: SOF-VD-06 HISTORIAN

Personality: HISTORIAN
Chunk: SOF-VD-06 SQL-on-FHIR ViewDefinition `select.forEach` / `select.forEachOrNull`

## Spec Anchors

- SQL-on-FHIR ViewDefinition `sql-expressions` constraint: `select` can have at most one of `forEach`, `forEachOrNull`, or `repeat`.
- SQL-on-FHIR unnesting semantics: `forEach` is inner-join-like, `forEachOrNull` is left-outer-join-like and preserves one row with null values for an empty selected collection.
- FHIRPath environment variables: `%context` is supplied by the calling environment; SQL-on-FHIR ViewDefinition also uses `%resource`, `%rootResource`, and `%rowIndex` in iterated contexts.

## Probes

- Parser/public validator boundary for iterator mutual exclusion.
- SQL generation and DuckDB execution for parent columns, row multiplication, empty-collection suppression, and `forEachOrNull` null-row preservation.
- Native-loaded C++ DuckDB FHIRPath registration versus forced Python fallback for built-in variables in iterator scopes.
- Official ViewDefinition `foreach.json` and `row_index.json` behavior through conformance.

## Findings

- `QA-001` MEDIUM `RESOLVED`: `parse_view_definition()` and `validate_view_definition()` accepted `forEach`/`repeat` and `forEachOrNull`/`repeat` combinations, violating the `sql-expressions` constraint at the parser/validator boundary.
- `QA-002` HIGH `RESOLVED`: Complex leading `%resource.*` / `%rootResource.*` FHIRPath expressions inside iterators, such as `%resource.name.family.first()`, were evaluated against the current unnested alias instead of the root resource in both native-loaded and forced Python fallback DuckDB paths.

## Validation

- Focused parser tests: `5 passed`
- Focused native/fallback DuckDB tests: `2 passed`
- Full ViewDefinition pytest: `838 passed`
- ViewDefinition conformance: `134/134`
- Full conformance: `2822/2822`
- Full package pytest: `7376 passed, 5 skipped, 9 warnings`
