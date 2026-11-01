# Engineer Handoff: FP-08 EXPLORER

## Triage

| Issue | Severity | Category | Status |
|---|---:|---|---|
| QA-001 | MEDIUM | SPEC_VIOLATION | RESOLVED |

## Fix

Resolved `QA-001`: native C++ `fn_toQuantity()` accepted empty quoted units in String quantity conversion.

Spec reference: FHIRPath §5.5.7 quantity string conversion regex requires quoted units to match `[^']+`, so `1 ''` is not convertible.

Root cause: the quoted-unit parser in `extensions/fhirpath/src/fhirpath/evaluator.cpp` scanned from the opening quote to the closing quote but did not reject a zero-length span.

Change:

- Added `if (idx == unit_start) return {};` before constructing the quantity unit.
- Added forced native-vs-Python fallback parity cases for `toQuantity()` and `convertsToQuantity()`.
- Added native SQL extension assertions for the bundled C++ extension.
- Rebuilt `extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension`.
- Copied the rebuilt binary to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

## Validation

- Reproducer before fix: new parity test failed with native `true` vs fallback `false`.
- Reproducer after fix: native and forced fallback both returned empty/false.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py::test_quantity_string_parser_edges_match_python_fallback -q --tb=short` -> passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath` -> 154 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q --tb=short` -> 10 passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py -q --tb=short` -> 120 passed.
- `python3 -m pytest fhir4ds/fhirpath -q --tb=short` -> 1174 passed, 1 existing warning.
- `python3 conformance/scripts/run_all.py | grep ...` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2822/2822.

## Notes

No new issues discovered during remediation.
