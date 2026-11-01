# Engineer Handoff - FP-15 HISTORIAN

## Triage

| Issue | Category | Severity | Result |
|---|---|---:|---|
| QA-001 | SPEC_VIOLATION | HIGH | RESOLVED and verified |

## Fix

Implemented model-aware qualified type-specifier validation for §6.3:
- Python fallback now rejects FHIR-qualified System primitive aliases such as `FHIR.Boolean`, `FHIR.Integer`, `FHIR.String`, `FHIR.Decimal`, `FHIR.Date`, `FHIR.DateTime`, and `FHIR.Time`.
- Native C++ now applies the same validation in `fn_isType()` / `fn_asType()` before empty-input short-circuiting, so `fhirpath_is_valid()` catches invalid type specifiers even when the validation resource lacks the left-side path.
- Native unqualified choice-type suffix behavior was preserved: `value.ofType(Integer)` still matches `valueInteger` through `fhir_type` metadata.
- Official R4 behavior was preserved for `System.Patient`: it resolves as a non-matching type, so `Patient.is(System.Patient).not()` returns true.

## Files Touched For Fix

- `fhir4ds/fhirpath/engine/__init__.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`

## Validation

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py::test_choice_type_oftype_matches_cpp -q` passed: 7 tests.
- `./build/release/test/unittest '*fhirpath*'` from `extensions/fhirpath` passed: 250 assertions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q` passed: 18 tests.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_convenience_udfs.py fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py -q` passed: 158 tests.
- `python3 -m pytest fhir4ds/fhirpath -q` passed: 1216 tests, 1 existing warning.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
