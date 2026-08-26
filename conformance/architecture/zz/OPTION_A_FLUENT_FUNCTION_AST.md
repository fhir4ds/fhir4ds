# Option A: Making Fluent Functions Return AST

## Executive Summary

**Status**: JOIN optimization is partially working (13 JOINs generated), but complex definitions with fluent functions bypass optimization.

**Problem**: Fluent functions (`.verified()`, `.prevalenceInterval()`) return SQL strings instead of AST, causing downstream definitions to use STRING path instead of AST path, which prevents JOIN generation and precomputed column usage.

**Solution**: Refactor fluent function translation to return structured AST instead of SQL strings, enabling full optimization for all definition types.

---

## Background: Current State

### What's Working ✅

1. **JOIN Generation (13 JOINs)**
   - Simple definitions that reference other definitions now use LEFT JOINs
   - Example: `"Numerator" AS (SELECT ... FROM _patients LEFT JOIN "Has Systolic..." AS j1 ...)`
   - Architecture: Two-pass translation with query_builder tracking

2. **Column Registration (29 columns)**
   - Retrieve CTEs precompute common properties
   - Columns registered in ColumnRegistry with FHIRPath mappings
   - Example: `onset_date` → `onsetDateTime`, `verification_status` → `verificationStatus.coding.code`

3. **AST-Based Optimization for Simple Definitions**
   - Definitions with boolean expressions, EXISTS checks work correctly
   - `_wrap_expression_in_select()` wraps non-SELECT AST
   - `_add_joins_from_tracked_refs()` generates JOIN clauses

### What's Not Working ❌

**Complex Definitions with Fluent Functions Use STRING Path**

Example from CMS165:
```cql
define "Essential Hypertension Diagnosis":
  ( [Condition: "Essential Hypertension"] ).verified() ) Hypertension
  where Hypertension.prevalenceInterval() overlaps ...
```

Current SQL (WRONG - uses correlated subqueries):
```sql
"Essential Hypertension Diagnosis" AS (
  SELECT p.patient_id
  FROM _patients p
  WHERE CASE WHEN fhirpath_text(
    (SELECT sq.resource FROM "Condition: Essential Hypertension" sq WHERE sq.patient_ref = p.patient_id),
    'verificationStatus.coding.code'
  ) IN ('confirmed', 'provisional') THEN ...
)
```

Expected SQL (RIGHT - uses JOINs):
```sql
"Essential Hypertension Diagnosis" AS (
  SELECT p.patient_id
  FROM _patients p
  LEFT JOIN "Condition: Essential Hypertension" AS j1 ON j1.patient_id = p.patient_id
  WHERE j1.verification_status IN ('confirmed', 'provisional')
    AND intervalFromBounds(j1.onset_date, j1.abatement_date, ...) OVERLAPS ...
)
```

---

## Root Cause Analysis

### The Circular Dependency

1. **To use precomputed columns** → Need JOINs to access upstream CTE columns
2. **To generate JOINs** → Definitions must use AST path (`_build_cte_from_ast()`)
3. **To use AST path** → Expressions must return `SQLSelect` AST objects
4. **But fluent functions** → Return SQL strings (bypassing AST optimization)

### Where Fluent Functions Become Strings

**File**: `cql-py/src/cql_py/translator/fluent_functions.py`

**Line 789-831**: `_inline_fluent_function_call()`
```python
def _inline_fluent_function_call(self, call, is_where_clause=False):
    func_def = self.registry.get_function(call.function_name)

    # Translate the resource expression
    resource_expr = self.expr_translator.translate(call.source)

    # Substitute into template
    result = self._substitute_template(
        func_def.template,
        resource_expr,
        call.arguments,
        func_def,
        is_where_clause
    )

    return result  # Returns SQLExpression (string wrapper)
```

**Line 831-900**: `_substitute_template()`
```python
def _substitute_template(self, template, resource_expr, args, func_def, is_where_clause):
    # ... builds SQL string from template ...

    result = template.format(
        resource=resource_str,
        **arg_map
    )

    return SQLExpression(result)  # Wraps SQL string
```

