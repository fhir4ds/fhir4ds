# Engineer Handoff

**Date**: 2026-05-07
**Role**: REMEDIATION_ENGINEER
**Session scope**: QA-001 (CRITICAL), QA-002 (HIGH)

## Issues Fixed

### QA-001 (CRITICAL): ReactiveEvaluator.update() broken API call

**File**: `/mnt/d/fhir4ds/fhir4ds/dqm/reactive.py`

**Root cause**: `ReactiveEvaluator` was written against an old `MeasureEvaluator` API that accepted `measure` as a constructor arg. After refactoring, `MeasureEvaluator.__init__` takes `(conn, audit_or_strategy)` and `evaluate()` requires `measure_bundle` and `cql_library_path` as positional args. The reactive module was never updated.

**Fix applied**:
1. Changed `ReactiveEvaluator.__init__` signature from `(con, measure, adapter)` to `(con, measure_bundle, cql_library_path, adapter)`.
2. Stored `measure_bundle` and `cql_library_path` as instance attributes.
3. In `update()`, construct `MeasureEvaluator(self._con)` (no second arg) and call `evaluate(self._measure_bundle, self._cql_library_path, patient_ids=..., audit_mode=...)`.

**API contract referenced**:
- `MeasureEvaluator.__init__(conn, audit_or_strategy=AuditOrStrategy.TRUE_BRANCH, narrative_generator=None)` -- line 29 of `evaluator.py`
- `MeasureEvaluator.evaluate(measure_bundle, cql_library_path, ...)` -- line 52 of `evaluator.py`

### QA-002 (HIGH): Stale mock assertion

**File**: `/mnt/d/fhir4ds/fhir4ds/sources/tests/unit/test_delta.py`

**Root cause**: Test asserted `evaluate(patient_ids=changed_ids)` but the code now also passes `audit_mode='none'` as well as the two new positional args.

**Fix applied**:
1. Updated all `ReactiveEvaluator(...)` constructor calls in the test to include the new `cql_library_path` parameter: `"CBP"` -> `measure_bundle`, `"/dummy/lib.cql"` -> `cql_library_path`.
2. Updated the mock assertion to `assert_called_once_with("CBP", "/dummy/lib.cql", patient_ids=changed_ids, audit_mode="none")`.

### QA-003 (LOW): DEFERRED

IEEE 754 inherent limitation. Not fixable without major refactor. No action taken.

## Validation

| Suite | Result |
|---|---|
| `test_delta.py` (26 tests) | 26 passed |
| `test_evaluator.py` (26 tests) | 26 passed |
| Full suite (6624 tests) | 6624 passed, 116 skipped, 18 xfailed, 2 xpassed |

Zero failures across the board.

## Breaking Change Notice

`ReactiveEvaluator.__init__` signature changed:
- Old: `(con, measure: str, adapter, audit_mode="none")`
- New: `(con, measure_bundle: str|dict, cql_library_path: str, adapter, audit_mode="none")`

Any code constructing `ReactiveEvaluator` must be updated to pass `measure_bundle` and `cql_library_path` before `adapter`.
