# QA Handoff: SOF-VD-04 EXPLORER

## Scope

Fresh EXPLORER pass for SQL-on-FHIR ViewDefinition column `collection`,
`type`, and `tag`. I did not use archived prior spec-compliance outputs as
behavior evidence.

## Spec Verification

Verified against SQL-on-FHIR v2.0.0:

- `ViewDefinition.select.column.collection` is `0..1 boolean`, defaults to
  `false`, and implementations SHALL report an error if multiple values are
  produced when it is not true.
- `ViewDefinition.select.column.type` is a FHIR StructureDefinition URI,
  relative FHIR URIs are allowed, element-ID notation such as
  `Observation.referenceRange` is allowed, and non-primitive values require
  type.
- `ViewDefinition.select.column.tag` is `0..* BackboneElement`; `tag.name`
  and `tag.value` are required strings. Tags are metadata such as
  database-specific hints, not base semantic overrides.

## Probes

- Parser validation for default `collection=false`, invalid collection shapes,
  full/relative type URI parsing, required tag name/value, tag array shape.
- SQL generation and DuckDB execution against shared `resources` tables.
- Native C++ FHIRPath extension and forced Python fallback comparison.
- Official ViewDefinition collection fixture execution through
  `conformance/scripts/run_viewdef.py`.

## Finding

`QA-001` MEDIUM: Primitive typed collection columns return `VARCHAR[]` rather
than a typed primitive list. Reproducer:

```json
{
  "resource": "Observation",
  "select": [{
    "column": [{
      "path": "component.value",
      "name": "values",
      "type": "http://hl7.org/fhir/StructureDefinition/integer",
      "collection": true
    }]
  }]
}
```

With `component.valueInteger` values `1` and `2`, both native and fallback
returned `['1', '2']` with DuckDB type `VARCHAR[]`. The column declaration
expects integer element values.

## Clean Checks

- Parser/tag/cardinality/type mismatch behavior otherwise matched scope.
- `collection=false` multivalue errors were reported in native and fallback.
- Non-primitive missing type errors were reported in native and fallback.
- Type-hint tags remained inert for base semantics.
- Existing focused tests before remediation: `202 passed`.
