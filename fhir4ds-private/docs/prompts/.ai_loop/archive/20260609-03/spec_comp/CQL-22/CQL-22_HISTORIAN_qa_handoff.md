# QA Handoff: CQL-22 HISTORIAN

Scope: CQL-22 Errors and Messaging, HISTORIAN personality, iteration 1. Focus was the published `Message(source, condition, code, severity, message)` signature and runtime behavior across Python fallback, native-loaded DuckDB, and no-Python/browser-style SQL surfaces.

Finding: `CQL22-HISTORIAN-001` HIGH `SPEC_VIOLATION`. Fresh probes showed statically invalid operands translated instead of failing: non-Boolean `condition` values such as `1` and `'true'`, non-String `severity` values such as `5` and `true`, and non-String `message` values such as `5` and `false`. The CQL Reference signature requires `condition Boolean`, `severity String`, and `message String`.

Coverage added:
- Fresh probe: `.temp/qa/cql22_historian_probe.py`
- Regression tests: `fhir4ds/cql/duckdb/tests/integration/test_message_parity.py`
- Tested valid `Message` returns for non-Error severities, false/null conditions, null code/message, parameter default severity, list source preservation, and true-condition Error severity raising.
- Tested invalid static signature operands raising `TranslationError`.
- Rechecked Python fallback, native-loaded DuckDB registration, and no-Python macro execution.

Validation:
- `python3 .temp/qa/cql22_historian_probe.py` -> PASS
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_message_parity.py -q` -> 8 passed
- `python3 conformance/scripts/run_cql.py | grep -E 'CqlErrorsAndMessagingOperatorsTest|Summary|FAIL|ERROR|passed'` -> `CqlErrorsAndMessagingOperatorsTest.xml: 4/4 passed`, `Summary: 1706/1706 tests passed (100.0%)`
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> overall 2822/2822

No remaining open QA issues for this pass.
