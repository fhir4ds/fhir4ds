# Engineer Handoff — SOF-VD-04, iteration 1

## QA-001 (MEDIUM) — RESOLVED
- Root cause: `parser._parse_column` had no unknown-field allowlist (only the targeted plural-`tags` guard); `ColumnTag.from_dict` ignored extra keys. Reference validator schema (legacy-tests/tests.schema.json) sets `additionalProperties:false` on both column and tag objects.
- Fix: `_COLUMN_FIELDS` frozenset {name,path,description,collection,type,tag}; unknown column fields raise ParseError; unknown tag keys raise ValueError (wrapped as ParseError). Files: fhir4ds/viewdef/parser.py, fhir4ds/viewdef/types.py.

## QA-002 (LOW) — RESOLVED
- Root cause: element-ID `column.type` declarations skip runtime type probes by design (backbone shapes not identifiable via `type().name`), so statically impossible declarations (leading resource segment != ViewDefinition.resource) passed silently. Spec: "should report an error if the returned type does not match the type set here".
- Fix: `SQLGenerator._validate_element_id_column_types` (generator.py) rejects element-ID types whose leading segment differs from ViewDefinition.resource, walking select/unionAll trees. Same-resource element-ID declarations unchanged (runtime cardinality-only guard).
- Type fix note in docstring: "SQL-on-FIR" typo corrected to "SQL-on-FHIR".

## Validation
- Reproducers: all three now rejected with actionable messages.
- ViewDef suite: 1177/1177 (1171 baseline + 6 new tests in test_parser.py).
- Master gate: ViewDef 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832.
- Binaries unchanged (Python-only fixes): cql c5b22d58310c1eb7bafa17ce7877f989, fhirpath 57d0634b6ee6eddee9fc06a1355bef5a — repo and site-packages md5-matched.
