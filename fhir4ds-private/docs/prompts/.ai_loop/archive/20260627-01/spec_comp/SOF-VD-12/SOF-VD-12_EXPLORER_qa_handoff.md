# QA Handoff - SOF-VD-12 / EXPLORER
Chunk: SOF-VD-12 (SQL-on-FHIR ViewDefinition)
Sections: Profiling, Shareable View Definition, Tabular View Definition, Mappings, XML, JSON
Items: Shareable and Tabular profile-required metadata handling, JSON representation uses official field names and round-trips through parser/generator inputs, XML representation support is implemented or explicitly documented as unsupported, canonical URL, version, status, and profile metadata do not break execution, FHIR mapping/profile fields are retained, ignored, or rejected consistently with documented behavior, official examples serialize and parse consistently across supported formats
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (214 passed, 0 failed, 0 errors)

No issues found.
