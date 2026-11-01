# QA Handoff - SOF-VD-09 / EXPLORER
Chunk: SOF-VD-09 (SQL-on-FHIR ViewDefinition)
Sections: Key Elements: Where; ViewDefinition.where; ViewDefinition.where.path/description
Items: where 0..* root-level FHIRPath constraints; every where constraint must evaluate true for resource inclusion; false, empty, and null filter results exclude rows as specified; non-boolean where results are rejected or surfaced as spec errors; where.description 0..1 human-readable text retention; constant references and complex FHIRPath expressions inside where clauses; filter SQL generation preserves intended root-resource scope
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Result: PASS

No issues found.
