# QA Handoff - SOF-VD-04 HISTORIAN

Scope: SQL-on-FHIR ViewDefinition column `collection`, `type`, and `tag`.

Spec anchor checked: SQL-on-FHIR v2.0.0 states that `collection` defaults to
false and multiple values under `collection=false` must be reported as an
error. `column.type` is a FHIR StructureDefinition URI and implementations
should report an error when a non-primitive type is returned with `type` unset,
or when the returned type does not match the declared type. `column.tag` is the
singular repeating metadata field with required `name` and `value`.

Fresh probe: `.temp/qa/sof_vd04_historian_probe.py`.

Finding:
- `SOFVD04-HISTORIAN-001` HIGH: complex FHIRPath expressions bypass runtime
  type checking. `code.coding.where(system = 'http://loinc.org')` returned a
  serialized `Coding` object when `column.type` was unset, and also bypassed
  the primitive mismatch guard when declared as `type: string`.

No fresh failures were found for scalar multi-value runtime errors,
`collection=true` primitive list output, singular `tag` parsing, plural `tags`
rejection, or mutated `ColumnTag` serializer/generator revalidation.
