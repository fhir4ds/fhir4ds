# Engineer Handoff - FP-20 EXPLORER - 2026-05-17

Resolved `QA-FP20-EXP-001`.

Changes made:

- Added Python core `defineVariable()` support in `fhir4ds/fhirpath/engine/invocations/misc.py`.
- Registered `defineVariable` in `fhir4ds/fhirpath/engine/invocations/__init__.py` with one- and two-argument forms.
- Added invocation-chain tracking in `fhir4ds/fhirpath/engine/evaluators/__init__.py` so same-chain redefinition is rejected and chain state is cleaned up after evaluation.
- Restored transient environment-variable state around `where()`, `select()`, `repeat()`, `all()`, and `aggregate()` expression-parameter evaluation to prevent variables defined inside callbacks from leaking.
- Added native-vs-forced-fallback regression coverage in `fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py`.

Validation:

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py -q` passed: 5 tests.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py -q` passed: 18 tests.
- `python3 -m pytest fhir4ds/fhirpath -q` passed: 1305 tests, 1 existing warning.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No C++ was touched, so no native extension rebuild/copy was required.
