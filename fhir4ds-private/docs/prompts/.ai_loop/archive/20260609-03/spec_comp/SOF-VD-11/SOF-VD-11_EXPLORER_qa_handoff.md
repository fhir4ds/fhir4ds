# QA Handoff: SOF-VD-11 / EXPLORER

## Scope
- Chunk: SOF-VD-11, SQL-on-FHIR ViewDefinition View Runner / Examples.
- Personality: EXPLORER.
- Focus: composed runner behavior around nested/unrolled arrays, `%rowIndex`, type coercion, root and nested filters, official examples, and native C++ versus forced Python fallback parity.

## Spec Anchor
- The official SQL-on-FHIR v2 ViewDefinition page describes a ViewDefinition as a tabular projection of FHIR resources, and a View Runner as executing a ViewDefinition and returning a table.
- `ViewDefinition.select.forEach` produces a row for each selected element.
- `ViewDefinition.select.column.type` says implementations should report an error if the returned type does not match the declared type; `collection=false` columns must not silently accept multi-valued outputs.

Official sources consulted:
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition-definitions.html

## Fresh Probe
- Added `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd11_explorer_probe.py`.
- The probe runs the same ViewDefinitions under a native-loaded DuckDB connection and a forced Python fallback connection.

## Finding
1. `SOF-VD-11-EXPLORER-001` HIGH, OPEN
   - Valid iterator projection fails: `forEach: "component.value"` with column `path: "$this", type: "integer"` raises a DuckDB binder error because the `$this` fast path builds `COALESCE(fhirpath_number(...), CAST(json AS VARCHAR))`.
   - Invalid iterator type declarations silently coerce: `$this` or relative `value` numeric/Boolean outputs declared as `type: "string"` return string values instead of a type mismatch.
   - `%rowIndex` declared as `type: "string"` or `type: "boolean"` returns integer ordinals instead of reporting that `%rowIndex` is integer-valued.

## Reproducer
Command:

```bash
python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd11_explorer_probe.py
```

Current failing output begins with:

```text
_duckdb.BinderException: Binder Error: Cannot mix values of type DOUBLE and VARCHAR in COALESCE operator
```

## Recommended Fix
- In `fhir4ds/viewdef/generator.py`, keep iterator fast paths but add physical JSON type guards for contexts where FHIRPath `type().name` metadata is intentionally disabled.
- Fix the `$this` expression builder so numeric and Boolean typed columns do not mix typed UDF output with a VARCHAR fallback.
- Validate `%rowIndex` declarations statically: allow integer-compatible numeric declarations, reject string/Boolean/complex declarations, and keep `type: "integer"` as DuckDB `INTEGER`.
