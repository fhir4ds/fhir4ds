QA HANDOFF - SOF-VD-03 HISTORIAN

Role focus:
- Walked SQL-on-FHIR v2.0.0 ViewDefinition.select and column requirements:
  required non-empty select, repeating select containers, column path/name/
  description, deterministic column ordering, and root/select-relative contexts.

Spec anchors checked:
- SQL-on-FHIR v2.0.0 ViewDefinition.select is 1..* BackboneElement.
- ViewDefinition.select.column is 0..* BackboneElement.
- column.path and column.name are 1..1 strings; column.description is 0..1
  markdown.
- column.name must satisfy sql-name and output column names must not duplicate.
- Functional model says select cross-joins sibling row sets, and forEach/nested
  selects evaluate relative to the active parent context.

Probes run:
- Parser/public-constructor shape probes for missing/empty select, invalid
  column primitive fields, markdown retention, and null repeating containers.
- SQL generation probe for duplicate names across sibling columns and unionAll
  branch columns.
- DuckDB execution probe for root and select-relative FHIRPath contexts across
  native C++ extension and forced Python fallback.

Findings:
- QA-SOF-VD-03-HISTORIAN-001 (MEDIUM): `column: null`, nested `select: null`,
  and `unionAll: null` are accepted as absent arrays by parser and
  `ViewDefinition.from_dict()`. Present repeating containers must be arrays.
- QA-SOF-VD-03-HISTORIAN-002 (MEDIUM): duplicate output names are not rejected
  when a sibling column and unionAll branch column collide in the same output
  schema.

Clean checks:
- Root plus select-relative context execution matched between native and forced
  Python fallback:
  `('p1', True, 'Alpha', 'Ann')`, `('p1', True, 'Beta', 'Bob')`.
- `column.description` markdown text was retained by parser and public
  constructor in the positive probe.

Recommended remediation:
- Change parser and `ViewDefinition.from_dict()` array helpers so present
  `null` is rejected for repeating select containers while absent fields still
  default to empty lists.
- Replace the global duplicate-name walker with an effective-output-schema
  validator that includes sibling/parent columns plus one representative
  unionAll branch, while preserving the existing branch-order/name equality
  check.
