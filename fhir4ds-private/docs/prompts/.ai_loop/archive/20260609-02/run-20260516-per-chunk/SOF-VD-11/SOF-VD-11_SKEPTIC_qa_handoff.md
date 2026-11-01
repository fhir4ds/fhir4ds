# QA Handoff - SOF-VD-11 SKEPTIC

## Scope

SQL-on-FHIR ViewDefinition View Runner and examples: executing ViewDefinitions
to tabular DuckDB rows, simple Patient and Observation views, Patient.address
unrolling, filtered Observation/resource views, column type coercion, official
spec parity, and native C++ versus forced Python fallback comparison.

## Spec Basis

Verified against SQL-on-FHIR v2.0.0:
- `ViewDefinition` is a tabular projection of FHIR resources using FHIRPath.
- A View Runner executes a ViewDefinition and returns a table.
- A ViewDefinition is tied to one FHIR resource type and creates zero or more
  rows per resource instance, including simple Patient views, Observation
  views, and unrolled Patient addresses.
- Column types may be explicit; primitive column values must be single values
  when `collection` is not true.

## SKEPTIC Hypotheses

1. Forced Python fallback might disagree with native C++ on FHIRPath type
   reflection used by ViewDefinition runtime guards.
2. Patient.address `forEach`/`forEachOrNull` might drop parent rows or misplace
   `%rowIndex`.
3. Root `where` filters might behave differently from nested iteration scopes.
4. Primitive column type coercion might not produce DuckDB typed result columns.
5. Observation examples using Quantity values might fail at the type guard
   boundary even though direct scalar extraction works.

## Fresh Probe

Created and ran:
`fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_11_skeptic_probe.py`

Before fix, the probe showed:
- Simple Patient rows passed and matched native/fallback.
- Patient.address `forEach` passed with two address rows and `%rowIndex`.
- Patient.address `forEachOrNull` preserved the parent row with null address
  columns for the patient with no address.
- Numeric/boolean literal coercion returned `BOOLEAN`, `INTEGER`, `DOUBLE`,
  and `VARCHAR` columns.
- Filtered Observation view failed only on forced Python fallback for
  `valueQuantity.value` declared as `decimal`.

## Finding

`QA-001` HIGH `SPEC_VIOLATION`: valid filtered Observation ViewDefinition with
`{"path": "valueQuantity.value", "name": "value", "type": "decimal"}` failed
under forced Python fallback with:

`InvalidInputException: ViewDefinition column 'value' path 'valueQuantity.value' violates collection=false / declared type decimal`

Native C++ returned the expected row. Direct comparison showed:
- Native `(valueQuantity.value).type().name` -> `decimal`
- Forced fallback `(valueQuantity.value).type().name` -> `string`

## Artifacts

- Before-fix probe output:
  `.temp/qa/sof_vd_11_skeptic_probe.json`
- After-fix probe output:
  `.temp/qa/sof_vd_11_skeptic_probe_after_fix.json`