**The Problem**:
- Templates like `"list_filter({resource}, r -> fhirpath_text(r, 'verificationStatus.coding.code') IN ('confirmed', 'provisional'))"` are substituted as strings
- `SQLExpression` is just a string wrapper, not structured AST
- When `translate_definition()` receives `SQLExpression(sql_string)`, it can't use AST optimization

### Why This Matters for CMS165

**CMS165 has 42 definitions**:
- **Simple definitions** (13): Boolean checks, EXISTS → Use JOINs ✅
- **Complex definitions** (29): Use fluent functions → Use STRING path ❌

Impact:
- 13 JOINs generated (simple definitions)
- 579 correlated subqueries (complex definitions + FHIRPath calls)
- 29 precomputed columns unused

Potential improvement with Option A:
- 40+ JOINs generated (most definitions)
- 480-520 correlated subqueries (only resource retrieves + complex FHIRPath)
- 29 precomputed columns heavily used

---

## Option A Implementation Plan

### Phase 1: Create AST Builder for Fluent Function Templates

**Goal**: Build structured AST instead of SQL strings

**File**: `cql-py/src/cql_py/translator/fluent_functions.py`

**New method**: `_build_template_ast()`

```python
def _build_template_ast(
    self,
    func_def: FunctionDefinition,
    resource_expr: SQLExpression,
    args: List[SQLExpression],
    context: SQLTranslationContext,
) -> SQLExpression:
    """
    Build structured AST for fluent function templates.

    Returns AST instead of SQL string, enabling JOIN optimization
    and precomputed column usage.
    """
    from .types import (
        SQLFunctionCall, SQLBinaryOp, SQLQualifiedIdentifier,
        SQLIdentifier, SQLLiteral, SQLList, SQLLambda
    )

    # Dispatch based on function name
    if func_def.name == "verified":
        return self._build_verified_ast(resource_expr, context)
    elif func_def.name == "prevalenceInterval":
        return self._build_prevalence_interval_ast(resource_expr, args, context)
    elif func_def.name == "latest":
        return self._build_latest_ast(resource_expr, args, context)
    else:
        # Fall back to string template for unsupported functions
        return self._substitute_template_fallback(func_def.template, resource_expr, args)
```

### Phase 2: Implement AST Builders for Key Fluent Functions

#### 2.1: `.verified()` Function

**Current template**:
```python
"list_filter({resource}, r -> fhirpath_text(r, 'verificationStatus.coding.code') IN ('confirmed', 'provisional'))"
```

**New AST builder**:
```python
def _build_verified_ast(
    self,
    resource_expr: SQLExpression,
    context: SQLTranslationContext,
) -> SQLExpression:
    """
    Build AST for .verified() - filters resources by verification status.

    Optimization: If resource_expr references a CTE with precomputed
    verification_status column, use column instead of FHIRPath.
    """
    from .types import SQLFunctionCall, SQLBinaryOp, SQLIdentifier, SQLList, SQLLiteral

    # Try to extract CTE name for column optimization
    cte_name = self._extract_cte_name(resource_expr)

    # Check if CTE has precomputed verification_status column
    if cte_name and context.column_registry:
        col_info = context.column_registry.lookup(cte_name, "verificationStatus.coding.code")
        if col_info:
            # OPTIMIZATION: Use precomputed column via JOIN
            # Build: list_filter({resource}, r -> r.verification_status IN ('confirmed', 'provisional'))
            return SQLFunctionCall(
                name="list_filter",
                args=[
                    resource_expr,
                    SQLLambda(
                        param="r",
                        body=SQLBinaryOp(
                            operator="IN",
                            left=SQLQualifiedIdentifier(parts=["r", col_info.name]),
                            right=SQLList([
                                SQLLiteral("'confirmed'"),
                                SQLLiteral("'provisional'")
                            ])
                        )
                    )
                ]
            )

    # FALLBACK: Use FHIRPath call
    # Build: list_filter({resource}, r -> fhirpath_text(r, 'verificationStatus.coding.code') IN (...))
    return SQLFunctionCall(
        name="list_filter",
        args=[
            resource_expr,
            SQLLambda(
                param="r",
                body=SQLBinaryOp(
                    operator="IN",
                    left=SQLFunctionCall(
                        name="fhirpath_text",
                        args=[
                            SQLIdentifier(name="r"),
                            SQLLiteral("'verificationStatus.coding.code'")
                        ]
                    ),
                    right=SQLList([
                        SQLLiteral("'confirmed'"),
                        SQLLiteral("'provisional'")
                    ])
                )
            )
        ]
    )
```

