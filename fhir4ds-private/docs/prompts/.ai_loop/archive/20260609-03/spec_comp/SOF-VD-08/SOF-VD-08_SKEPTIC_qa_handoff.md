# QA Handoff: SOF-VD-08 / SKEPTIC

## Scope

Fresh SKEPTIC pass for SQL-on-FHIR ViewDefinition `select.unionAll`.

Spec basis used:
- SQL-on-FHIR ViewDefinition v2.0.0: `unionAll` combines nested selection
  rowsets, preserves duplicate rows like SQL `UNION ALL`, and every branch must
  produce matching columns by count, name, order, and FHIR type.
- SQL-on-FHIR definitions: `ViewDefinition.select.unionAll` is a `0..*`
  recursive `select` content reference.
- FHIR JSON representation: empty properties should be omitted; present
  repeating properties must not be silently normalized to a different semantic
  shape.

## Fresh Probes

Created `.temp/qa/sof_vd08_skeptic_probe.py` and tested:
- malformed/null/non-array `unionAll` values
- present empty `unionAll: []`
- branch name/type/collection/missing-column compatibility
- duplicate row preservation
- nested `unionAll` recursion
- `unionAll` with `forEach`, `forEachOrNull`, `repeat`, nested select, and
  select-local `where`
- native-loaded DuckDB FHIRPath and forced Python fallback parity

## Finding

`SOFVD08-SKEPTIC-001` HIGH: `parse_view_definition()` accepted present
`select.unionAll: []` and produced the same dataclass state as an omitted
`unionAll`. This hid invalid official JSON and could let a malformed
rowset-producing branch directive disappear before SQL generation.

Status after remediation: VERIFIED.
