# SOF-VD-11 HISTORIAN Engineer Handoff

Resolved:
- `QA-001` HIGH / SPEC_VIOLATION.

Root cause:
- Python fallback had `getResourceKey()`/`getReferenceKey()` in the core
  invocation registry, but native C++ did not include those functions in the
  known-function list or `Evaluator::evalFunction()` dispatch. Native
  ViewDefinition execution therefore treated required SQL-on-FHIR View Runner
  helpers as unknown functions and materialized NULL output.

Fix:
- Added native C++ dispatch for `getResourceKey()` and
  `getReferenceKey([Type])`.
- Validated `getReferenceKey([Type])` type specifiers through the existing
  native type-validation path so unknown type arguments match fallback
  `fhirpath_is_valid()` behavior.
- Added the functions to native known-function validation and the Python UDF
  warning allowlist.
- Rebuilt and copied the bundled `fhirpath.duckdb_extension`.
- Added regression coverage in native SQL tests, FHIRPath native/fallback
  parity tests, and ViewDefinition integration tests.

Validation:
- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/sof_vd_11_historian_probe.py`
  passed: parser validation, PatientDemographics rows, Patient.address row
  unrolling, filtered Observation blood-pressure rows, native/fallback parity,
  and DOUBLE quantity result columns.
- Focused pytest: 2 passed.
- `python3 -m pytest fhir4ds/viewdef/tests/test_spec_compliance.py -q`:
  435 passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q`: 888 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py -q`:
  9 passed.
- `python3 conformance/scripts/run_viewdef.py`: 134/134 passed.
- `python3 conformance/scripts/run_all.py`: ViewDefinition 134/134,
  FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `./build/release/test/unittest "*fhirpath*"`: 304 assertions passed.

Changed paths:
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/src/fhirpath_extension.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/udf.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/viewdef/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
