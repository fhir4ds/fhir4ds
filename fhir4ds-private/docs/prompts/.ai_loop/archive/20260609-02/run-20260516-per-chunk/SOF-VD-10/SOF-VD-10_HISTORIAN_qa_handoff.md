# QA Handoff - SOF-VD-10 HISTORIAN

## Scope Probed

- SQL-on-FHIR ViewDefinition `sql-name` invariant for `ViewDefinition.name`,
  `constant.name`, and `select.column.name`.
- `sql-expressions` mutual exclusion for `forEach`, `forEachOrNull`, and
  `repeat`.
- Required fields: root `resource`/`select`, `column.path`, `column.name`,
  `constant.name`, `constant.value[x]`, and `where.path`.
- Terminology bindings for `resource` (`ResourceType`) and `fhirVersion`
  (`FHIRVersion`).
- Official `expectError` fixture behavior and native C++ vs forced Python
  fallback execution parity for a ViewDefinition using `forEachOrNull`.

## Spec Basis

The SQL-on-FHIR v2.1.0-pre ViewDefinition StructureDefinition lists
`ViewDefinition.resource` and `ViewDefinition.fhirVersion` with required
terminology bindings, defines `sql-expressions` as an error constraint allowing
at most one of `forEach`, `forEachOrNull`, or `repeat`, and defines `sql-name`
as `^[A-Za-z][A-Za-z0-9_]*$` for root, constant, and column names.

## Finding

- `QA-001` MEDIUM API_CONTRACT: `validate_view_definition()` is documented as
  permissive and returning warnings, but a direct dataclass ViewDefinition with
  both `forEach` and `repeat` raises `ValidationError` before returning any
  warning list. Strict parser/generator behavior is correct; the gap is the
  permissive validation API boundary.

## Reproducer

`PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/sof_vd10_historian_probe.py`

The script fails at `exercise_permissive_validation_boundary()` with:
`ValidationError: select[0]: Select can only have at most one of forEach, forEachOrNull, or repeat; got forEach, repeat`.
