# Implementation Review: Retrieve Optimization with Precomputed Columns

**Reviewer:** Senior Developer
**Date:** 2026-02-25
**Implementation By:** Junior Developer
**Plan Reference:** `docs/IMPLEMENTATION_PLAN_RETRIEVE_OPTIMIZATION.md`

---

## Executive Summary

The junior developer has implemented **most** of the structural components correctly, but there are **3 critical architectural deviations** from the plan that violate core design decisions. These deviations introduce a hybrid text/AST approach that was explicitly rejected during design discussions.

**Overall Assessment:** ❌ **Does NOT align with planned architecture**

**Required Action:** Significant rework needed to align with pure AST approach

---

## Critical Issues

### 🔴 CRITICAL #1: `.sql` Property Not Removed

**Plan Requirement (Phase 1, Step 1.1):**
> "Remove .sql Property from SQLExpression"
> "IMPORTANT: SQL string generation happens ONLY via to_sql() call. No intermediate string storage - everything stays as AST until final generation."

**What Was Implemented:**
```python
# types.py lines 75-77
@property
def sql(self) -> str:
    """Get the SQL string representation (convenience property)."""
    return self.to_sql()
```

**Issue:** The `.sql` property was kept as a "convenience property" instead of being removed entirely. This violates the pure AST design decision.

**Impact:**
- 17+ places in the codebase still use `.sql` property
- Allows intermediate SQL string generation, defeating the pure AST approach
- Makes it easy for future code to bypass AST transformations

**Evidence:**
```bash
$ grep -rn "\.sql[^_]" cql-py/src/cql_py/translator/*.py | grep -v "to_sql" | wc -l
17
```

**Examples of remaining `.sql` usage:**
- `translator.py:312`: `ast.sql if hasattr(ast, 'sql')`
- `translator.py:370`: `expr.sql`
- `translator.py:607`: `sql = expr.sql`
- `expressions.py:2823`: `source.sql`

**Required Fix:**
1. Remove the `sql` property completely from `SQLExpression` (types.py lines 75-77)
2. Replace all 17+ `.sql` accesses with `.to_sql()` calls
3. Remove all `hasattr(x, 'sql')` checks

**Design Decision Reference:**
From `DESIGN_DECISIONS_RETRIEVE_OPTIMIZATION.md` Decision #1:
> "Pure AST Throughout: Remove .sql property from SQLExpression. No intermediate string storage."

---

### 🔴 CRITICAL #2: Placeholder Returns Text Marker Instead of Raising Error

**Plan Requirement (Phase 2, Step 2.1):**
```python
def to_sql(self) -> str:
    """
    Should never be called - placeholders must be resolved first.

    Raises:
        RuntimeError: Always, with helpful message
    """
    raise RuntimeError(
        f"Unresolved retrieve placeholder: {self.resource_type}"
        f"{f' with valueset {self.valueset}' if self.valueset else ''}\n"
        f"This is a bug - all placeholders must be resolved before SQL generation.\n"
        f"Key: {self.key}"
    )
```

**What Was Implemented:**
```python
# placeholder.py lines 62-75
def to_sql(self, parent_precedence: int = 0) -> str:
    """
    Generate a placeholder SQL string that can be resolved later.

    Returns a special placeholder marker that will be textually replaced
    during the resolution phase.
    """
    valueset_str = f"'{self.valueset}'" if self.valueset else "NULL"
    return f"__RETRIEVE_PLACEHOLDER__({self.resource_type}, {valueset_str})__"
```

**Issue:** Instead of raising an error, the placeholder generates a text marker like `__RETRIEVE_PLACEHOLDER__(Condition, 'Diabetes')__` that gets resolved later via regex string replacement.

**Impact:**
- Introduces text-level processing that defeats the pure AST approach
- If a placeholder isn't resolved, it silently produces invalid SQL instead of failing fast
- Makes debugging harder (invalid SQL at runtime vs. clear error at translation time)
- Violates "hard error for unresolved placeholders" design decision

**Required Fix:**
1. Make `RetrievePlaceholder.to_sql()` raise `RuntimeError` as specified in plan
2. Remove text-level placeholder resolution code:
   - Remove `resolve_text_placeholders()` function (placeholder.py:254-296)
   - Remove `find_all_text_placeholders()` function (placeholder.py:299-321)
3. Remove text-level resolution from `run_optimization_phases()` (retrieve_optimizer.py:219-230, 276-286)

**Design Decision Reference:**
From `DESIGN_DECISIONS_RETRIEVE_OPTIMIZATION.md` Decision #6:
> "Error Handling: Hard error for unresolved placeholders"
> User quote: "i think we need to cause an error so we fix the bugs"

---

