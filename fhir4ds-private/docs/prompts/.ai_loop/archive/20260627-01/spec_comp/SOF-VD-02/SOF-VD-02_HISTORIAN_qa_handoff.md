# QA Handoff - SOF-VD-02 / HISTORIAN
Chunk: SOF-VD-02 (SQL-on-FHIR ViewDefinition)
Sections: Key Elements: Constants, ViewDefinition.constant, ViewDefinition.constant.name, ViewDefinition.constant.value[x]
Items: constant 0..* parsing using the spec singular field name, constant.name 1..1 with sql-name validation and %name FHIRPath reference, value[x] 1..1 exactly-one behavior, primitive value types: base64Binary, boolean, canonical, code, date, dateTime, decimal, id, instant, integer, integer64, oid, string, positiveInt, time, unsignedInt, uri, url, uuid, constant substitution in column paths and where filters, invalid/missing constant values raise explicit spec errors
Command: python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (214 passed, 0 failed, 0 errors)

No issues found.
