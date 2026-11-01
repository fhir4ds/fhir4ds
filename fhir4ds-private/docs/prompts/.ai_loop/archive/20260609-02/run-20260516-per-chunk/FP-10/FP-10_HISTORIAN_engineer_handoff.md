# Engineer Handoff - FP-10 HISTORIAN

Resolved `QA-001` by tightening the native C++ Unicode uppercase mapping in `extensions/fhirpath/src/fhirpath/evaluator.cpp`.

Root cause:
- `fn_upper()` used a simple code-point mapping table.
- U+03C2 Greek final sigma was checked after the broader U+03B1-U+03C9 range, so it mapped to U+03A2 instead of U+03A3.
- U+00DF German sharp s was not handled as a multi-code-point uppercase mapping, so it remained `ß` instead of `SS`.

Fix:
- Added a dedicated U+00DF branch that appends `SS`.
- Moved the U+03C2 final-sigma branch before the generic Greek lowercase range.
- Added native SQL regression assertions in `extensions/fhirpath/test/sql/fhirpath.test`.
- Added public native-vs-Python parity coverage to `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`.
- Rebuilt the native extension and copied the refreshed `fhirpath.duckdb_extension` into `fhir4ds/fhirpath/duckdb/extensions/`.

Validation:
- Native smoke: `Straße.upper()` -> `STRASSE`; `Σςσ.upper()` -> `ΣΣΣ`.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"`: 180 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py -q`: 2 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_string.py fhir4ds/fhirpath/tests/unit/test_new_functions.py -q`: 174 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q`: 12 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
