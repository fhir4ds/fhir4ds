# Engineer Handoff — FP-09 (iteration 1, 2026-08-17)

## Triage
| Issue | Category | Triage | Action |
|---|---|---|---|
| QA-001 | API_COMPLETENESS (LOW) | CONFIRMED | Fixed |
| QA-002 | SHARED_CONVENTION (LOW) | INTENDED | None (pin in AGENTS.md) |
| QA-003 | SHARED_CONVENTION (LOW) | INTENDED | None (pin in AGENTS.md) |

## QA-001 fix (surgical, Python-only; no extension rebuild)
- Root cause: the §5.6 direct-helper module
  (`fhir4ds/fhirpath/duckdb/functions/string.py`) predates the FP-09
  HISTORIAN direct-helper doctrine for `indexOf`; only the four sibling
  functions were exported, so direct-helper consumers had no indexOf.
- Fix (spec-grounded in FHIRPath §5.6.1):
  - Added `index_of(collection, substring_val)` to `string.py`:
    0-based first occurrence, `-1` not found, `''` argument → `0`,
    empty input collection or `None` (empty-argument) → empty,
    multi-item/non-String input raises `FHIRPathFunctionError` via the
    shared `_get_singleton_string` guard. Python `str.find` is
    code-point (UTF-8-aware) based, satisfying the GLOBAL_RULES
    Unicode-position mandate.
  - Registered `"indexOf"` in `STRING_FUNCTIONS`.
  - Exported `index_of` from `fhir4ds/fhirpath/duckdb/functions/__init__.py`.
- Backwards compatible: purely additive public helper; the UDF path
  already implemented indexOf correctly (verified by QA probe).

## Files changed
- `fhir4ds/fhirpath/duckdb/functions/string.py` (index_of + registry)
- `fhir4ds/fhirpath/duckdb/functions/__init__.py` (export)
- `fhir4ds/fhirpath/duckdb/tests/unit/test_string.py`
  (`TestIndexOfFp09Skeptic`, 10 focused cases)

## Validation (Recovery Gate)
- Focused: `pytest fhir4ds/fhirpath/duckdb/tests/unit/test_string.py` →
  117 passed.
- fhirpath tree: 1757 passed.
- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47 — OVERALL 2832/2832 (baseline held, no regressions).

All issues terminal; no new issues discovered.
