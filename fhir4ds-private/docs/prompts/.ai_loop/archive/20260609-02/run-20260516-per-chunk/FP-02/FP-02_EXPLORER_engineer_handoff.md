# Engineer Handoff - FP-02 EXPLORER

## Issues Resolved
- QA-001: Python DuckDB fallback singleton Boolean/iif drift. Root cause was `FHIRPathEvaluator` preferring external `fhirpathpy`, which still mishandled operand order and singleton truthiness for FP-02 cases. Fixed by preferring the in-repo `fhir4ds.fhirpath` engine.
- QA-002: Native `gender.not()` returned empty from the packaged binary while source was already corrected. Rebuilt `extensions/fhirpath` and copied the refreshed `fhirpath.duckdb_extension` into the Python package.

## Files Changed
- `fhir4ds/fhirpath/duckdb/evaluator.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

## Validation
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q` -> 13 passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath` -> 114 assertions passed.
- Fresh native smoke: `gender.not()`, `true and gender`, `zero and true`, `iif(gender, 1, 2)` all matched expected singleton Boolean behavior.
- Fresh forced Python fallback smoke: `gender.not()`, `true and gender`, `zero and true`, `iif(gender, 'yes', 'no')` all matched expected non-strict wrapper behavior.
- `python3 conformance/scripts/run_all.py | grep ...` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Residual Risk
- DuckDB extension loading is process-global enough that same-process native/fallback comparison can be polluted after a native extension has loaded. Fresh-process fallback smoke tests are the reliable way to validate true Python fallback startup behavior.
