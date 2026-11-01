# QA Handoff: SOF-VD-02 HISTORIAN

## Scope

SQL-on-FHIR ViewDefinition constants:
- `ViewDefinition.constant` singular 0..*
- `constant.name` sql-name and `%name` references
- `constant.value[x]` exactly-one behavior and primitive value choices
- constant substitution in column paths and where filters

## Spec Sources Consulted

- SQL-on-FHIR CI build `StructureDefinition-ViewDefinition-definitions.html`, lines for `ViewDefinition.constant`, `constant.name`, and `constant.value[x]`.
- FHIR R5 `datatypes.html`, primitive datatype table for JSON representation, ranges, and lexical constraints.

## Fresh Validation/Exploration

- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_constants.py fhir4ds/viewdef/tests/test_spec_compliance.py -q`
  - Result: 475 passed.
- Native/Fallback execution probe:
  - ViewDefinition using `constant` singular with `%name_use` in both root `where` and column path.
  - Native registration returned `('pt1', 'Smith')`.
  - Forced Python fallback returned `('pt1', 'Smith')`.

## Findings

1. `SOF-VD-02-HIST-001` HIGH: parser accepts non-spec complex constant choices `valueCoding` and `valueCodeableConcept`.
2. `SOF-VD-02-HIST-002` MEDIUM: parser accepts invalid FHIR primitive constant values such as negative `positiveInt`, integer overflow, invalid dates/times, malformed OID/UUID/code/base64 values.
3. `SOF-VD-02-HIST-003` MEDIUM: `ViewDefinition.from_dict()` ignores spec singular `constant`, while `parse_view_definition()` parses it.

## Not A Bug

- Constant substitution in generated SQL for column paths and where filters worked in both native/C++ and forced Python fallback FHIRPath registration.
