# QA Handoff - SOF-VD-06 / EXPLORER
Chunk: SOF-VD-06 (SQL-on-FHIR ViewDefinition)
Sections: ViewDefinition.select.forEach, ViewDefinition.select.forEachOrNull
Items: forEach 0..1 FHIRPath expression selects parent elements for the containing select, forEach multiplies rows for each item in the selected collection, forEach suppresses rows when the collection is empty, forEachOrNull preserves one row with null nested values when the collection is empty, nested columns are evaluated relative to each iterated item, built-in ViewDefinition/FHIRPath variables remain correct in iterated contexts, including %context, %resource, %rootResource, and %rowIndex
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (214 passed, 0 failed, 0 errors)

No issues found.