### 🔴 CRITICAL #3: Hybrid Text/AST Resolution Approach

**Plan Requirement:**
Pure AST transformation throughout - placeholders resolved at AST level only.

**What Was Implemented:**
```python
# retrieve_optimizer.py lines 218-230
# Detect text-level placeholders by generating SQL and parsing it back
try:
    sql_str = sql_ast.to_sql()
    text_placeholders = find_all_text_placeholders(sql_str)
    for resource_type, valueset in text_placeholders:
        placeholder = RetrievePlaceholder(resource_type, valueset)
        phase1_result.placeholders.append(placeholder)
        stats.num_retrieves += 1
except Exception:
    pass

# Lines 276-286
# Convert resolved AST to SQLRaw after text resolution
from .types import SQLRaw
if isinstance(resolved_ast, SQLExpression):
    raw_sql = resolved_ast.to_sql()
    resolved_sql = resolve_text_placeholders(raw_sql, phase2_result.cte_name_map)
    resolved_ast = SQLRaw(raw_sql=resolved_sql)
```

**Issue:** The implementation uses a hybrid approach:
1. AST-level resolution first
2. Then generates SQL to find text-level placeholders
3. Then resolves text placeholders via regex
4. Then wraps result in `SQLRaw`

This defeats the entire purpose of the AST-first architecture.

**Root Cause Analysis:**

The junior developer likely encountered an issue where fluent functions were already inlining SQL strings during translation (before placeholders could be resolved). Rather than fixing the fluent function implementation, they created a workaround with text-level resolution.

**Impact:**
- Mixed AST/string processing defeats optimization opportunities
- `SQLRaw` nodes can't be transformed by later optimization passes
- Makes the code harder to understand and maintain
- Violates pure AST design decision

**Required Fix:**
1. Remove all text-level placeholder detection and resolution
2. Ensure fluent functions work with AST placeholders directly
3. Keep everything as AST until final SQL generation in Phase 3
4. Do NOT wrap resolved ASTs in `SQLRaw` - keep as structured AST types

**Why This Matters:**

From the design discussions, the user specifically wanted pure AST to enable:
- Property access optimization (Phase 3.5 in plan)
- JOIN optimization between CTEs
- Future query optimizations

Text-level processing blocks all of these.

---

## What Was Implemented Correctly

### ✅ File Structure

All required files created:
- `placeholder.py` ✓
- `property_scanner.py` ✓
- `cte_builder.py` ✓
- `retrieve_optimizer.py` ✓

### ✅ Data Structures

Correctly implemented:
- `RetrievePlaceholder` class with `key` property ✓
- `Phase1Result` dataclass ✓
- `Phase2Result` dataclass ✓
- `OptimizationStats` dataclass ✓
- `PropertyAccess` dataclass ✓

### ✅ Property Scanner (property_scanner.py)

**Fully Correct** - Matches plan exactly:
- `scan_ast_for_properties()` function ✓
- Recursive AST walker ✓
- Detects `fhirpath_*` function calls ✓
- Returns `Set[PropertyAccess]` ✓
- Handles all SQL AST node types ✓

**No issues found.**

### ✅ CTE Builder (cte_builder.py)

**Fully Correct** - Matches plan exactly:
- `build_retrieve_cte()` function ✓
- `property_to_column_name()` mapping ✓
- `infer_fhirpath_function()` logic ✓
- Returns `(cte_name, cte_ast, column_info_map)` tuple ✓
- Builds `SQLSelect` with precomputed columns ✓
- Includes base columns (patient_id, resource) ✓

**No issues found.**

### ✅ Retrieve Translation (expressions.py)

**Correct** - Returns placeholders as specified:
```python
# expressions.py lines 2923-2977
def _translate_retrieve(self, node, ...) -> SQLExpression:
    """Returns a placeholder that will be resolved to a CTE reference."""
    ...
    return RetrievePlaceholder(
        resource_type=resource_type,
        valueset=valueset
    )
```

**No issues found.**

### ✅ Translator Integration (translator.py)

**Correct** - Calls `run_optimization_phases()`:
```python
# translator.py lines 463-465
resolved_asts, phase1_result, phase2_result, opt_stats = run_optimization_phases(
    library, self._context, self
)
```

**Correct** - Adds retrieve CTEs to SQL:
```python
# translator.py lines 507-512
for cte_name, cte_ast in phase2_result.ctes.items():
    cte_sql = cte_ast.to_sql()
    quoted_name = f'"{cte_name}"'
    cte_parts.append(f'{quoted_name} AS (\n  {cte_sql}\n)')
```

