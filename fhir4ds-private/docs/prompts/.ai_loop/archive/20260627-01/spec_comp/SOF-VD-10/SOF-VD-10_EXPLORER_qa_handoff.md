# QA Handoff - SOF-VD-10 / EXPLORER
Chunk: SOF-VD-10 (SQL-on-FHIR ViewDefinition)
Sections: Terminology Bindings, Constraints: sql-name/sql-expressions, Cardinality and required fields
Items: sql-name regex for ViewDefinition.name, constant.name, and column.name, sql-expressions constraint: at most one of forEach, forEachOrNull, or repeat, required field validation for resource, select, column.path, column.name, constant.name, constant.value[x], and where.path, resource binding validation against FHIR ResourceType, fhirVersion binding validation against FHIRVersion, expectError official fixtures fail explicitly rather than being skipped, permissive versus strict validation modes are clearly separated
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (214 passed, 0 failed, 0 errors)

No issues found.
