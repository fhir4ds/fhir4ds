## Engineer Handoff - FP-02 SKEPTIC

Resolved issues:
- `QA-001` MEDIUM RESOLVED: forced Python fallback `fhirpath()` list UDF no longer leaks `NotImplementedError` for unknown function invocations such as `unknownFunction()`.

Root cause:
- `fhirpath_scalar()` explicitly re-raised `NotImplementedError`, unlike native C++ and the typed public wrappers (`fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_number`) that expose invalid/evaluation failures as empty/NULL in non-strict public SQL use.

Fix:
- `fhir4ds/fhirpath/duckdb/udf.py`: changed `fhirpath_scalar()` to return `[]` for `NotImplementedError` in non-strict mode, preserving strict-mode propagation.
- `fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py`: added native-vs-forced-fallback regression coverage asserting `unknownFunction()` returns `[]`/NULL public outputs and `fhirpath_is_valid=false`.
- `fhir4ds/fhirpath/AGENTS.md`: updated the FP-02 fragile-area entry to fixed.

Validation:
- `python3 .temp/qa/fp02_skeptic_fresh_probe.py` passed.
- `python3 .temp/qa/fp02_skeptic_diff_probe.py` passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q` passed: 9 tests.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > .temp/qa/fp02_skeptic_validation_summary.log && cat .temp/qa/fp02_skeptic_validation_summary.log` passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

State:
- `evolution.json.phase` set to `ARCHITECT`.
- No new issues discovered during remediation.
