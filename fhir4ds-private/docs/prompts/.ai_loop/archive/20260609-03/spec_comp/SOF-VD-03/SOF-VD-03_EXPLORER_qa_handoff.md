# QA Handoff: SOF-VD-03 EXPLORER

## Scope

Fresh EXPLORER pass for SQL-on-FHIR ViewDefinition select/column basics:
root `select` cardinality, column path/name/description boundaries, SQL-safe
column output names, multiple select blocks, deterministic column order, and
root/select-relative execution contexts.

## Spec Anchors

- SQL-on-FHIR v2 `ViewDefinition.select` is `1..*`; `select.column` is `0..*`;
  `column.path` and `column.name` are required strings; `column.name` uses
  `sql-name`; `column.description` is `0..1 markdown`.
- FHIR JSON primitive values are represented as string/number/boolean values
  when present; absent optional primitives are omitted rather than represented
  as JSON null.

## Finding

- `SOFVD03-EXPLORER-001` HIGH, OPEN at QA handoff: `parse_view_definition()` accepted a
  present JSON null `ViewDefinition.select.column.description` and silently
  materialized it as absent metadata. Expected strict rejection because
  `column.description` is a markdown primitive. Root cause: `_parse_column()`
  used `col_data.get("description")`, conflating missing and present-null
  input before optional markdown validation.

## Fresh Evidence

- Minimal reproducer before remediation:
  `{"resource":"Patient","select":[{"column":[{"path":"id","name":"id","description":null}]}]}`
  parsed successfully with `Column.description is None`.
- A fresh probe was added at `.temp/qa/sof_vd03_explorer_probe.py` to cover the
  null-description rejection plus select/column parser boundaries, direct
  dataclass generation boundaries, SQL keyword-safe output names, column order,
  nested select contexts, and native/fallback execution parity.
