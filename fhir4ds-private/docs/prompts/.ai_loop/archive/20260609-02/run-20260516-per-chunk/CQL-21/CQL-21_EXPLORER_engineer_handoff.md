# Engineer Handoff - CQL-21 EXPLORER

## Resolved

`QA-001` is resolved. Dynamic FHIR CodeSystem membership no longer falls through to generic SQL `IN`.

Root cause: `_translate_in_op` handled static `Code`, `Concept`, and `String` operands for `in CodeSystem`, but resource-backed operands such as `O.code` were already lowered to `fhirpath_text(resource, path)` and escaped the CodeSystem branch. The fallback emitted syntactically invalid SQL against a structured CodeSystem literal.

Fix: added dynamic FHIRPath-backed CodeSystem lowering in `fhir4ds/cql/translator/expressions/_operators.py`. It detects resource/path operands and emits a `fhirpath_bool` predicate that checks both CodeableConcept-style `<path>.coding.system` and Coding-style `<path>.system`.

Regression coverage: added `test_cql_clinical_dynamic_codesystem_membership_matches_cpp_registration` to `fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py`.

## Validation

- `PYTHONPATH=. python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/cql21_explorer_probe.py` passed the QA reproducer on forced Python fallback and native-loaded DuckDB.
- `PYTHONPATH=. python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py -q --tb=short` passed `6/6`.
- Adjacent clinical/type/WASM pytest passed `11/11`.
- Valueset/cache pytest passed `45/45`.
- Full conformance passed ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.
- Full pytest passed `7231 passed, 5 skipped, 9 warnings`.

## Notes

No new issues were discovered during remediation. I did not change the existing static `String in CodeSystem` behavior because that was already covered by prior CQL-21 tests and is a separate terminology-service contract question, not needed for `QA-001`.
