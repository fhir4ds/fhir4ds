# QA Handoff: SOF-VD-04 EXPLORER

Personality: EXPLORER
Chunk: SOF-VD-04, `ViewDefinition.select.column.collection`, `column.type`, and `column.tag`

Fresh probes combined parser/serializer/direct dataclass metadata boundaries with real DuckDB execution through native-loaded FHIRPath and forced Python fallback. I verified singular `tag` preservation/rejection of plural `tags`, direct mutated `ColumnTag` rejection, `collection=true` primitive list output, scalar multi-value runtime errors, non-primitive output requiring `column.type`, and tag type-hint metadata not changing base semantics.

Finding:
- `SOFVD04-EXPLORER-001` HIGH: non-simple primitive FHIRPath expressions with incompatible declared `column.type` values silently returned NULL instead of reporting a type mismatch. Reproducer: Patient column path `'abc'`, name `bad_int`, type `integer`; generated SQL returned `[(None,)]` because the non-simple guard only errored for complex JSON values. Spec anchor: SQL-on-FHIR `ViewDefinition.select.column.type` says implementations should report an error when returned type does not match the declared type.

Fresh probe path:
- `.temp/qa/sof_vd04_explorer_probe.py`
