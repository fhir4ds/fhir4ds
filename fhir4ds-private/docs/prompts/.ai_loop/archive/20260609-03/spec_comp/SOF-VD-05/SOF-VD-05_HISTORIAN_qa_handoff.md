# QA Handoff: SOF-VD-05/HISTORIAN

## Scope

- Chunk: SOF-VD-05, SQL-on-FHIR ViewDefinition nested `select.select`.
- Personality: HISTORIAN.
- Iteration: 1.
- Result: No product defects found.

## Spec Anchors

- SQL-on-FHIR v2.0.0 `ViewDefinition.select` is the row/column selection structure and can express columns or nested selects for nested resources.
- `ViewDefinition.select.select` is a recursive content reference relative to the parent expression; if the parent select has `forEach` or `forEachOrNull`, the child applies for each selected parent item.
- `forEach` defaults effectively to `$this`; `forEachOrNull` preserves one row with null child values when the collection is empty.
- Multiple select expressions compose by parent/child repetition and sibling cross-join semantics; `unionAll` branches must have matching output schemas.
- Sources: https://sql-on-fhir.org/ig/2.0.0/StructureDefinition-ViewDefinition-definitions.html and https://sql-on-fhir.org/ig/2.0.0/StructureDefinition-ViewDefinition.html.

## Fresh Probe Coverage

Probe: `.temp/qa/sof_vd05_historian_probe.py`.

- Official `combinations.json` slice: `select`, `column + select`, sibling select, nested sibling select, and root where combination.
- Parent/child default `$this` context when no iterator is present.
- Child select inheritance of parent `forEach`.
- Child select inheritance of parent `forEachOrNull`; verified null-preserved rows produce SQL NULL child columns, including collection-valued child columns.
- Sibling nested selects cross-join while sharing the parent context.
- Nested `unionAll` under a default `$this` wrapper.
- Empty nested select behavior: no-op under a column-bearing parent and defined empty result when the full select tree has no columns.
- Duplicate output-name rejection across parent/child and sibling nested selects.
- Direct dataclass `ViewDefinition`/`Select`/`Column` serializer and generator path for nested select recursion.
- Normal/native DuckDB registration and forced Python fallback registration.

## Validation

- Fresh probe: PASS.
- Focused pytest: `fhir4ds/viewdef/tests/integration/test_duckdb.py`, `test_generator.py`, `test_union.py`, `test_foreach.py`: 172 passed.
- Official ViewDefinition pytest harness: `fhir4ds/viewdef/tests/test_spec_compliance.py`: 435 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Issues

None.

## Notes

- A first draft of the probe expected an empty array for a collection column in a `forEachOrNull` null row. The official behavior is null-valued child columns for that preserved row, so the probe was corrected before final validation.
- Review-45 risks were kept in context. No root metadata or `where` serializer defect was encountered in this nested-select pass.
