# Engineer Handoff: CQL-22 SKEPTIC

Issue resolved:
- `CQL22-SKEPTIC-001` HIGH: `CQLMessage` was missing from the no-Python/browser-style runtime. Translated `Message` expressions can emit `CQLMessage`, so SQL-only execution failed with a catalog error.

Root cause:
- `CQLMessage` existed as part of Python supplement registration, but `register_all_macros()` did not include a pure SQL macro. The no-Python runtime loads C++ extensions plus pure macros only.

Fix:
- Added `CQLMessage(source, condition, code, severity, message)` to `fhir4ds/cql/duckdb/macros/math.py`.
- Made `fhir4ds/cql/duckdb/udf/math.py` tolerate the macro already existing before registering the legacy Python UDF.
- Added no-Python direct and translated `Message` coverage in `fhir4ds/cql/duckdb/tests/integration/test_message_parity.py`.
- Updated the existing parameter-severity test to use the supported runtime-parameter path, `translate_library_to_population_sql(..., parameters=...)`, rather than legacy `setvariable()` expectations for `translate_cql()` with a declared default.
- Recorded the invariant in `extensions/cql/AGENTS.md`.

Validation:
- `.temp/qa/cql22_skeptic_probe.py`: PASS across Python fallback, native-loaded, and no-Python.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_message_parity.py -q`: 7 passed.
- Focused no-Python translate/execute gate: 2 passed.
- `python3 conformance/scripts/run_cql.py`: CQL 1706/1706, messaging 4/4.
- `python3 conformance/scripts/run_all.py`: overall 2822/2822.
