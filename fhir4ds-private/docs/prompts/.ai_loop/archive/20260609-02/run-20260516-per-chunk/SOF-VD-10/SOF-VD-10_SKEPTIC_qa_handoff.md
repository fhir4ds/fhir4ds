# QA Handoff - SOF-VD-10 SKEPTIC

## Scope Probed

- SQL-on-FHIR ViewDefinition terminology bindings, sql-name/sql-expressions constraints, cardinality, and required fields.
- Parser boundary: `parse_view_definition()`.
- Public constructor boundary: `ViewDefinition.from_dict()`.
- Direct dataclass/generator boundary: `SQLGenerator.generate(ViewDefinition(...))`.
- Official expectError behavior and DuckDB execution were reserved for focused validation after remediation.

## Spec Basis

- SQL-on-FHIR v2.0.0 `ViewDefinition.name` and `ViewDefinition.constant.name` carry the `sql-name` invariant `^[A-Za-z][A-Za-z0-9_]*$`.
- `ViewDefinition.resource` is 1..1 and has required binding to FHIR `ResourceType`.
- `ViewDefinition.fhirVersion` has required binding to `FHIRVersion`.
- `ViewDefinition.select` is 1..*, `column.path`, `column.name`, `constant.name`, `constant.value[x]`, and `where.path` are required where their parent element is present.
- SQL-on-FHIR v2.1.0-pre `sql-expressions` says a select can have at most one of `forEach`, `forEachOrNull`, or `repeat`.

## Result

Opened `QA-001` (`MEDIUM`): parser/from_dict accept invalid `ViewDefinition.name` values (`_bad`, `bad-name`, `bad.name`, `1bad`), and direct dataclass generation bypasses `ViewDefinition.name`, `fhirVersion`, and `Constant.name`/`value[x]` validation.

Clean behaviors observed: parser rejects missing `resource`, missing/empty `select`, missing `column.path`, missing `column.name`, missing `constant.name`, missing `constant.value[x]`, missing `where.path`, unknown `resource`, unknown `fhirVersion`, and combined `forEach`/`forEachOrNull`/`repeat`.
