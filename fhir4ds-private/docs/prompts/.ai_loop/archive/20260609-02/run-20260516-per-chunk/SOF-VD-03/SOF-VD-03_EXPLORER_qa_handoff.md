# QA Handoff: SOF-VD-03 EXPLORER

## Scope Probed

- Parser validation for `ViewDefinition.select`, `select.column`, required
  column path/name fields, markdown description shape, select iteration fields,
  and column collection shape.
- SQL generation and DuckDB execution for multiple root select blocks,
  deterministic output ordering, root-context columns combined with
  select-relative `forEachOrNull`, and primitive `$this` projection.
- Native bundled C++ FHIRPath path and forced Python fallback path using the
  same generated ViewDefinition SQL.
- Official SQL-on-FHIR logical model definitions and local official fixtures for
  `basic`, `foreach`, `collection`, `union`, and `validate`.

## Spec Basis

- `ViewDefinition.select` is `1..*` BackboneElement and has an invariant
  allowing at most one of `forEach`, `forEachOrNull`, or `repeat`.
- `select.column.path` is `1..1 string`; `select.column.name` is `1..1 string`
  with the SQL-name invariant; `select.column.description` is `0..1 markdown`.
- `select.column.collection` is `0..1 boolean`, defaulting to false.
- `select.forEach` and `select.forEachOrNull` are optional string FHIRPath
  expressions; `select.repeat` is a repeating string FHIRPath field.

## Findings

- `QA-001` MEDIUM: `repeat` shape validation is unsafe. A dict value such as
  `{"path": "name"}` is coerced by `list(repeat)` into `["path"]`, so an
  invalid ViewDefinition silently generates SQL over the wrong FHIRPath. Parser
  also accepts non-string `forEach` / `forEachOrNull` and defers failure until
  generator syntax validation.
- `QA-002` MEDIUM: `column.collection` accepts non-boolean values. The string
  `"false"` is truthy and switches generated SQL from scalar wrappers to
  `fhirpath(...)` collection output. Direct dataclass input with an empty
  `Column.path` also bypasses the parser and reaches SQL generation.

## Passing Probes

- Multiple root `select` blocks preserved deterministic column order
  `["id", "active"]` and produced matching native/fallback rows.
- Root columns plus select-relative `forEachOrNull` produced expected rows,
  including a null-preserved parent row, in native and forced Python fallback.
- Primitive `forEach` plus `$this` projected matching native/fallback rows.