#### 2.2: `.prevalenceInterval()` Function

**Current template**:
```python
"intervalFromBounds(fhirpath_date({resource}, 'onsetDateTime'), fhirpath_date({resource}, 'abatementDateTime'), true, true)"
```

**New AST builder**:
```python
def _build_prevalence_interval_ast(
    self,
    resource_expr: SQLExpression,
    args: List[SQLExpression],
    context: SQLTranslationContext,
) -> SQLExpression:
    """
    Build AST for .prevalenceInterval() - extracts onset/abatement interval.

    Optimization: Use precomputed onset_date and abatement_date columns if available.
    """
    from .types import SQLFunctionCall, SQLIdentifier, SQLQualifiedIdentifier, SQLLiteral

    cte_name = self._extract_cte_name(resource_expr)

    # Check for precomputed date columns
    if cte_name and context.column_registry:
        onset_col = context.column_registry.lookup(cte_name, "onsetDateTime")
        abatement_col = context.column_registry.lookup(cte_name, "abatementDateTime")

        if onset_col and abatement_col:
            # OPTIMIZATION: Use precomputed columns
            return SQLFunctionCall(
                name="intervalFromBounds",
                args=[
                    SQLQualifiedIdentifier(parts=["r", onset_col.name]),
                    SQLQualifiedIdentifier(parts=["r", abatement_col.name]),
                    SQLLiteral("true"),
                    SQLLiteral("true")
                ]
            )

    # FALLBACK: Use FHIRPath calls
    return SQLFunctionCall(
        name="intervalFromBounds",
        args=[
            SQLFunctionCall(
                name="fhirpath_date",
                args=[
                    resource_expr,
                    SQLLiteral("'onsetDateTime'")
                ]
            ),
            SQLFunctionCall(
                name="fhirpath_date",
                args=[
                    resource_expr,
                    SQLLiteral("'abatementDateTime'")
                ]
            ),
            SQLLiteral("true"),
            SQLLiteral("true")
        ]
    )
```

#### 2.3: `.latest()` Function

**Current template**:
```python
"list_latest({resource}, r -> fhirpath_date(r, '{property}'))"
```

**New AST builder**:
```python
def _build_latest_ast(
    self,
    resource_expr: SQLExpression,
    args: List[SQLExpression],  # [property_name]
    context: SQLTranslationContext,
) -> SQLExpression:
    """
    Build AST for .latest() - returns most recent resource by property.

    Optimization: Use precomputed date columns if available.
    """
    from .types import SQLFunctionCall, SQLIdentifier, SQLQualifiedIdentifier, SQLLiteral, SQLLambda

    # Extract property name from args
    property_name = args[0] if args else "effectiveDateTime"
    if isinstance(property_name, SQLLiteral):
        property_name = property_name.value.strip("'\"")

    cte_name = self._extract_cte_name(resource_expr)

    # Check for precomputed column
    if cte_name and context.column_registry:
        col_info = context.column_registry.lookup(cte_name, property_name)
        if col_info:
            # OPTIMIZATION: Use precomputed column
            return SQLFunctionCall(
                name="list_latest",
                args=[
                    resource_expr,
                    SQLLambda(
                        param="r",
                        body=SQLQualifiedIdentifier(parts=["r", col_info.name])
                    )
                ]
            )

    # FALLBACK: Use FHIRPath
    return SQLFunctionCall(
        name="list_latest",
        args=[
            resource_expr,
            SQLLambda(
                param="r",
                body=SQLFunctionCall(
                    name="fhirpath_date",
                    args=[
                        SQLIdentifier(name="r"),
                        SQLLiteral(f"'{property_name}'")
                    ]
                )
            )
        ]
    )
```

#### 2.4: Helper Method - Extract CTE Name

