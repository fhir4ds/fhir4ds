# Engineer Handoff — Phase 2 FIX (ARCH-002, ARCH-004, ARCH-009)

## Summary

Resolved 3 OPEN MEDIUM architectural issues. All changes are logging/test-only — no behavioral changes to library code.

## Issues

### ARCH-002 (MEDIUM): RESOLVED — Profile registry silent fallback
**Problem:** `_resolve_profile_registry()` in cte_builder.py fell back to default registry silently when context.profile_registry was None.

**Fix:** The function already had a `logger.warning()` call from prior remediation. Cleaned up redundant inline `import logging` to use the existing module-level `logger` variable. The fallback is correct defensive behavior; the issue was about observability.

**Files changed:**
- `fhir4ds/cql/translator/cte_builder.py` — 1 line: use module-level logger instead of inline import

### ARCH-004 (MEDIUM): RESOLVED — Stale BP profile test
**Problem:** `test_bp_profile_includes_component_columns` expected eager systolic/diastolic columns, but implementation uses demand-driven generation. Conformance tests pass 100%.

**Fix:** Updated 2 tests to match actual (correct) demand-driven behavior:
1. `test_bp_profile_includes_component_columns` — Now asserts standard columns (effective_date, status) are present and component columns (systolic_value, diastolic_value) are NOT eagerly generated.
2. `test_bp_column_sql_uses_where_and_number` → renamed to `test_bp_profile_sql_includes_standard_observation_columns` — Verifies SQL output contains fhirpath_text and effective date references.

**Files changed:**
- `fhir4ds/cql/tests/unit/test_choice_type_columns.py` — Updated 2 test methods

### ARCH-009 (MEDIUM): RESOLVED — UDF broad exception catches
**Problem:** Multiple `except Exception: return None` / `except Exception: pass` patterns in CQL DuckDB UDF code swallowed unexpected errors silently.

**Fix:** Added `_logger.debug("Unexpected error in UDF ...: %s", e)` to all broad except blocks:
- `interval.py` — 10 sites (intervalWidth, intervalIntersect, intervalUnion, intervalExcept, expand)
- `math.py` — 3 sites (_step_value quantity/numeric parse, cqlPrecision)
- `quantity.py` — 1 site (toConcept)

All files already had `_logger = logging.getLogger(__name__)` at module level. Catches remain broad to preserve SQL UDF null-return semantics.

**Files changed:**
- `fhir4ds/cql/duckdb/udf/interval.py`
- `fhir4ds/cql/duckdb/udf/math.py`
- `fhir4ds/cql/duckdb/udf/quantity.py`

## Test Results

- `test_choice_type_columns.py`: **6/6 passed** (was 4/6 before fix)
- Smoke test: CQL translate ✅, FHIRPath ✅
- Build: `hatch build` succeeded
- No conformance regression (logging-only changes)

## Open ARCH Issues (remaining)

| ID | Severity | Summary |
|----|----------|---------|
| ARCH-001 | MEDIUM | Strategy 2 body_sql templates (KNOWN_DEBT, blocked Task C4) |
| ARCH-005 | LOW | Broad exception in fhirpath_is_valid |
| ARCH-006 | LOW | ViewDef module-level array load |
| ARCH-007 | LOW | ViewDef string-based SQL generation |
| ARCH-008 | LOW | Context profile registry warning fallback |
