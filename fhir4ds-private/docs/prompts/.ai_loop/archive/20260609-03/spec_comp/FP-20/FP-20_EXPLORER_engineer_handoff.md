# Engineer Handoff — FP-20 EXPLORER

Resolved `QA-001` as a native metadata parity defect. Root cause: `extensions/fhirpath/src/fhirpath/evaluator.cpp::fhirFieldType()` classified unknown primitive string fields as FHIR `string` unless they appeared in a small code-field allowlist; R4 `Questionnaire.subjectType` was missing from that list.

Fix implemented:
- Added `subjectType` to the native FHIR primitive code-field metadata.
- Added native/fallback parity coverage for `Questionnaire.subjectType.type().name`, `.is(code)`, and `.is(string)` in `test_environment_type_parity.py`.
- Added native sqllogictest assertions in `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied the bundled `fhirpath.duckdb_extension`.
- Recorded the fragile area in `fhir4ds/fhirpath/AGENTS.md` and `extensions/fhirpath/AGENTS.md`.

Validation:
- `python3 .temp/qa/fp20_explorer_probe.py`: 81 cases, 16 validity checks, 0 mismatches.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py -q`: 9 passed.
- `./extensions/fhirpath/build/release/test/unittest test/sql/fhirpath.test`: 356 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No open remediation items remain for this pass.
