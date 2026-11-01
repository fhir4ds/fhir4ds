# QA Handoff - SOF-VD-05 / SKEPTIC
Chunk: SOF-VD-05 (SQL-on-FHIR ViewDefinition)
Sections: ViewDefinition.select.select, Nested select contentReference
Items: nested select 0..* recursion through contentReference to ViewDefinition.select, child selects use the parent forEach/forEachOrNull context when present, default context is effectively $this when row generators are absent, parent and child columns combine into expected output rows, column name collision and duplicate-name validation behavior, empty nested select and column combinations produce defined output or errors
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (214 passed, 0 failed, 0 errors)

No issues found.
