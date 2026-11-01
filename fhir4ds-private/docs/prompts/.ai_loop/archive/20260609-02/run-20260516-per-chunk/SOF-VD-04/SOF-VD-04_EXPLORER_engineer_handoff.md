# Engineer Handoff: SOF-VD-04 EXPLORER

## Issue Resolved

`QA-001` MEDIUM: `collection=true` primitive typed columns returned
`VARCHAR[]` because SQL generation used raw `fhirpath(...)` for every
collection column. This bypassed the scalar primitive type path.

## Fix

Updated `SQLGenerator.generate_column_expr()` so collection columns with
declared primitive numeric/boolean types wrap `fhirpath(...)` in
`list_transform(..., _v -> TRY_CAST(_v AS <type>))`.

Preserved existing behavior for:

- string-like primitives and temporal strings
- untyped collection columns
- complex JSON and element-ID collection outputs
- runtime cardinality/type guard errors

## Regression Coverage

Added native C++ vs forced Python fallback coverage for:

- `integer` collection output from full FHIR StructureDefinition URI
- `boolean` collection output from expression-derived values
- existing string and complex collection behavior remained covered

## Validation

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py fhir4ds/viewdef/tests/integration/test_duckdb.py -q`
  - `203 passed`
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_viewdef.py`
  - `Summary: 134/134 tests passed (100.0%)`
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep ...`
  - `OVERALL COMPLIANCE | 2822 | 2822 | 100.0%`

No new issues discovered.
