# Engineer Handoff - SOF-VD-10

## Triage

| Issue | Category | Severity | Status |
|---|---|---:|---|
| QA-001 | SPEC_VIOLATION | MEDIUM | RESOLVED |

## Fix Summary

- Added parser/public `ViewDefinition.from_dict()` validation for optional `ViewDefinition.name` using the SQL-on-FHIR `sql-name` invariant.
- Added strict SQL generator validation for direct dataclass `ViewDefinition.name`, `ViewDefinition.fhirVersion`, and direct `Constant` objects before constant resolution or SQL generation.
- Changed the ViewDefinition spec test helper so accepted `expectError` fixtures call `pytest.fail()` instead of `pytest.xfail()`.

## Spec Basis

- SQL-on-FHIR v2.0.0: `ViewDefinition.name`, `ViewDefinition.constant.name`, and `ViewDefinition.select.column.name` use `sql-name` (`^[A-Za-z][A-Za-z0-9_]*$`).
- SQL-on-FHIR v2.0.0: `ViewDefinition.resource` is required and bound to FHIR `ResourceType`; `ViewDefinition.fhirVersion` is bound to `FHIRVersion`; `constant.name`, `constant.value[x]`, `column.path`, `column.name`, and `where.path` are required under their parent elements.
- SQL-on-FHIR v2.1.0-pre: `sql-expressions` permits at most one of `forEach`, `forEachOrNull`, or `repeat`.

## Validation

- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py -q` -> 194 passed.
- `python3 conformance/scripts/run_viewdef.py | grep -E "FAIL|ERROR|Passed|Running|Overall|passed|failed|ViewDefinition|Report"` -> 134/134 passed.
- `python3 -m pytest fhir4ds/viewdef/tests/test_spec_compliance.py -q -rxXs` -> 435 passed.
- Normal vs forced Python fallback ViewDefinition execution probe matched rows `[('p1', '555'), ('p2', None)]`; native C++ extension registration returned `False` in this workspace, so no native/C++ comparison was available.
- `python3 -m pytest fhir4ds/viewdef -q --tb=short` -> 884 passed.

## Notes

`validate_view_definition()` remains the permissive warning API; strict rejection is enforced by parser/from_dict and generator guard paths.
