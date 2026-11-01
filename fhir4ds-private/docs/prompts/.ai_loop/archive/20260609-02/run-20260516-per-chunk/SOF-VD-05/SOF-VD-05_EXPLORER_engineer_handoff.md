# Engineer Handoff: SOF-VD-05 EXPLORER

## Triage

| Issue | Severity | Category | Terminal Status |
| --- | --- | --- | --- |
| QA-001 | MEDIUM | SPEC_VIOLATION | RESOLVED |
| QA-002 | LOW | VALIDATION_GAP | RESOLVED |

## Fixes

### QA-001

`SQLGenerator._validate_union_all_columns()` now compares union branch output
schema as `(column name, normalized declared FHIR type, collection flag)` rather
than only column names/order. Branches with matching names but mismatched FHIR
types or scalar/collection cardinality now fail before SQL execution, matching
the SQL-on-FHIR functional model requirement that `unionAll` operands have the
same number of columns with the same names, order, and FHIR types.

### QA-002

`SQLGenerator._validate_select_shape()` now validates direct dataclass inputs
recursively:
- `select` containers must be arrays of `Select` objects.
- `column` containers must be arrays of `Column` objects.
- nested `select` and `unionAll` containers must be arrays of `Select` objects.

This keeps public direct-construction guardrails aligned with parser validation
instead of allowing raw `TypeError`/`AttributeError` or silent `None` handling.

## Files Changed

- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/unit/test_generator.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.ai_loop/qa_handoff.md`
- `.ai_loop/evolution.json`

## Validation

- Focused generator unit tests: `7 passed`
- Focused native/fallback DuckDB integration: `1 passed`
- Adjusted nested-union native/fallback integration: `2 passed`
- Full ViewDefinition pytest: `830 passed`
- ViewDefinition conformance: `134/134 tests passed (100.0%)`
- Full conformance: `2822/2822 OVERALL COMPLIANCE (100.0%)`
- Full package pytest: `7368 passed, 5 skipped, 9 warnings`

No new issues were discovered during remediation.
