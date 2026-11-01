# QA Handoff - SOF-VD-03 SKEPTIC

## Scope

Chunk SOF-VD-03: SQL-on-FHIR ViewDefinition select and column basics.
Personality: SKEPTIC.

## Spec Anchor

SQL-on-FHIR v2.0.0 ViewDefinition logical model defines `ViewDefinition.select`
as `1..*`, `select.column` as `0..*`, `column.path` and `column.name` as
`1..1` strings, `column.name` with the `sql-name` invariant
`^[A-Za-z][A-Za-z0-9_]*$`, and `column.description` as `0..1 markdown`.

## Fresh Probe

Probe written and run:

```bash
python3 .temp/qa/sof_vd03_skeptic_probe.py
```

Parser and `ViewDefinition.from_dict()` rejected malformed select/column JSON:
missing/null/empty root `select`, non-array `select`, bad select items,
non-array `column`, bad column items, missing/empty/non-string column path/name,
invalid sql-name, and non-string markdown description.

Native-loaded and forced Python fallback execution both preserved root and
select-relative FHIRPath behavior for a two-select Patient view. The probe's
initial row-order expectation was intentionally not logged as a bug because SQL
result row order is not specified without `ORDER BY`.

## Finding

`SOF-VD03-SKEPTIC-001` (HIGH): direct dataclass SQL generation and official JSON
serialization can bypass select/column logical-model validation. Invalid direct
objects accepted today:

- `SQLGenerator().generate(ViewDefinition(resource="Patient", select=[]))`
- `ViewDefinition(resource="Patient", select=[]).to_dict()`
- `ViewDefinition.to_dict()` with direct `Column(path="", ...)`
- `ViewDefinition.to_dict()` with direct `Column(name="_bad", ...)`
- `ViewDefinition.to_dict()` with non-string `Column.description`
- `ViewDefinition.to_dict()` with non-Boolean `Column.collection`

## Requested Fix

Add shared direct-object validation so `SQLGenerator.generate()` rejects empty
root `select`, and `ViewDefinition.to_dict()` / nested `Select.to_dict()` /
`Column.to_dict()` reject invalid select containers and column primitive shapes
before emitting official JSON.
