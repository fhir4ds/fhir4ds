# Fluent Function AST Implementation - Status Report

## What Was Implemented

### Phase 1: AST Types ✅
Added missing AST types to `types.py`:
- `SQLList` - for list literals like `('confirmed', 'provisional')`
- `SQLLambda` - for lambda expressions like `r -> condition`

### Phase 2: AST Builders ✅
Added AST builders to `fluent_functions.py`:
- `_extract_cte_name()` - helper to extract CTE name from resource expression
- `_build_template_ast()` - dispatcher for AST builders
- `_build_verified_ast()` - builds AST for `.verified()` function
- `_build_prevalence_interval_ast()` - builds AST for `.prevalenceInterval()` function
- `_build_latest_ast()` - stub for `.latest()` function (not fully implemented)

### Phase 3: Template Flow Modification ✅
Modified `_inline_function_body()` to try AST first, then fall back to string templates.

## Current State

### What Works
1. **Fluent functions return AST** - `.verified()` and `.prevalenceInterval()` now return structured AST (SQLFunctionCall, SQLCase, etc.) instead of raw SQL strings
2. **AST types are complete** - SQLList and SQLLambda work correctly
3. **Fallback mechanism works** - Functions without AST builders still use string templates

### What Doesn't Work
1. **No JOINs generated** - Still 0 JOINs in CTEs, 649 correlated subqueries in CMS165
2. **Retrieves are inline SQL, not CTE references** - Even though CTEs exist for retrieves, fluent functions operate on inline SQL queries
3. **Definition cross-references not working** - Found bug: `define_expression()` stores in wrong dict, definitions can't find each other

## Root Cause Analysis

### The Architectural Issue

The current translation flow is **bottom-up**:
1. Translate retrieve → inline SQL (correlated subquery)
2. Apply fluent function → more SQL wrapping the subquery
3. Create definition CTE → wrap the entire SQL

But optimization requires **top-down**:
1. Identify all retrieves used across definitions
2. Create CTEs for retrieves (with precomputed columns)
3. Translate expressions using CTE *references* (not inline SQL)
4. Add JOINs between CTEs

### Why Fluent Function AST Isn't Enough

When `.verified()` is called on `[Condition: "Essential Hypertension"]`:
1. The retrieve is translated to: `(SELECT resource FROM resources WHERE ...)`
2. `.verified()` receives this SQLSubquery (not a CTE reference)
3. `.verified()` returns: `list_filter((SELECT ...), r -> ...)`
4. No CTE reference exists to join to

Even though `.verified()` returns AST, the retrieve is **inline SQL**, so there's no CTE to join against.

### The Definition Lookup Bug

Found critical bug in `translator.py` line 308:
```python
# WRONG - stores in expression_definitions dict
self._context.define_expression(statement.name, result)
```

Should be:
```python
# CORRECT - stores in definitions dict
self._context.add_definition(statement.name, result.sql)
```

This breaks definition cross-references like `"Denominator": "Initial Population"` because `get_definition()` looks in `definitions` dict, not `expression_definitions`.

**Fix applied** but definition cross-references still not fully working because of translate flow issues.

## What Would Be Needed for Full Optimization

### Option 1: Two-Phase Retrieve Translation (RECOMMENDED)

**Phase 1: Collect Retrieves**
- Scan all definitions for retrieve expressions
- Extract retrieves as CTEs with precomputed columns
- Assign unique names: `"Condition: Essential Hypertension"`

**Phase 2: Translate with CTE References**
- When translating retrieve, return CTE reference (just name), not inline SQL
- Fluent functions operate on CTE references
- Can access precomputed columns via column registry
- JOIN generation works because references are CTE names

**Files to modify**:
- `expressions.py` - `_translate_retrieve()` needs two modes: collect vs reference
- `translator.py` - add retrieve collection phase before definition translation
- `fluent_functions.py` - optimize templates when resource is CTE reference

### Option 2: Post-Translation Optimization (COMPLEX)

After generating SQL with inline retrieves:
- Parse SQL to find repeated retrieve patterns
- Extract as CTEs
- Rewrite references to use CTE names
- Add JOINs where possible

**Problems**:
- Requires SQL parsing/rewriting
- Against AST-first philosophy
- Fragile and error-prone

### Option 3: Incremental Fix (PARTIAL SOLUTION)

Focus on definition cross-references first:
1. Fix definition lookup bug completely
2. Get definition-to-definition JOINs working ("Denominator" → "Initial Population")
3. Leave retrieve optimization for later

**Benefit**: Shows infrastructure works
**Limitation**: Won't help with fluent function patterns in CMS165

## Recommendation

Given the scope of changes needed, I recommend:

**Short-term**: Fix definition cross-reference JOINs (Option 3)
- Complete the bug fix for definition registration
- Test definition-to-definition references
- Verify JOINs work for simple patterns
- Document that fluent function optimization requires Phase 1 changes

**Medium-term**: Implement two-phase retrieve translation (Option 1)
- Design the retrieve collection phase
- Modify retrieve translator to return CTE references
- Test with CMS165
- Measure performance improvement

## Test Results

### Before Implementation
- Definitions using AST path: 13/42
- JOINs generated: 13
- Correlated subqueries: 579

### After Fluent Function AST
- Fluent functions return AST: ✅
- Definitions using AST path: Still issues
- JOINs generated: 0 (blocked by architecture)
- Correlated subqueries: 649 (worse!)

The increase in subqueries suggests the AST is being wrapped in additional layers but not optimized.

## Next Steps

1. **Immediate**: Complete definition lookup fix and test cross-references
2. **Short-term**: Design two-phase retrieve translation
3. **Medium-term**: Implement Option 1 for full optimization
4. **Long-term**: Measure performance impact on real data

## Files Modified

- `cql-py/src/cql_py/translator/types.py` - Added SQLList, SQLLambda
- `cql-py/src/cql_py/translator/fluent_functions.py` - Added AST builders
- `cql-py/src/cql_py/translator/translator.py` - Fixed definition registration bug

## Conclusion

The fluent function AST implementation is **technically correct** but **architecturally blocked**. The AST builders work, but the optimization requires fundamental changes to how retrieves are handled during translation. The current bottom-up translation flow needs to be replaced with a top-down approach that extracts retrieves as CTEs before applying fluent functions.
