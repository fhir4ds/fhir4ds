# Code Review Findings — v0.0.4 Pressure Test

**Date**: 2026-05-05
**Scope**: Files changed in evolution loop + broader security scan

## HIGH Findings (2)

### REV-001: `_check_not_done_valueset` returns `None` but declared `-> bool`
- **File**: `fhir4ds/cql/duckdb/udf/valueset.py:385,406`
- **Issue**: Function signature says `-> bool` but returns `None` on JSON parse error. DuckDB UDF may interpret `None` as SQL NULL, causing three-valued logic divergence.
- **Fix**: Change return type to `bool | None` or revert to `False`.

### REV-002: SQL injection in `clear_valuesets`/`count_valueset_codes`
- **File**: `fhir4ds/cql/loader/fhir_loader.py:509-542`
- **Issue**: These methods accept `table_name` and pass it directly to `f"DELETE FROM {table_name}"` without `isidentifier()` validation. Other methods in the same class validate properly.
- **Fix**: Add `isidentifier()` check matching existing pattern in `__init__`.

## MEDIUM Findings (4)

### REV-003: String interpolation in SQL DDL (mitigated)
- **File**: `fhir4ds/dqm/tests/conformance/database.py:160-168`
- **Issue**: `scope_to_measure` uses string interpolation for CREATE VIEW. Mitigated by allowlist filter but should use parameterized queries where possible.

### REV-004: Single-quote-only escaping is DuckDB-specific
- **File**: `fhir4ds/cql/translator/fhirpath_builder.py:237-257`
- **Issue**: `_escape_fhirpath_string` only doubles single quotes. Correct for DuckDB but not portable.

### REV-005: Silent `except Exception: pass` in valueset loading
- **File**: `fhir4ds/dqm/tests/conformance/database.py:422-429,510-511`
- **Issue**: Malformed valueset files silently skipped. Makes debugging extremely difficult.

### REV-006: No NaN guard before arithmetic in summary_report
- **File**: `fhir4ds/dqm/evaluator.py:203-206`
- **Issue**: `_count_col` could produce unexpected results if DataFrame column contains mixed types.

## LOW Findings (6)

### REV-007: Redundant JSON parse in `_check_not_done_valueset`
- **File**: `fhir4ds/cql/duckdb/udf/valueset.py:404`

### REV-008: `result: Any` type hint too broad
- **File**: `fhir4ds/dqm/evaluator.py:168`

### REV-009: Late import inside except block
- **File**: `fhir4ds/dqm/evaluator.py:500-505`

### REV-010: Hardcoded absolute path
- **File**: `scripts/fix_input_bundles.py:16`

### REV-011: Unclosed file handle
- **File**: `fhir4ds/dqm/tests/conformance/loader.py:232`

### REV-012: End-of-month boundary edge case in YearsBetween/MonthsBetween
- **File**: `extensions/cql/src/cql_extension.cpp:333-349`

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 2 |
| MEDIUM | 4 |
| LOW | 6 |

No CRITICAL findings. The two HIGH findings have limited attack surface (internal API methods) but should be fixed before release.
