# Engineer Handoff — Iteration 7 FIX Phase

## Issues

### QA7-001 (MEDIUM): RESOLVED — CQL `on or before/after <precision> of` returns NULL/wrong
**Status:** RESOLVED
**Root Cause:** The parser's `ON_OR_BEFORE`/`ON_OR_AFTER` token path emits `operator="on or before"` with precision nested inside the right operand as `BinaryExpression(operator="precision of", ...)`. The translator then calls `cqlSameOrBefore(full_left, truncated_right)` with mixed precisions, producing NULL.

**Fix:** Translator-level detection in `_operators.py` (lines 653-662). Before translating the right operand, check if it's a `BinaryExpression(operator="precision of")`. If so, extract the precision and promote it into the operator string (e.g., `"on or before" → "on or before month of"`), then pass the unwrapped inner expression as the right side. This routes to the precision-qualified `cqlSameOrBeforeP`/`cqlSameOrAfterP` UDFs.

**Why not parser fix:** An initial parser-level fix (adding `_try_parse_precision_of()` to the `ON_OR_BEFORE` branch) was correct for the reported bug but caused a DQM regression in CMS159 (100% → 53.7%). The CMS159 pattern `on or before day of end of "Measure Assessment Period"` changed routing from `cqlSameOrBefore(left, DATE_TRUNC_result)` to `cqlSameOrBeforeP(left, raw_right, 'day')`, which produced different results. The translator-level fix avoids this by operating on the AST before SQL translation.

**File:** `fhir4ds/cql/translator/expressions/_operators.py`

### QA7-002 (MEDIUM): RESOLVED — Count/Sum on flatten/union/except/intersect returns 1
**Status:** RESOLVED
**Root Cause:** `_unwrap_list_source()` only recognized `SQLArray` and `Distinct()` wrappers, not `flatten()`, `union`, `except`, or `intersect`. The aggregate handler also only checked `isinstance(source_sql, SQLArray)`.

**Fix:** Two changes in `_functions.py`:
1. Extended `_unwrap_list_source()` (line ~118) to detect `FunctionRef` (for flatten) and `BinaryExpression` with `union`/`except`/`intersect` operators.
2. Extended the Count/Sum handler (line ~708) to check `_is_list_returning_sql(source_sql)` in addition to `isinstance(source_sql, SQLArray)`.

**File:** `fhir4ds/cql/translator/expressions/_functions.py`

### QA7-003 (LOW): RESOLVED — MeasureParser.parse(None) throws AttributeError
**Status:** RESOLVED
**Fix:** Added `None` guard at top of `parse()` method. Raises `MeasureParseError("measure must be a non-null dict")` for `None` input.

**File:** `fhir4ds/dqm/parser.py`

## Conformance (unchanged from baseline)

| Suite | Passed | Total | Rate |
|-------|--------|-------|------|
| ViewDefinition | 134 | 134 | 100.0% |
| FHIRPath (R4) | 935 | 935 | 100.0% |
| CQL | 1706 | 1706 | 100.0% |
| DQM (QI Core 2025) | 42 | 46 | 91.3% |
| **OVERALL** | **2817** | **2821** | **99.9%** |

## Pre-existing Test Failures (not introduced by this iteration)
- `test_choice_type_columns.py::test_bp_profile_includes_component_columns` (ARCH-004)
