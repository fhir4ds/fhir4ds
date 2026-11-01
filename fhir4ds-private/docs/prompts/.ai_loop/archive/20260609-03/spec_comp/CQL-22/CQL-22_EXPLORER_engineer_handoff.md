# Engineer Handoff - CQL-22 EXPLORER

## Issue Resolved
- `CQL22-EXPLORER-001` HIGH, `SPEC_VIOLATION`.
- Spec: CQL 1.5.3 Reference Appendix B defines `Message(source T, condition Boolean, code String, severity String, message String) T`.

## Root Cause
- `fhir4ds/cql/translator/expressions/_functions.py::_validate_message_signature_args` validated the Boolean `condition` operand and String `severity` / `message` operands, but omitted the String `code` operand.
- Statically invalid code expressions such as integer literals, Booleans, or aliases through `as Any` could reach the SQL helper and be cast at runtime.

## Fix
- Extended the existing static String operand validation loop to include argument index 2 (`code`).
- Added focused regression coverage in `fhir4ds/cql/duckdb/tests/integration/test_message_parity.py` for non-String code operands.
- Updated `extensions/cql/AGENTS.md` so future CQL-22 work remembers that `code`, `severity`, and `message` are all String operands at the translator boundary.

## Validation
- `.temp/qa/cql22_explorer_probe.py`: PASS.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_message_parity.py -q`: 8 passed.
- `python3 -m pytest fhir4ds/cql/tests/official/test_cql_compliance.py -q -k CqlErrorsAndMessaging`: 4 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## New Issues
- None.
