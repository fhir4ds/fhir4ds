# QA Handoff - SOF-VD-04 HISTORIAN

## Scope

Verified current source against SQL-on-FHIR v2 ViewDefinition column
`collection`, `type`, and `tag` behavior. Did not inspect archived prior
workflow outputs.

## Spec Anchors

- `column.collection` is `0..1 boolean`, defaults false, and implementations
  shall report an error if multiple values are produced when it is not true.
- `column.type` is a FHIR StructureDefinition URI; relative URIs may use
  element ID notation such as `Observation.referenceRange`.
- Non-primitive returns require `column.type`; implementations should report
  errors when returned type mismatches the declaration or a non-primitive value
  is returned with type unset.
- `column.tag` is `0..*`; each tag requires string `name` and `value`.
  Database/type-hint tags are metadata unless explicitly handled.

## Probes

- Created `.temp/qa/sof_vd_04_historian_probe.py`.
- Checked parser defaults and validation for collection, type URI, and tag
  required fields.
- Checked SQL generation and execution on a shared `resources` table.
- Compared native C++ DuckDB registration and forced Python fallback for
  collection output and runtime errors.

## Findings

- `QA-001` MEDIUM: `Observation.referenceRange` element-ID type declarations
  are rejected by runtime type guards even though the spec allows this notation.
- `QA-002` HIGH: `$this` columns bypass runtime non-primitive/type mismatch
  checks, silently returning serialized JSON for untyped or primitive-declared
  complex values.

## Clean Checks

- Collection unset defaults false.
- Non-collection multi-value paths report runtime errors in native and fallback.
- Collection true primitive multi-values return DuckDB list output in native and
  fallback.
- Full primitive StructureDefinition URIs such as FHIR `date` work.
- `ansi/type` tags parse and preserve metadata without changing base output.
