# QA Handoff - SOF-VD-03 / SKEPTIC
Chunk: SOF-VD-03 (SQL-on-FHIR ViewDefinition)
Sections: Key Elements: Select, ViewDefinition.select, ViewDefinition.select.column, ViewDefinition.select.column.path/name/description
Items: select 1..* required and non-empty, column 0..* within each select, column.path 1..1 FHIRPath expression relative to the active context, column.name 1..1 SQL-safe output name, column.description 0..1 markdown retention, multiple select blocks and deterministic column ordering, root and select-relative FHIRPath evaluation contexts
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (214 passed, 0 failed, 0 errors)

No issues found.