```python
def _extract_cte_name(self, resource_expr: SQLExpression) -> Optional[str]:
    """
    Extract CTE name from a resource expression for column optimization.

    Returns:
        CTE name if extractable, None otherwise
    """
    from .types import SQLIdentifier, SQLQualifiedIdentifier, SQLSubquery

    # Direct identifier: "Condition: Essential Hypertension"
    if isinstance(resource_expr, SQLIdentifier):
        name = resource_expr.name
        return name.strip('"') if name.startswith('"') else name

    # Qualified identifier: cte.column
    if isinstance(resource_expr, SQLQualifiedIdentifier):
        name = resource_expr.parts[0] if resource_expr.parts else None
        return name.strip('"') if name and name.startswith('"') else name

    # Subquery: (SELECT ... FROM cte)
    if isinstance(resource_expr, SQLSubquery):
        select = resource_expr.query
        if hasattr(select, 'from_clause') and isinstance(select.from_clause, SQLIdentifier):
            name = select.from_clause.name
            return name.strip('"') if name.startswith('"') else name

    return None
```

### Phase 3: Modify Template Substitution Flow

**File**: `cql-py/src/cql_py/translator/fluent_functions.py`

**Line 789**: Update `_inline_fluent_function_call()`

```python
def _inline_fluent_function_call(self, call, is_where_clause=False):
    """Inline a fluent function call by substituting its template."""
    func_def = self.registry.get_function(call.function_name)

    if not func_def:
        raise ValueError(f"Unknown fluent function: {call.function_name}")

    # Translate the resource expression (returns AST)
    resource_expr = self.expr_translator.translate(call.source)

    # Translate arguments (returns list of AST)
    args = [self.expr_translator.translate(arg) for arg in call.arguments]

    # NEW: Try to build AST instead of string template
    try:
        result = self._build_template_ast(func_def, resource_expr, args, self.context)
        return result
    except NotImplementedError:
        # FALLBACK: Use string template for unsupported functions
        return self._substitute_template(
            func_def.template,
            resource_expr,
            args,
            func_def,
            is_where_clause
        )
```

### Phase 4: Handle AST Types in SQLExpression

**Current issue**: AST types need consistent `to_sql()` methods

**File**: `cql-py/src/cql_py/translator/types.py`

**Verify/Add**:
```python
@dataclass
class SQLLambda(SQLExpression):
    """Lambda expression for list operations."""
    param: str
    body: SQLExpression

    def to_sql(self) -> str:
        return f"{self.param} -> {self.body.to_sql()}"

@dataclass
class SQLList(SQLExpression):
    """List literal."""
    items: List[SQLExpression]

    def to_sql(self) -> str:
        items_sql = ", ".join(item.to_sql() for item in self.items)
        return f"({items_sql})"
```

### Phase 5: Ensure Query Builder Tracks Through Fluent Functions

**File**: `cql-py/src/cql_py/translator/expressions.py`

**Current state**: Query builder tracking happens in `_translate_identifier()`

**Required**: Ensure fluent function AST preserves CTE references for tracking

Example flow:
```
[Condition: "Essential Hypertension"]  -> track_cte_reference()
  .verified()                          -> AST preserves reference
  .prevalenceInterval()                -> AST preserves reference
```

**Verification**: Check that `track_cte_reference()` is called when resource_expr is translated, before fluent function processing.

### Phase 6: Test and Validate

#### Test 1: Simple Fluent Function
```cql
define "Verified Hypertension":
  [Condition: "Essential Hypertension"].verified()
```

Expected:
- Uses AST path (not STRING)
- Generates LEFT JOIN to "Condition: Essential Hypertension"
- Uses `j1.verification_status` column

#### Test 2: Chained Fluent Functions
```cql
define "Essential Hypertension Diagnosis":
  ( [Condition: "Essential Hypertension"] ).verified() ) Hypertension
  where Hypertension.prevalenceInterval() overlaps ...
```

Expected:
- Uses AST path
- Generates LEFT JOIN
- Uses `j1.verification_status`, `j1.onset_date`, `j1.abatement_date`

#### Test 3: Full CMS165
Expected improvements:
- JOINs: 13 → 40+ (3x increase)
- Correlated subqueries: 579 → 480-520 (15-20% reduction)
- Precomputed column usage: 0 → 50+ uses

---

## Implementation Checklist

### Prerequisites
- [ ] Review current fluent function implementations in `fluent_functions.py`
- [ ] Understand fluent function registry and templates
- [ ] Review AST types in `types.py` (SQLFunctionCall, SQLLambda, SQLList)

