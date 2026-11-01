# QA Handoff - SOF-VD-10 EXPLORER

## Scope Probed
- SQL-on-FHIR `sql-name` invariant for root `ViewDefinition.name`, `constant.name`, and `column.name` across valid names, leading underscores, punctuation, empty strings, and non-strings.
- Required field and binding failures for `resource`, `select`, `column.path`, `column.name`, `constant.name`, `constant.value[x]`, `where.path`, ResourceType, and FHIRVersion.
- `sql-expressions` mutual exclusion for all pairs among `forEach`, `forEachOrNull`, and `repeat`.
- Direct dataclass/generator bypasses for invalid root names, constants, fhirVersion, where, column names, and iterator conflicts.
- `validate_view_definition()` permissive warning behavior for direct dataclass issues.
- Generated ViewDefinition execution over DuckDB registration with the available FHIRPath registration path and forced Python fallback.

## Spec Basis
- SQL-on-FHIR v2 marks `sql-name` on `ViewDefinition.name`, `ViewDefinition.constant.name`, and `ViewDefinition.select.column.name` with regex `^[A-Za-z][A-Za-z0-9_]*$`.
- SQL-on-FHIR v2.1 pre-release makes the `sql-expressions` invariant explicit for `forEach`, `forEachOrNull`, and `repeat`; the active codebase already targets that stricter chunk requirement.
- FHIR JSON resource format says repeating elements use JSON arrays and present properties cannot be null except the documented primitive-extension alignment case.

## Finding
- `QA-EXPLORER-001` (MEDIUM): strict `parse_view_definition()` accepts present-null optional/repeating fields for `constant` and `fhirVersion` as if absent. Reproducer: `constant: null` and `fhirVersion: null` both returned a `ViewDefinition`. Expected strict parser rejection; absent optional fields should remain allowed.

## Non-Findings
- `sql-name` validation is enforced for parser/from_dict and strict generator paths.
- Required resource/select/column/constant/where fields fail explicitly.
- ResourceType and FHIRVersion bad string values fail explicitly.
- Direct dataclass generator guards reject the SOF-VD-10 bypass cases tested.
- Official `expectError` handling in the ViewDefinition pytest harness is explicit (`pytest.fail` if an expected-error case is accepted).
- Native C++ extension did not load in this environment (`register_fhirpath()` returned `False`), so execution parity was available only between normal registration fallback and forced Python fallback; both returned `[('555',), (None,)]` for the generated ViewDefinition probe.
