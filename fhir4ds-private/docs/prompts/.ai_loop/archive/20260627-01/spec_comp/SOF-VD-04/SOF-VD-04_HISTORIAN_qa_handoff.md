# QA Handoff - SOF-VD-04 / HISTORIAN
Chunk: SOF-VD-04 (SQL-on-FHIR ViewDefinition)
Sections: ViewDefinition.select.column.collection, ViewDefinition.select.column.type, ViewDefinition.select.column.tag
Items: collection default false when unset, error when multiple values are produced for a non-collection column, collection true multi-value output representation, type URI handling for primitive and non-primitive result expectations, type mismatch reporting for generated/executed columns, tag 0..* parsing with required tag.name and tag.value, database/implementation type-hint tags do not affect base semantics unless explicitly handled
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (214 passed, 0 failed, 0 errors)

No issues found.
