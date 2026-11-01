# QA Handoff - SOF-VD-08 / SKEPTIC
Chunk: SOF-VD-08 (SQL-on-FHIR ViewDefinition)
Sections: ViewDefinition.select.unionAll
Items: unionAll 0..* combines all rows from branch selection structures; UNION ALL semantics preserve duplicate rows; branch column compatibility and missing-column behavior; nested unionAll recursion; unionAll branches combined with forEach, forEachOrNull, repeat, and nested select; where filters interact with branch generation according to their scope
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Result: PASS

No issues found.
