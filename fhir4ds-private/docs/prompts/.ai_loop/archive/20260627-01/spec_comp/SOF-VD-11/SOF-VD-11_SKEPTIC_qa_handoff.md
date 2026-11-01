# QA Handoff - SOF-VD-11 / SKEPTIC
Chunk: SOF-VD-11 (SQL-on-FHIR ViewDefinition)
Sections: View Runner, Examples
Items: execute a ViewDefinition and return tabular rows, simple Patient and Observation example views, unrolling arrays such as Patient.address into row sets, filtered Observation/resource views, column type coercion into DuckDB result columns, official SQL-on-FHIR v2 spec_tests parity, parser, generator, and DuckDB execution agree for supported examples
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (214 passed, 0 failed, 0 errors)

No issues found.
