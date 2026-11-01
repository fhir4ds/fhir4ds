# QA Handoff: SOF-VD-10 EXPLORER

Personality: EXPLORER
Scope: SQL-on-FHIR ViewDefinition terminology bindings, `sql-name`,
`sql-expressions`, cardinality, and strict/permissive boundaries.

Fresh probes:
- Created and ran `.ai_loop/.temp/qa/sof_vd10_explorer_probe.py`.
- Checked strict parser/generator rejection for invalid root/constant/column
  `sql-name`, required fields, present-null repeating root fields, row-generator
  mutual exclusion, ResourceType binding, and FHIRVersion binding.
- Included a composed parse -> SQLGenerator -> DuckDB execution case intended
  for native-loaded and forced Python fallback comparison.

Finding:
- `SOF-VD-10-EXPLORER-001` MEDIUM, OPEN.
- `validate_view_definition()` is documented as the permissive validation API,
  but it returned `[]` for direct dataclasses that violate SOF-VD-10 constraints:
  invalid ResourceType, invalid FHIRVersion, invalid root `ViewDefinition.name`,
  invalid `Column.name`, and invalid `Constant.name`.
- Strict parse/generator paths already reject these cases, so the defect is a
  public validator false-negative rather than SQL generation acceptance.

Spec basis:
- SQL-on-FHIR ViewDefinition logical model binds `ViewDefinition.resource` to
  ResourceType and `ViewDefinition.fhirVersion` to FHIRVersion as required
  bindings.
- The `sql-name` constraint applies to `ViewDefinition.name`,
  `ViewDefinition.constant.name`, and `ViewDefinition.select.column.name` with
  regex `^[A-Za-z][A-Za-z0-9_]*$`.