**Issue here:** Some places still use `.sql` property (see Critical #1)

### ✅ Placeholder Resolution (placeholder.py)

**Partially Correct** - AST-level resolution is good:
- `resolve_placeholders()` function correctly walks AST ✓
- Replaces `RetrievePlaceholder` with `SQLIdentifier` ✓
- Handles all SQL node types ✓
- Raises `UnresolvedPlaceholderError` for missing CTEs ✓

**Issues:** Text-level resolution should be removed (see Critical #2, #3)

### ✅ Three-Phase Orchestration (retrieve_optimizer.py)

**Correct Structure:**
- Phase 1: Translate + Scan ✓
- Phase 2: Build CTEs ✓
- Phase 3: Resolve placeholders ✓
- Returns `(resolved_asts, phase1, phase2, stats)` ✓

**Issues:** Text-level resolution mixing (see Critical #3)

---

## Minor Issues (Non-Critical)

### ⚠️ Issue #4: Missing `to_sql()` Implementation Consistency

**Observation:** `RetrievePlaceholder` implements `to_sql(parent_precedence: int = 0)` with the precedence parameter, but doesn't actually use it.

**Fix:** Not critical, but could be simplified to match the plan's signature: `def to_sql(self) -> str:`

### ⚠️ Issue #5: Extra Functions Not in Plan

**Observation:** `placeholder.py` includes extra functions not in the plan:
- `resolve_text_placeholders()` - should be removed (part of Critical #3)
- `find_all_text_placeholders()` - should be removed (part of Critical #3)

**Fix:** Remove as part of Critical #3 fix.

---

## Testing Status

**Unable to Verify** - Need to run tests after critical fixes.

The plan includes comprehensive testing strategy (Section 10), but implementation deviations mean tests would pass for wrong reasons (text-level workarounds).

**Required Testing After Fixes:**
1. Unit tests for placeholder raising error
2. Unit tests for property scanner
3. Unit tests for CTE builder
4. Integration test with simple CQL
5. Integration test with CMS165 measure
6. Verify no `.sql` property accesses remain

---

## Compliance Matrix

| Plan Requirement | Status | Notes |
|-----------------|--------|-------|
| **Phase 1: Setup** | | |
| Remove `.sql` property | ❌ FAIL | Kept as convenience property |
| Update all `.sql` access to `.to_sql()` | ❌ FAIL | 17+ places still use `.sql` |
| Create new module files | ✅ PASS | All files created |
| **Phase 2: Placeholder** | | |
| RetrievePlaceholder class | ⚠️ PARTIAL | Exists but wrong `to_sql()` |
| `to_sql()` raises error | ❌ FAIL | Returns text marker instead |
| Placeholder unit tests | ❓ UNKNOWN | Need to check |
| Update `_translate_retrieve` | ✅ PASS | Returns placeholders |
| **Phase 3: Scanner** | | |
| `scan_ast_for_properties()` | ✅ PASS | Correct implementation |
| Handle all AST node types | ✅ PASS | Comprehensive walker |
| Return `Set[PropertyAccess]` | ✅ PASS | Correct return type |
| **Phase 4: CTE Builder** | | |
| `build_retrieve_cte()` | ✅ PASS | Correct implementation |
| `property_to_column_name()` | ✅ PASS | Good mappings |
| Return tuple format | ✅ PASS | Correct |
| **Phase 5: Resolution** | | |
| `resolve_placeholders()` AST walker | ✅ PASS | Correct |
| Handle all node types | ✅ PASS | Comprehensive |
| Raise error for unresolved | ⚠️ PARTIAL | Only in AST, not text |
| **Phase 6: Integration** | | |
| Phase result dataclasses | ✅ PASS | All correct |
| `run_optimization_phases()` | ⚠️ PARTIAL | Structure good, text mixing bad |
| Update `translate_library_to_population_sql` | ⚠️ PARTIAL | Integration present, uses `.sql` |
| **Design Decisions** | | |
| Pure AST throughout | ❌ FAIL | Hybrid text/AST approach |
| Hard error for unresolved | ❌ FAIL | Text markers allowed |
| No regex or string manipulation | ❌ FAIL | Text-level regex resolution |

**Overall Compliance: ~60% (Structural: Good, Architectural: Failed)**

---

## Root Cause Analysis

### Why Did This Happen?

The junior developer likely encountered an issue where existing code (particularly fluent function inlining) was already generating SQL strings before placeholders could be resolved. Rather than fixing the root cause (ensuring fluent functions stay as AST), they created a workaround:

1. Let placeholders generate text markers
2. Add regex-based text-level resolution
3. Wrap results in `SQLRaw`

This is understandable from a "make it work" perspective, but it violates the architectural principles.

### What Should Have Happened?

When encountering SQL strings with placeholders:
1. Identify where SQL is being generated too early
2. Modify that code to keep AST structure
3. Ensure placeholders stay as AST nodes until Phase 3
4. Fail fast with clear error if placeholder reaches `to_sql()`

---

## Recommended Action Plan

### Immediate Actions (Required Before Merge)

1. **Fix Critical #1: Remove `.sql` Property**
   - Delete lines 75-77 from `types.py`
   - Find and replace all `.sql` with `.to_sql()` (17+ occurrences)
   - Remove all `hasattr(x, 'sql')` checks
   - Run tests to find any remaining issues

2. **Fix Critical #2: Placeholder Error Behavior**
   - Replace `RetrievePlaceholder.to_sql()` with version that raises `RuntimeError`
   - Use exact error message from plan
   - Remove text marker generation

3. **Fix Critical #3: Remove Text-Level Resolution**
   - Delete `resolve_text_placeholders()` function
   - Delete `find_all_text_placeholders()` function
   - Remove text-level detection from `run_optimization_phases()` (lines 218-230)
   - Remove `SQLRaw` wrapping from Phase 3 (lines 276-286)
   - Return resolved AST directly, not wrapped in `SQLRaw`

4. **Verify Fluent Functions Work with Placeholders**
   - Check that fluent function inlining preserves AST structure
   - If not, fix fluent function implementation
   - Ensure no premature SQL generation

5. **Run Full Test Suite**
   - All unit tests should pass
   - Integration tests should pass
   - Manually test with CMS165 measure

### Validation Checklist

After fixes, verify:
- [ ] No `.sql` property exists in `SQLExpression`
- [ ] All code uses `.to_sql()` instead of `.sql`
- [ ] `RetrievePlaceholder.to_sql()` raises `RuntimeError`
- [ ] No text-level placeholder resolution code exists
- [ ] Phase 3 returns AST, not `SQLRaw`
- [ ] All unit tests pass
- [ ] CMS165 measure translates successfully
- [ ] Generated SQL has retrieve CTEs with precomputed columns
- [ ] No `__RETRIEVE_PLACEHOLDER__` markers in generated SQL

---

## Detailed File-by-File Assessment

### types.py
- ❌ Keep `.sql` property → **MUST REMOVE**
- ✅ All AST types have `to_sql()` methods

### placeholder.py
- ⚠️ `RetrievePlaceholder.to_sql()` returns text marker → **MUST RAISE ERROR**
- ✅ `resolve_placeholders()` function is correct
- ❌ `resolve_text_placeholders()` function → **MUST REMOVE**
- ❌ `find_all_text_placeholders()` function → **MUST REMOVE**
- ✅ `find_all_placeholders()` function is correct

### property_scanner.py
- ✅ **NO ISSUES** - Fully correct implementation

### cte_builder.py
- ✅ **NO ISSUES** - Fully correct implementation

### retrieve_optimizer.py
- ✅ Data structures correct
- ✅ Three-phase structure correct
- ❌ Lines 218-230: Text placeholder detection → **MUST REMOVE**
- ❌ Lines 276-286: SQLRaw wrapping and text resolution → **MUST REMOVE**
- ⚠️ Phase 3 should return resolved AST directly

### expressions.py
- ✅ `_translate_retrieve()` correctly returns placeholders
- ❌ Line 2823: Uses `.sql` property → **MUST CHANGE TO `.to_sql()`**

### translator.py
- ✅ Calls `run_optimization_phases()` correctly
- ✅ Adds retrieve CTEs to SQL correctly
- ❌ Multiple `.sql` property accesses → **MUST CHANGE TO `.to_sql()`**
  - Line 312
  - Line 370
  - Line 607
  - Line 2267
  - Line 2532
  - Line 2552
  - Line 2566

---

## Conclusion

The junior developer has successfully implemented the **structural components** of the optimization system (data structures, file organization, individual functions). However, they have introduced **critical architectural deviations** that violate the core design decisions.

The implementation uses a hybrid text/AST approach that was explicitly rejected during design. This defeats the purpose of the pure AST architecture and blocks future optimizations.

**Recommendation:** **DO NOT MERGE** until all three critical issues are fixed.

The fixes are straightforward:
1. Remove the convenience `.sql` property
2. Make placeholders error instead of generating text markers
3. Remove all text-level resolution code

These changes will align the implementation with the original plan and enable the full benefits of the pure AST approach.

---

## Questions for Junior Developer

1. What issue did you encounter that led to the text-level placeholder approach?
2. Did you find SQL strings being generated before placeholders could be resolved?
3. Are there specific fluent functions that need AST fixes?
4. Did you run into any test failures that suggested the pure AST approach wouldn't work?

Understanding the root cause will help us ensure the fixes address the real underlying issues.
