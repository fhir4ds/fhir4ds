SOF-VD-10/SKEPTIC QA handoff

Scope tested:
- SQL-on-FHIR ViewDefinition sql-name invariant on root `name`, `constant.name`, and `select.column.name`.
- `sql-expressions` mutual exclusion for `forEach`, `forEachOrNull`, and `repeat`.
- Required fields: root `resource`, root `select`, `column.path`, `column.name`, `constant.name`, exactly one `constant.value[x]`, and `where.path`.
- Required bindings for `resource` against FHIR ResourceType and `fhirVersion` against FHIRVersion.
- Official spec `expectError` cases in the local ViewDefinition fixtures.
- Strict parser / `from_dict` / direct serializer / SQLGenerator preflight versus permissive `validate_view_definition()`.

Fresh evidence:
- Scratch probe: `.temp/qa/sof_vd_10_skeptic_probe.py`.
- Specification checked: SQL-on-FHIR ViewDefinition 2.1.0-pre logical model, especially the `sql-name` invariant, `sql-expressions` invariant, 1..1/1..* cardinalities, and required bindings; FHIR JSON representation rules for present elements.

Finding:
- `SOF-VD-10-SKEPTIC-001` HIGH: strict parser and `ViewDefinition.from_dict()` accept present JSON null for optional root metadata (`resourceType`, `id`, `meta`, `url`, `version`, `status`, `title`, `description`). This verifies open review finding `REV-045-001`.

Important non-findings:
- Invalid sql-name values, missing required chunk fields, invalid ResourceType/FHIRVersion bindings, multi-row-generator selects, and local official `expectError` fixtures all failed explicitly in fresh probes.
- `validate_view_definition()` remained permissive and returned warnings for direct dataclass issues while strict SQL generation rejected the same invalid object.
