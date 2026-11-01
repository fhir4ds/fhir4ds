# Engineer Handoff - FP-14 EXPLORER

## Triage

| Issue | Severity | Category | Status |
|---|---:|---|---|
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fix

Root cause:
`fhir4ds/fhirpath/engine/util.py::parse_value()` only materialized FHIR
Quantity-shaped dicts when `code` was present. Native C++ recognizes `value`
plus `code` or `unit`, so forced Python fallback treated display-unit-only
FHIR Quantity path values as plain dicts and returned empty for comparisons.

Change:
Use `code` or `unit` as the Quantity unit source, and recognize dicts with
`value` plus either field.

Regression:
Added `test_fhir_quantity_unit_only_path_comparisons_match_python_fallback()` to
`fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`.

## Validation

- `python3 .temp/qa/fp14_explorer_fresh/probe_fp14_comparison.py` passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py -q` passed: 112 passed.
- `python3 -m pytest fhir4ds/fhirpath -q` passed: 1208 passed, 1 existing warning.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2822/2822.

## Files Changed

- `fhir4ds/fhirpath/engine/util.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`
- `fhir4ds/fhirpath/AGENTS.md`

