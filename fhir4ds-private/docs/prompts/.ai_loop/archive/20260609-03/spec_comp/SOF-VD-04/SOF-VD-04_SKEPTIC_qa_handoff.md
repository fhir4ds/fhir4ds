# QA Handoff - SOF-VD-04 SKEPTIC

Scope: SQL-on-FHIR ViewDefinition column `collection`, `type`, and `tag`.

Spec anchor checked: SQL-on-FHIR v2.0.0 `ViewDefinition.select.column.collection`
defaults false and requires an error for multi-value scalar output;
`ViewDefinition.select.column.type` is a FHIR StructureDefinition URI and is
required for non-primitive output; `ViewDefinition.select.column.tag` is the
official 0..* backbone field with required string `name` and `value`.

Fresh probe: `.temp/qa/sof_vd04_skeptic_probe.py`.

Probe coverage:
- Parser/serializer handling for omitted, null, and malformed `collection`,
  `type`, and `tag`.
- Native-loaded and forced Python fallback DuckDB execution for scalar
  multi-value errors, collection output lists, primitive collection casts,
  complex typed output, missing complex `type`, primitive type mismatches, and
  database/type-hint tags not changing base semantics.
- Direct dataclass `ColumnTag` mutation before serializer/generator use.

Findings:
- `SOFVD04-SKEPTIC-001` HIGH: parser accepts plural column `tags` and
  canonicalizes it to official `tag`, even though the logical model defines
  only `ViewDefinition.select.column.tag`.
- `SOFVD04-SKEPTIC-002` HIGH: direct `ColumnTag` objects can be mutated after
  construction, and `ViewDefinition.to_dict()` / `SQLGenerator.generate()` do
  not revalidate required tag `name` / `value` before serialization/generation.

No failures were found for scalar multi-value runtime errors, collection=true
output lists, primitive collection element typing, full FHIR type URI handling,
missing non-primitive type errors, primitive mismatch errors, or tag metadata
accidentally changing execution semantics.