### Phase 1: Infrastructure
- [ ] Create `_build_template_ast()` method
- [ ] Create `_extract_cte_name()` helper
- [ ] Add NotImplementedError for fallback to string templates

### Phase 2: Core Functions
- [ ] Implement `_build_verified_ast()`
- [ ] Implement `_build_prevalence_interval_ast()`
- [ ] Implement `_build_latest_ast()`
- [ ] Test each function individually

### Phase 3: Integration
- [ ] Modify `_inline_fluent_function_call()` to try AST first
- [ ] Ensure backward compatibility with string templates
- [ ] Test with simple definitions

### Phase 4: AST Types
- [ ] Add/verify SQLLambda type with `to_sql()`
- [ ] Add/verify SQLList type with `to_sql()`
- [ ] Add/verify SQLFunctionCall handles nested AST args

### Phase 5: Query Builder
- [ ] Verify CTE reference tracking works through fluent functions
- [ ] Test JOIN generation for fluent function definitions
- [ ] Ensure column registry lookups happen correctly

### Phase 6: Testing
- [ ] Test with CMS165 measure
- [ ] Compare before/after SQL
- [ ] Measure performance improvements
- [ ] Run diagnostic test: `uv run test_join_optimization.py`

---

## Success Metrics

### Current (Before Option A)
- Definitions using AST path: 13/42 (31%)
- JOINs generated: 13
- Correlated subqueries: 579
- Precomputed columns used: 0

### Target (After Option A)
- Definitions using AST path: 38-40/42 (90%+)
- JOINs generated: 38-40
- Correlated subqueries: 480-520
- Precomputed columns used: 50+

### Verification Commands
```bash
# Run translation test
uv run test_join_optimization.py

# Count JOINs in CTEs
grep "LEFT JOIN" cms165_optimized.sql | grep -v "_patients AS" | wc -l

# Count correlated subqueries
grep -c "(SELECT sq.resource FROM" cms165_optimized.sql

# Count precomputed column uses (sample)
grep -c "j[0-9]\.onset_date" cms165_optimized.sql
grep -c "j[0-9]\.verification_status" cms165_optimized.sql
```

---

## Alternative Approach: Option B (Not Recommended)

**Option B**: Post-process SQL strings with regex to inject JOINs

**Why not recommended**:
- Against design philosophy (should use AST)
- Fragile (breaks with SQL formatting changes)
- Hard to maintain
- Doesn't enable column optimization
- Loses benefits of structured representation

**If pursued anyway**:
1. Parse SQL string to extract CTE structure
2. Detect FHIRPath calls in WHERE clauses
3. Extract CTE references from correlated subqueries
4. Inject LEFT JOINs before WHERE
5. Replace subqueries with JOIN aliases

This would be ~500 lines of complex regex and string manipulation, vs ~300 lines of clean AST building for Option A.

---

## Next Steps

1. **Immediate**: Review this document with team
2. **Short-term**: Implement Phase 1-3 (core AST builders)
3. **Medium-term**: Complete Phases 4-5 (types and integration)
4. **Validation**: Test with CMS165 and measure improvements

## Questions for Discussion

1. Should we implement all fluent functions at once, or phase by phase?
2. What's the fallback strategy if AST building fails for a function?
3. Should column optimization be automatic or opt-in?
4. How to handle fluent functions on non-CTE sources (e.g., raw resources table)?
5. Performance testing strategy for large datasets?

---

## Appendix: Key Files Reference

- **fluent_functions.py**: Fluent function translation (lines 789-900)
- **translator.py**: CQL to SQL translation, definition building
- **expressions.py**: Expression translation, identifier tracking
- **types.py**: AST type definitions (SQLExpression subclasses)
- **column_registry.py**: Precomputed column tracking
- **context.py**: Translation context, DefinitionMeta

## Appendix: Glossary

- **AST Path**: Definitions that return SQLSelect AST, enabling JOIN optimization
- **STRING Path**: Definitions that return SQL strings, bypassing optimization
- **CTE**: Common Table Expression (WITH clause)
- **Query Builder**: Tracks CTE references for JOIN generation
- **Precomputed Column**: Column added to retrieve CTE for common property access
- **Fluent Function**: CQL extension method (.verified(), .prevalenceInterval(), etc.)
