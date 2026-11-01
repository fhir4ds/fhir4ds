# Engineer Handoff - FP-13 HISTORIAN

## Resolved Issues

### QA-001

- Fixed native ordered multi-item `=`/`!=` so singleton pair comparisons can return the FHIRPath empty result instead of being forced through Boolean `fpValuesEqual()`.
- The native path now propagates empty for Date/Time precision mismatch and incompatible Quantity dimensions inside equal-length ordered collection equality.
- Files changed:
  - `extensions/fhirpath/src/fhirpath/evaluator.cpp`
  - `extensions/fhirpath/test/sql/fhirpath.test`
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py`
  - `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`

### QA-002

- Fixed forced Python fallback complex equivalence for list-valued child properties containing complex objects.
- Replaced direct `sorted(list)` comparison with recursive order-independent matching.
- Files changed:
  - `fhir4ds/fhirpath/engine/invocations/equality.py`
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py`

## Validation

- Fresh FP-13 probe: `47` cases, `0` failures.
- Focused pytest: `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py` -> `8 passed`.
- Native sqllogictest: `548 assertions in 2 test cases`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.

## State

- `QA-001`: `RESOLVED`
- `QA-002`: `RESOLVED`
- `evolution.json` advanced to `phase: ARCHITECT`.
