# Design Document: Context-Aware CQL-to-SQL Translation

## 1. Executive Summary

### What is Context-Aware Translation?

Context-aware translation is an approach where the translator knows **how an expression's result will be used** before generating SQL. This context flows down through the translation pipeline, enabling correct SQL generation from the start.

### Why Do We Need It?

**The O(n^2) Correlated Subquery Problem**

Consider this simple CQL:
```cql
define Diabetes: [Condition: "Diabetes"]
define HasDiabetes: exists Diabetes
```

Without context awareness, the translator generates:
```sql
-- Current (BROKEN) - O(n^2) performance
SELECT p.patient_id,
       EXISTS (SELECT 1 FROM "Diabetes" d WHERE d.patient_ref = p.patient_id)
FROM _patients p
```

Each patient row executes a separate subquery. For 10,000 patients, this is 10,000 subquery executions.

With context awareness:
```sql
-- Expected (CORRECT) - O(n) performance
SELECT p.patient_id, j1.resource IS NOT NULL AS has_diabetes
FROM _patients p
LEFT JOIN "Diabetes" j1 ON j1.patient_ref = p.patient_id
```

A single JOIN processes all patients in one pass.

### High-Level Approach

1. **Pass usage context down**: When translating a WHERE clause, pass `ExprUsage.BOOLEAN`. When translating property access, pass `ExprUsage.SCALAR`.

2. **Register JOINs during translation**: When a Retrieve expression is translated with SCALAR/BOOLEAN/EXISTS context, register a JOIN with `SQLQueryBuilder` and return a column reference.

3. **Emit JOINs in the right scope**: JOINs registered during CTE translation are added to that CTE's FROM clause, not the final SELECT.

---

## 2. CQL to SQL Examples

### 2.1 Simple Retrieve

**CQL Input:**
```cql
define Diabetes: [Condition: "Diabetes"]
```

**Current (Working) SQL:**
```sql
"Diabetes" AS (
    SELECT r.patient_ref AS patient_id, r.resource
    FROM resources r
    WHERE r.resourceType = 'Condition'
      AND fhirpath_in_valueset(r.resource, 'code', 'http://diabetes-valueset-url')
)
```

**Expected (Same):** This works correctly - retrieve expressions default to LIST context.

**What needs to change:** Nothing - this pattern is correct.

---

### 2.2 Property Access

**CQL Input:**
```cql
define Diabetes: [Condition: "Diabetes"]
define DiabetesStatus: Diabetes.status
```

**Current (Broken) SQL:**
```sql
"Diabetes" AS (
    SELECT r.patient_ref AS patient_id, r.resource
    FROM resources r
    WHERE ...
),
"DiabetesStatus" AS (
    SELECT p.patient_id,
           fhirpath_text((SELECT resource FROM "Diabetes" d WHERE d.patient_id = p.patient_id), 'status')
    FROM _patients p
)
```

The nested SELECT inside `fhirpath_text` is a correlated subquery - executes once per patient.

**Expected (Correct) SQL:**
```sql
"Diabetes" AS (
    SELECT r.patient_ref AS patient_id, r.resource
    FROM resources r
    WHERE ...
),
"DiabetesStatus" AS (
    SELECT p.patient_id, fhirpath_text(j1.resource, 'status') AS value
    FROM _patients p
    LEFT JOIN "Diabetes" j1 ON j1.patient_id = p.patient_id
)
```

**What needs to change:**
- `_translate_property()` must pass `ExprUsage.SCALAR` when translating the source
- `_translate_identifier()` must register a JOIN and return a column reference when in SCALAR context
- `_build_definition_cte_with_patient_id()` must emit JOINs registered during CTE translation

**Files to modify:**
- `expressions.py:645` - `_translate_property()`
- `expressions.py:365` - `_translate_identifier()`
- `translator.py:1051` - `_build_definition_cte_with_patient_id()`

---

### 2.3 Exists Expression

**CQL Input:**
```cql
define Diabetes: [Condition: "Diabetes"]
define HasDiabetes: exists Diabetes
```

**Current (Broken) SQL:**
```sql
"HasDiabetes" AS (
    SELECT p.patient_id,
           CASE WHEN array_length((SELECT resource FROM "Diabetes" d WHERE d.patient_id = p.patient_id)) > 0
                THEN TRUE ELSE FALSE END
    FROM _patients p
)
```

**Expected (Correct) SQL:**
```sql
"HasDiabetes" AS (
    SELECT p.patient_id, j1.resource IS NOT NULL AS value
    FROM _patients p
    LEFT JOIN "Diabetes" j1 ON j1.patient_id = p.patient_id
)
```

**What needs to change:**
- `_translate_exists_expression()` must translate source with `ExprUsage.EXISTS`
- `_translate_identifier()` in EXISTS context must return `IS NOT NULL` expression
- JOINs must be emitted in the CTE

**Files to modify:**
- `expressions.py` - `_translate_exists_expression()` (needs to be updated to use `usage` parameter)
- `queries.py:568` - `_translate_where()` (already passes BOOLEAN)

---

### 2.4 WHERE Clause

**CQL Input:**
```cql
define ConfirmedDiabetes:
    [Condition: "Diabetes"] C where C.verificationStatus = 'confirmed'
```

**Current (Broken) SQL:**
```sql
"ConfirmedDiabetes" AS (
    SELECT r.patient_ref AS patient_id, r.resource
    FROM resources r
    WHERE r.resourceType = 'Condition'
      AND fhirpath_in_valueset(r.resource, 'code', 'http://...')
      AND fhirpath_text(r.resource, 'verificationStatus') = 'confirmed'
)
```

Actually this one works! Because the WHERE clause is on the same resource being retrieved.

**What needs to change:** Nothing for this pattern - it's already correct.

---

### 2.5 Definition Reference

**CQL Input:**
```cql
define Diabetes: [Condition: "Diabetes"]
define HasDiabetes: exists Diabetes
```

**Current Flow (Broken):**
```
1. translate_library() translates "Diabetes" -> SQLSelect
2. translate_library() translates "HasDiabetes" -> exists (subquery to "Diabetes")
3. _build_definition_cte_with_patient_id() wraps each in CTE
4. JOINs are registered but NOT added to CTE FROM clauses
5. JOINs only appear in final SELECT (wrong scope)
```

**Expected Flow (Correct):**
```
1. translate_library() creates fresh SQLQueryBuilder for each definition
2. "Diabetes" translated -> SQLSelect (LIST context, no JOIN)
3. "HasDiabetes" translated:
   - _translate_exists_expression() calls translate(source, usage=EXISTS)
   - _translate_identifier("Diabetes", usage=EXISTS) registers JOIN, returns IS NOT NULL
4. _build_definition_cte_with_patient_id():
   - Detects tracked JOINs
   - Adds JOINs to CTE's FROM clause
   - Clears query_builder for next definition
```

**Files to modify:**
- `translator.py:672` - `translate_library()` - ensure query_builder is created
- `translator.py:1133` - `_build_definition_cte_with_patient_id()` - emit JOINs

---

### 2.6 Fluent Function

**CQL Input:**
```cql
define Diabetes: [Condition: "Diabetes"]
define VerifiedDiabetes: Diabetes.verified()
```

**Current (Broken) SQL:**
The fluent function template in `fluent_functions.py` uses `{resource}` placeholder:
```python
body_sql="list_filter({resource}, r -> fhirpath_text(r, 'verificationStatus.coding.code') IN ('confirmed', 'provisional'))"
```

When `{resource}` is substituted with a subquery:
```sql
list_filter((SELECT resource FROM "Diabetes" d WHERE d.patient_id = p.patient_id), r -> ...)
```

This is invalid - `list_filter` expects an array, not a scalar subquery.

**Expected (Correct) SQL:**
```sql
"VerifiedDiabetes" AS (
    SELECT p.patient_id, list_filter(j1.resource, r -> ...) AS resource
    FROM _patients p
    LEFT JOIN "Diabetes" j1 ON j1.patient_id = p.patient_id
)
```

**What needs to change:**
- `_substitute_template()` in `fluent_functions.py` needs to handle JOIN references
- When `{resource}` is a CTE reference, use the JOIN alias instead of inline subquery
- Column registry needed to know which columns are available

**Files to modify:**
- `fluent_functions.py:831` - `_substitute_template()`
- Need new: column registry in `SQLRetrieveCTE`

---

### 2.7 Complex Query (Union with WHERE and Property Access)

**CQL Input:**
```cql
define Hypertension: [Condition: "Essential Hypertension"]
define Diabetes: [Condition: "Diabetes"]
define ChronicConditions: Hypertension union Diabetes
define HasChronic: exists ChronicConditions
define ChronicStatus: ChronicConditions.status
```

**Current (Broken) SQL:**
```sql
-- Multiple levels of nested subqueries
"HasChronic" AS (
    SELECT p.patient_id,
           EXISTS (
               SELECT 1 FROM (
                   SELECT resource FROM "Hypertension" WHERE patient_id = p.patient_id
                   UNION ALL
                   SELECT resource FROM "Diabetes" WHERE patient_id = p.patient_id
               )
           )
    FROM _patients p
)
```

**Expected (Correct) SQL:**
```sql
"HasChronic" AS (
    SELECT p.patient_id,
           COALESCE(j1.resource IS NOT NULL, j2.resource IS NOT NULL) AS value
    FROM _patients p
    LEFT JOIN "Hypertension" j1 ON j1.patient_id = p.patient_id
    LEFT JOIN "Diabetes" j2 ON j2.patient_id = p.patient_id
)
```

**What needs to change:**
- `SQLUnion` handling needs to register multiple JOINs
- COALESCE of IS NOT NULL expressions for boolean context

---

## 3. Translation Pipeline

### Trace: `exists [Condition: "Diabetes"]`

```
CQL: exists [Condition: "Diabetes"]
     |
     v
AST: ExistsExpression(source=Retrieve(type="Condition", terminology="Diabetes"))
     |
     v
ExpressionTranslator.translate(expr, usage=ExprUsage.LIST)  [default]
     |
     v
_translate_exists_expression(expr, boolean_context=False)
     |
     [NEEDS FIX: Should call translate(source, usage=ExprUsage.EXISTS)]
     v
_translate_retrieve(retrieve, usage=???)
     |
     [CURRENT: usage is not passed, defaults to LIST]
     [EXPECTED: usage=EXISTS]
     v
```

**Current Behavior (Broken):**
```
_translate_retrieve() with usage=LIST (default)
     |
     v
Returns: SQLSubquery(query=SQLSelect(...FROM resources...))
     |
     v
_translate_exists_expression wraps in array_length() > 0
     |
     v
Result: array_length((SELECT resource FROM resources WHERE ...)) > 0
         [Correlated subquery - slow!]
```

**Expected Behavior (Correct):**
```
_translate_exists_expression calls translate(source, usage=ExprUsage.EXISTS)
     |
     v
_translate_retrieve() with usage=EXISTS
     |
     v
Registers JOIN with query_builder.track_cte_reference("Condition: Diabetes", usage=EXISTS)
     |
     v
Returns: SQLBinaryOp(operator="IS NOT", left=j1.resource, right=SQLNull())
     |
     v
_build_definition_cte_with_patient_id() sees tracked JOINs
     |
     v
Adds JOIN to CTE: LEFT JOIN "Condition: Diabetes" j1 ON j1.patient_id = p.patient_id
     |
     v
Result: j1.resource IS NOT NULL
         [JOIN - fast!]
```

### Key Files and Functions

| Step | File | Function | Line |
|------|------|----------|------|
| Entry point | `translator.py` | `translate_library()` | 672 |
| Query builder init | `translator.py` | `translate_library_to_population_sql()` | 850 |
| Definition translation | `translator.py` | `translate_definition()` | - |
| Expression dispatch | `expressions.py` | `translate()` | 217 |
| Exists handling | `expressions.py` | `_translate_function_ref()` | 1000 |
| Retrieve handling | `expressions.py` | `_translate_retrieve()` | - |
| Identifier handling | `expressions.py` | `_translate_identifier()` | 365 |
| JOIN tracking | `queries.py` | `track_cte_reference()` | 91 |
| CTE building | `translator.py` | `_build_definition_cte_with_patient_id()` | 1051 |
| JOIN emission | `translator.py` | `_convert_scalar_subqueries_to_joins_ast()` | 1253 |

---

## 4. Data Structures

### 4.1 ExprUsage Enum

**File:** `cql-py/src/cql_py/translator/context.py:18-31`

```python
class ExprUsage(Enum):
    """
    How an expression's result will be used.

    This determines how Retrieve expressions are translated:
    - LIST: Return a collection (correlated subquery)
    - SCALAR: Return a single value (JOIN + column reference)
    - BOOLEAN: Truth test in WHERE/AND/OR (JOIN + IS NOT NULL)
    - EXISTS: Existence check (JOIN + IS NOT NULL, same as BOOLEAN)
    """
    LIST = auto()      # Default CQL semantics - return collection
    SCALAR = auto()    # Need single value (property access, comparison, FHIRPath arg)
    BOOLEAN = auto()   # Truth test (WHERE clause, AND/OR operands, NOT operand)
    EXISTS = auto()    # Existence test (exists() function) - treated same as BOOLEAN
```

**When is each used?**

| Usage | Context | Example |
|-------|---------|---------|
| LIST | Query source, default | `[Condition: "Diabetes"]` |
| SCALAR | Property access source | `Diabetes.status` |
| SCALAR | Comparison operand | `Diabetes.status = 'confirmed'` |
| BOOLEAN | WHERE clause | `where C.status = 'confirmed'` |
| BOOLEAN | AND/OR operands | `exists A and exists B` |
| EXISTS | exists() function | `exists [Condition: "Diabetes"]` |

### 4.2 CTEReference

**File:** `cql-py/src/cql_py/translator/queries.py:56-65`

```python
@dataclass
class CTEReference:
    """
    Tracks a reference to a CTE that may need to be joined.

    Extended to include usage context for context-aware translation.
    """
    cte_name: str
    alias: str
    patient_correlated: bool = True  # Whether this CTE has patient_ref column
    usage: ExprUsage = ExprUsage.SCALAR  # How this reference is used
```

**When is it created?**
- In `track_cte_reference()` when a definition is referenced in SCALAR/BOOLEAN/EXISTS context

**When is it consumed?**
- In `generate_joins()` to build JOIN clauses
- In `get_column_reference()` to get `alias.resource`

### 4.3 SQLQueryBuilder

**File:** `cql-py/src/cql_py/translator/queries.py:68-183`

```python
class SQLQueryBuilder:
    """
    Helper class for building SQL queries with proper JOIN tracking.

    Tracks CTE references and converts scalar subqueries to JOINs for
    better query performance (avoids O(n^2) correlated subquery behavior).
    """

    def __init__(self):
        self.cte_references: Dict[str, CTEReference] = {}
        self.join_counter = 0

    def track_cte_reference(self, cte_name: str, alias: Optional[str] = None,
                           usage: ExprUsage = ExprUsage.SCALAR) -> str:
        """Register a CTE for JOINing, return the alias."""

    def generate_joins(self, patient_alias: str = "p") -> List[SQLJoin]:
        """Generate JOIN clauses for all tracked references."""

    def get_column_reference(self, cte_name: str, column: str = "resource") -> SQLQualifiedIdentifier:
        """Get qualified column reference (e.g., 'j1.resource')."""
```

**Lifecycle:**
1. Created at start of `translate_library_to_population_sql()` (line 850)
2. Cleared after each CTE is built (line 1135)
3. JOINs extracted and added to CTE FROM clause

### 4.4 SymbolInfo

**File:** `cql-py/src/cql_py/translator/context.py:34-53`

```python
@dataclass
class SymbolInfo:
    """
    Information about a symbol in the translation context.

    Attributes:
        name: The symbol name.
        symbol_type: The type of symbol ('parameter', 'let', 'definition', 'alias', etc.)
        sql_expr: The SQL expression for this symbol (if applicable).
        cql_type: The CQL type of the symbol (if known).
        scope_level: The scope level where this symbol was defined.
        union_expr: For aliases that are SQLUnion, store the actual object.
    """
    name: str
    symbol_type: str
    sql_expr: Optional[str] = None
    cql_type: Optional[str] = None
    scope_level: int = 0
    union_expr: Any = None  # SQLUnion object when sql_expr == "__UNION__"
```

**How definition references work:**
1. `translate_library()` calls `translate_definition()` for each definition
2. Result stored in `context.definitions[name] = sql_expression`
3. Later, `_translate_identifier()` looks up in `context.definitions`
4. If usage is SCALAR/BOOLEAN/EXISTS, registers JOIN and returns column ref

---

## 5. The JOIN Problem

### Current Flow (Broken)

```
translate_library_to_population_sql()
     |
     v
context.query_builder = SQLQueryBuilder()  [line 850]
     |
     v
translate_library()
     |
     v
translate_definition("HasDiabetes")
     |
     v
translate(exists Diabetes) -> SQL with correlated subquery
     |
     [JOIN registered but subquery still generated]
     v
_build_definition_cte_with_patient_id()
     |
     [JOINs added to select_stmt.joins at line 1118]
     [BUT query_builder cleared at line 1135]
     v
CTE built with JOINs
     |
     [Problem: JOINs reference "Diabetes" CTE which has its own scope]
     v
Final SELECT built separately
```

### The Core Issue

**JOINs are registered globally but CTEs have separate scopes.**

When translating "HasDiabetes":
1. It references "Diabetes" CTE
2. JOIN is registered: `LEFT JOIN "Diabetes" j1 ON j1.patient_id = p.patient_id`
3. This JOIN is added to "HasDiabetes" CTE's FROM clause
4. BUT "Diabetes" CTE doesn't have a `patient_id` column in the JOIN's scope - it has `patient_ref`

**The fix:** JOINs must be added to the CTE that contains the reference, using the correct column names for that CTE.

### What Should Happen

```
For each definition:
    1. Create fresh query_builder for this definition's scope
    2. Translate expression
       - If references another CTE in SCALAR/BOOLEAN/EXISTS context:
         - Register JOIN with correct column mapping
         - Return column reference or IS NOT NULL
    3. Build CTE:
       - Add all registered JOINs to FROM clause
       - Use correct correlation (j1.patient_ref = p.patient_id)
    4. Clear query_builder
```

### Scope Boundary

Each CTE is its own scope. JOINs registered during CTE A's translation should:
- Be added to CTE A's FROM clause
- Reference columns from CTE A's context (usually `_patients` or a dependent CTE)
- NOT leak into other CTEs or the final SELECT

---

## 6. Precomputed Columns

### 6.1 SQLRetrieveCTE Structure

**File:** `cql-py/src/cql_py/translator/types.py:791-925`

```python
@dataclass
class SQLRetrieveCTE:
    """
    Represents a CTE for a FHIR resource retrieval with ValueSet filter.

    Pre-computes commonly used columns to avoid repeated fhirpath calls.
    """
    name: str                          # CTE name: "{resourceType}: {valueset_alias}"
    resource_type: str                 # FHIR resource type
    valueset_url: Optional[str] = None
    valueset_alias: Optional[str] = None
    profile_url: Optional[str] = None
    precomputed_columns: Dict[str, SQLExpression] = field(default_factory=dict)
    materialized: bool = True
```

### 6.2 Precomputed Column Definitions

**File:** `cql-py/src/cql_py/translator/types.py:928-997`

```python
CHOICE_TYPE_COLUMNS = {
    "effective_date": {
        "paths": ["effectiveDateTime", "effectivePeriod.start"],
        "sql_type": "DATE",
        "fhirpath_function": "fhirpath_date",
        "resources": ["Observation", "Procedure", "Encounter", "DiagnosticReport"],
    },
    "onset_date": {
        "paths": ["onsetDateTime", "onsetPeriod.start"],
        "sql_type": "DATE",
        "fhirpath_function": "fhirpath_date",
        "resources": ["Condition"],
    },
    "verification_status": {
        "paths": ["verificationStatus.coding.code", "verificationStatus"],
        "sql_type": "VARCHAR",
        "fhirpath_function": "fhirpath_text",
        "resources": ["Condition"],
    },
    # ... more columns
}
```

### 6.3 Current Problem

The CTE has precomputed columns:
```sql
"Condition: Diabetes" AS (
    SELECT
        r.patient_ref,
        r.resource,
        COALESCE(fhirpath_text(r.resource, 'verificationStatus.coding.code'),
                 fhirpath_text(r.resource, 'verificationStatus')) AS verification_status
    FROM resources r
    WHERE ...
)
```

But property access still calls fhirpath:
```sql
-- Current: ignores precomputed column
fhirpath_text(j1.resource, 'verificationStatus') = 'confirmed'

-- Expected: use precomputed column
j1.verification_status = 'confirmed'
```

### 6.4 Solution Needed: Column Registry

**New component needed:** A registry that maps `(cte_name, property_path) -> column_name`

```python
class ColumnRegistry:
    """Tracks precomputed columns available in each CTE."""

    def __init__(self):
        self._columns: Dict[str, Dict[str, str]] = {}  # cte_name -> {path -> column}

    def register(self, cte_name: str, path: str, column_name: str):
        """Register a precomputed column for a CTE."""
        if cte_name not in self._columns:
            self._columns[cte_name] = {}
        self._columns[cte_name][path] = column_name

    def lookup(self, cte_name: str, path: str) -> Optional[str]:
        """Look up a precomputed column, return column name or None."""
        return self._columns.get(cte_name, {}).get(path)
```

**Integration points:**
- `SQLRetrieveCTE.to_sql()` registers columns when building CTE
- `_translate_property()` checks registry before calling fhirpath
- `_substitute_template()` in fluent_functions.py uses registry

---

## 7. Implementation Roadmap

### Priority 1: Fix JOIN Emission (Critical)

**Problem:** JOINs registered but not added to CTEs

**Files to modify:**

| File | Line | Function | Change |
|------|------|----------|--------|
| `translator.py` | 1133 | `_build_definition_cte_with_patient_id()` | Don't clear query_builder before emitting JOINs |
| `translator.py` | 1108 | `_build_definition_cte_with_patient_id()` | Ensure JOINs added to correct FROM clause |
| `translator.py` | 1221 | `_convert_scalar_subqueries_to_joins_ast()` | Handle scope correctly |

**Test case:**
```cql
define Diabetes: [Condition: "Diabetes"]
define HasDiabetes: exists Diabetes
```
Should produce JOIN in "HasDiabetes" CTE, not final SELECT.

---

### Priority 2: Complete Handler Migration (High)

**Problem:** Many handlers still use `boolean_context: bool` instead of `usage: ExprUsage`

**Files to modify:**

| File | Function | Current | Change To |
|------|----------|---------|-----------|
| `expressions.py` | `_translate_exists_expression()` | Not using `usage` | Pass `ExprUsage.EXISTS` to source |
| `expressions.py` | `_translate_unary_expression()` | `boolean_context` | `usage` parameter |
| `expressions.py` | `_translate_conditional()` | `boolean_context` | Pass BOOLEAN to condition |
| `queries.py` | `_translate_source()` | `boolean_context` | Default to LIST |

**Migration pattern:**
```python
# Before
def _translate_xxx(self, expr, boolean_context: bool = False):
    if boolean_context:
        ...

# After
def _translate_xxx(self, expr, usage: ExprUsage = ExprUsage.LIST):
    if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
        ...
```

---

### Priority 3: Add Column Registry (Medium)

**Problem:** Precomputed columns not used in property access

**New file:** `cql-py/src/cql_py/translator/column_registry.py`

```python
class ColumnRegistry:
    """Tracks precomputed columns available in each CTE."""

    def __init__(self):
        self._columns: Dict[str, Dict[str, str]] = {}

    def register_cte(self, cte_name: str, columns: Dict[str, str]):
        """Register all columns for a CTE."""
        self._columns[cte_name] = columns

    def lookup(self, cte_name: str, path: str) -> Optional[str]:
        """Look up precomputed column, return column name or None."""
        return self._columns.get(cte_name, {}).get(path)

    def get_all_for_cte(self, cte_name: str) -> Dict[str, str]:
        """Get all registered columns for a CTE."""
        return self._columns.get(cte_name, {})
```

**Integration:**
- `SQLTranslationContext` gets `column_registry: ColumnRegistry` field
- `SQLRetrieveCTE.to_sql()` registers columns
- `_translate_property()` checks registry first
- `_substitute_template()` uses registry for fluent functions

---

### Priority 4: Fix Fluent Functions (Medium)

**Problem:** Templates use `{resource}` placeholder but don't handle JOIN references

**Files to modify:**

| File | Line | Function | Change |
|------|------|----------|--------|
| `fluent_functions.py` | 831 | `_substitute_template()` | Check if resource is CTE reference, use JOIN alias |
| `fluent_functions.py` | 870 | `_substitute_template()` | Use column registry for property paths |

**Pattern:**
```python
def _substitute_template(self, template, resource_expr, args, func_def):
    resource_sql = resource_expr.to_sql()

    # Check if this is a CTE reference that's being JOINed
    if self.context.query_builder:
        ref = self.context.query_builder.get_cte_reference(resource_sql.strip('"'))
        if ref:
            # Use JOIN alias instead of CTE name
            resource_sql = ref.alias

            # Check column registry for precomputed columns
            if "{resource}" in template and "fhirpath_text" in template:
                # Try to use precomputed column if available
                ...

    result = template.replace("{resource}", resource_sql)
    ...
```

---

### Priority 5: Test Coverage (Ongoing)

**New tests needed:**

```python
# tests/unit/test_context_aware_translation.py

class TestJoinEmission:
    """JOINs must appear in CTEs, not just final SELECT."""

    def test_join_in_exists_cte(self):
        """exists Diabetes should have JOIN in HasDiabetes CTE."""
        sql = translate_cql('''
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        ''')
        # JOIN should be in "HasDiabetes" CTE, not final SELECT
        has_diabetes_cte = extract_cte(sql, "HasDiabetes")
        assert "LEFT JOIN" in has_diabetes_cte
        assert '"Diabetes"' in has_diabetes_cte

    def test_join_in_property_access_cte(self):
        """Diabetes.status should have JOIN in Status CTE."""
        sql = translate_cql('''
            define Diabetes: [Condition: "Diabetes"]
            define Status: Diabetes.status
        ''')
        status_cte = extract_cte(sql, "Status")
        assert "LEFT JOIN" in status_cte

class TestColumnRegistry:
    """Precomputed columns should be used."""

    def test_uses_precomputed_verification_status(self):
        """Property access should use precomputed column."""
        sql = translate_cql('''
            define Diabetes: [Condition: "Diabetes"]
            define Verified: Diabetes.verificationStatus = 'confirmed'
        ''')
        # Should use j1.verification_status, not fhirpath_text(j1.resource, ...)
        assert "verification_status" in sql
        assert "fhirpath_text" not in sql or "verification_status" in sql
```

---

## 8. Code References

### Key Files

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `context.py` | Translation context, symbol tables | `ExprUsage`, `SymbolInfo`, `SQLTranslationContext` |
| `queries.py` | Query translation, JOIN tracking | `CTEReference`, `SQLQueryBuilder`, `QueryTranslator` |
| `translator.py` | Main translator, CTE building | `CQLToSQLTranslator`, `_build_definition_cte_with_patient_id()` |
| `expressions.py` | Expression translation | `ExpressionTranslator`, `translate()`, `_translate_*()` |
| `fluent_functions.py` | Fluent function templates | `FluentFunctionTranslator`, `_substitute_template()` |
| `types.py` | SQL AST types | `SQLSelect`, `SQLJoin`, `SQLRetrieveCTE`, `CHOICE_TYPE_COLUMNS` |

### Critical Line Numbers

| File:Line | Function | Importance |
|-----------|----------|------------|
| `expressions.py:217` | `translate()` | Entry point, dispatches to handlers |
| `expressions.py:365` | `_translate_identifier()` | Definition references, JOIN registration |
| `expressions.py:645` | `_translate_property()` | Must pass SCALAR to source |
| `queries.py:91` | `track_cte_reference()` | JOIN tracking |
| `queries.py:121` | `generate_joins()` | JOIN emission |
| `translator.py:850` | `translate_library_to_population_sql()` | Query builder init |
| `translator.py:1051` | `_build_definition_cte_with_patient_id()` | CTE building, JOIN emission |
| `translator.py:1133` | `query_builder.clear()` | **Problem: clears JOINs too early** |
| `fluent_functions.py:831` | `_substitute_template()` | Template substitution |
| `types.py:865` | `SQLRetrieveCTE.to_sql()` | CTE generation with precomputed columns |

### Debug Commands

```bash
# Find all translate() calls
grep -rn "\.translate(" cql-py/src/cql_py/translator/ | grep -v "def translate"

# Find boolean_context usages (need migration)
grep -rn "boolean_context" cql-py/src/cql_py/translator/

# Find JOIN tracking
grep -rn "track_cte_reference\|generate_joins" cql-py/src/cql_py/translator/

# Find query_builder clearing
grep -rn "query_builder.clear()" cql-py/src/cql_py/translator/
```

---

## Appendix A: SQL Types Quick Reference

| Type | Usage | Example |
|------|-------|---------|
| `SQLLiteral` | Literal values | `'confirmed'`, `123`, `TRUE` |
| `SQLIdentifier` | Simple names | `patient_id`, `resource` |
| `SQLQualifiedIdentifier` | Qualified names | `j1.resource`, `p.patient_id` |
| `SQLBinaryOp` | Binary operators | `a = b`, `x AND y`, `j1.resource IS NOT NULL` |
| `SQLUnaryOp` | Unary operators | `NOT x`, `x IS NULL` |
| `SQLFunctionCall` | Function calls | `fhirpath_text(r, 'status')` |
| `SQLSelect` | SELECT statement | Full query structure |
| `SQLJoin` | JOIN clause | `LEFT JOIN "CTE" j1 ON ...` |
| `SQLSubquery` | Subquery wrapper | `(SELECT ...)` |
| `SQLUnion` | UNION/UNION ALL | Combining queries |
| `SQLCase` | CASE expression | Conditional logic |
| `SQLNull` | NULL literal | `NULL` |

---

## Appendix B: ExprUsage Decision Tree

```
Is this expression's result used as a...
|
+-- Collection source (FROM clause)? --> LIST
|
+-- Single value (property source, comparison operand)? --> SCALAR
|
+-- Truth test (WHERE condition, AND/OR operand)? --> BOOLEAN
|
+-- Existence check (exists() function)? --> EXISTS
```

**Examples:**

| CQL | Expression | Usage |
|-----|------------|-------|
| `[Condition]` | Retrieve | LIST (default) |
| `Diabetes.status` | Identifier "Diabetes" | SCALAR |
| `exists Diabetes` | Identifier "Diabetes" | EXISTS |
| `where C.status = 'confirmed'` | Property "C.status" | SCALAR (comparison) |
| `where exists Diabetes` | Identifier "Diabetes" | EXISTS |
| `where A and B` | A, B | BOOLEAN |
| `First([Condition])` | Retrieve | LIST (need all to pick first) |

---

## Appendix C: Validation Checklist

Before marking implementation complete:

- [ ] `ExprUsage` enum exists in `context.py`
- [ ] `CTEReference.usage` field exists
- [ ] `translate()` accepts `usage` parameter
- [ ] `_translate_identifier()` registers JOINs for SCALAR/BOOLEAN/EXISTS
- [ ] `_translate_property()` passes SCALAR to source
- [ ] `_translate_exists_expression()` passes EXISTS to source
- [ ] JOINs appear in CTE FROM clauses (not just final SELECT)
- [ ] Column registry tracks precomputed columns
- [ ] Property access uses precomputed columns when available
- [ ] Fluent function templates handle JOIN references
- [ ] All `boolean_context` parameters migrated to `usage`
- [ ] Test: `exists [Condition]` produces JOIN
- [ ] Test: `Definition.status` produces JOIN
- [ ] CMS165 SQL executes successfully

---

## Appendix D: Critical Design Gaps (Added 2025-02-24)

This section documents additional design issues discovered during architecture review.

### D.1 Duplicate SQLTranslationContext Classes (CRITICAL)

**Problem:** Two separate `SQLTranslationContext` classes exist:

| File | Line | Type | Key Differences |
|------|------|------|-----------------|
| `context.py` | 104 | `@dataclass` | Has `scopes`, `push_scope()`, `pop_scope()`, proper scope management |
| `translator.py` | 135 | Regular class | Has `_symbols`, `_alias_scopes`, different API |

**Impact:**
- Import confusion: which class is used where?
- Missing fields: `translator.py` version lacks `scopes` stack
- Different symbol APIs: `add_symbol()` vs `define_symbol()`
- `query_builder` may be on wrong instance

**Resolution Required:** Consolidate into single class. Recommend keeping `context.py` version (dataclass, cleaner) and migrating `translator.py` to use it.

### D.2 Row-Shape / Cardinality Tracking (CRITICAL)

**Problem:** `ExprUsage` tracks *how* a result is used but NOT *what* a definition produces.

**Missing Metadata:**

| Definition Type | Rows/Patient | Safe to JOIN? |
|-----------------|--------------|---------------|
| `[Condition]` | Many | NO - causes fanout |
| `exists [Condition]` | 1 (boolean) | YES |
| `First([Observation])` | 1 (resource) | YES |
| `[Observation].status` | Many (projection) | NO |

**Example Failure:**

```cql
define Diabetes: [Condition: "Diabetes"]  -- Returns 3 rows for patient A
define HasDiabetes: exists Diabetes
```

If "HasDiabetes" JOINs "Diabetes" directly:
```sql
-- WRONG: Patient A appears 3 times!
SELECT p.patient_id, j1.resource IS NOT NULL AS value
FROM _patients p
LEFT JOIN "Diabetes" j1 ON j1.patient_id = p.patient_id
```

**Correct approach:**
```sql
-- RIGHT: Use DISTINCT to avoid fanout
SELECT p.patient_id, j1.patient_id IS NOT NULL AS value
FROM _patients p
LEFT JOIN (SELECT DISTINCT patient_id FROM "Diabetes") j1 ON j1.patient_id = p.patient_id
```

**Required:** Add `RowShape` enum and track per definition:

```python
class RowShape(Enum):
    PATIENT_SCALAR = auto()   # Exactly 1 row per patient (boolean, scalar value)
    PATIENT_LIST = auto()     # Exactly 1 row per patient (list-valued column)
    RESOURCE_ROWS = auto()    # Many rows per patient (one per resource)

@dataclass
class DefinitionMeta:
    name: str
    shape: RowShape
    has_resource: bool
    patient_key_col: str = "patient_id"  # Column name for patient correlation
```

### D.3 patient_id vs patient_ref Inconsistency (HIGH)

**Problem:** Code uses both column names inconsistently:

| Location | Column Used |
|----------|-------------|
| `resources` table | `patient_ref` |
| `_patients` CTE | `patient_id` |
| `SQLRetrieveCTE` output | `patient_ref` (aliased to `patient_id`?) |
| `generate_joins()` | `patient_ref` |
| Most CTE outputs | `patient_id` |

**Example bug in `queries.py:139`:**
```python
on_condition=SQLBinaryOp(
    operator="=",
    left=SQLQualifiedIdentifier(parts=[ref.alias, "patient_ref"]),  # ← Assumes patient_ref
    right=SQLQualifiedIdentifier(parts=[patient_alias, "patient_id"]),
)
```

If the CTE outputs `patient_id` (not `patient_ref`), this JOIN silently fails.

**Resolution:** Standardize to `patient_id` everywhere in CTE outputs.

### D.4 Property Access Over Collections (SEMANTIC GAP)

**Problem:** CQL property access over a collection is a **projection** returning a list.

```cql
define Diabetes: [Condition: "Diabetes"]
define Statuses: Diabetes.status  -- Returns LIST of statuses
```

**Current behavior:** Passes `SCALAR` context, gets single value (first? arbitrary?)

**Correct behavior:** Property access over `RESOURCE_ROWS` should:
1. Keep as resource-rows: `SELECT patient_id, fhirpath_text(resource, 'status') AS status FROM "Diabetes"`
2. Or aggregate to list: `SELECT patient_id, list_agg(fhirpath_text(resource, 'status')) AS statuses FROM "Diabetes" GROUP BY patient_id`

### D.5 Fluent Function Template Limitations (MEDIUM)

**Problem:** Template substitution in `fluent_functions.py:870-875` uses fragile string matching:

```python
if resource_sql.startswith('"') and resource_sql.endswith('"') and '.' not in resource_sql:
    resource_sql = f"{resource_sql}.resource"
```

**Issues:**
- Doesn't work for JOINed CTEs (`j1.resource`)
- Doesn't distinguish templates expecting arrays vs JSON strings
- No integration with column registry

**Required:** Templates should declare expected input type:

```python
@dataclass
class FunctionDefinition:
    # ... existing fields ...
    resource_type: Literal["json", "array", "any"] = "json"  # NEW
```

### D.6 NULL vs Empty List Semantics (MEDIUM)

**CQL Semantics:**
- Empty list `{}` is distinct from `null`
- `exists {}` → `false`
- `exists null` → `null` (in some contexts)
- `null and true` → `null`
- `{} and true` → `null` (empty propagates as null in logic)

**Current:** FHIRPath returns empty list, converted to SQL NULL in many cases.

**Risk:** Incorrect boolean logic results.

### D.7 singleton from / Implicit Singleton (MEDIUM)

**CQL:**
```cql
define Status: singleton from Diabetes.status
```

Should **error** if more than one status exists.

**Current:** Likely uses `LIMIT 1` or `list_extract(..., 1)` silently.

**Required:** Add `strict_mode` option that validates cardinality.

---

## Appendix E: Recommended Architecture Changes

### E.1 Unified Context Class

```python
# context.py - SINGLE source of truth
@dataclass
class SQLTranslationContext:
    # Core symbol management
    scopes: List[Scope] = field(default_factory=list)
    current_scope_level: int = 0
    
    # Definition metadata (NEW)
    definition_meta: Dict[str, DefinitionMeta] = field(default_factory=dict)
    
    # Column registry (NEW)
    column_registry: ColumnRegistry = field(default_factory=ColumnRegistry)
    
    # Query builder - scoped per CTE (CHANGED)
    # NOT stored here - created fresh per CTE translation
    
    # ... existing fields ...
```

### E.2 Scoped Query Builder Pattern

```python
# In translator.py
def translate_definition(self, name: str, expr: Expression) -> SQLExpression:
    # Create fresh query builder for this definition's scope
    query_builder = SQLQueryBuilder()
    
    # Store temporarily in context for expression translator to use
    old_builder = self._context.query_builder
    self._context.query_builder = query_builder
    
    try:
        # Translate expression - may register JOINs
        sql_expr = self._translate_expression(expr)
        
        # Build CTE with registered JOINs
        cte = self._build_cte_with_joins(name, sql_expr, query_builder)
        
        # Record definition metadata
        self._context.definition_meta[name] = DefinitionMeta(
            name=name,
            shape=self._infer_shape(sql_expr),
            has_resource=self._has_resource_column(cte),
        )
        
        return cte
    finally:
        self._context.query_builder = old_builder
```

### E.3 Safe JOIN Conversion with Shape Checking

```python
def _translate_identifier_for_join(
    self, 
    name: str, 
    usage: ExprUsage
) -> SQLExpression:
    meta = self.context.definition_meta.get(name)
    
    if meta is None:
        # Forward reference or unknown - fall back to subquery
        return self._build_correlated_subquery(name)
    
    if meta.shape == RowShape.RESOURCE_ROWS:
        if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
            # Multi-row source used for existence check
            # JOIN against DISTINCT patient_id to avoid fanout
            alias = self.context.query_builder.track_cte_reference(
                name, 
                usage=usage,
                distinct_patient=True  # NEW flag
            )
            return SQLBinaryOp(
                operator="IS NOT",
                left=SQLQualifiedIdentifier(parts=[alias, "patient_id"]),
                right=SQLNull()
            )
        elif usage == ExprUsage.SCALAR:
            # Multi-row source used as scalar - ERROR or WARNING
            if self.strict_mode:
                raise TranslationError(
                    f"Definition '{name}' returns multiple rows per patient "
                    f"but is used in scalar context. Use First(), Last(), or "
                    f"singleton from to select a single value."
                )
            # Permissive: fall back to correlated subquery with LIMIT 1
            return self._build_correlated_subquery(name, limit=1)
    
    # PATIENT_SCALAR or PATIENT_BOOLEAN - safe to JOIN directly
    alias = self.context.query_builder.track_cte_reference(name, usage=usage)
    
    if usage == ExprUsage.SCALAR:
        return SQLQualifiedIdentifier(parts=[alias, "value"])
    else:  # BOOLEAN/EXISTS
        return SQLBinaryOp(
            operator="IS NOT",
            left=SQLQualifiedIdentifier(parts=[alias, "patient_id"]),
            right=SQLNull()
        )
```

### E.4 JOIN Generation with DISTINCT Option

```python
def generate_joins(self, patient_alias: str = "p") -> List[SQLJoin]:
    joins = []
    for ref in self.cte_references.values():
        if ref.distinct_patient:
            # JOIN against distinct patient_id keyset
            table = SQLSubquery(
                query=SQLSelect(
                    columns=[SQLIdentifier(name="patient_id")],
                    from_clause=SQLIdentifier(name=ref.cte_name, quoted=True),
                    distinct=True,
                )
            )
        else:
            table = SQLIdentifier(name=ref.cte_name, quoted=True)
        
        join = SQLJoin(
            join_type="LEFT",
            table=table,
            alias=ref.alias,
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=[ref.alias, "patient_id"]),
                right=SQLQualifiedIdentifier(parts=[patient_alias, "patient_id"]),
            ),
        )
        joins.append(join)
    return joins
```

---

## Appendix F: Design Review Feedback & Decisions (2025-02-24)

This section captures critical feedback from design review and the resulting architectural decisions.

### F.1 Outstanding Design Decisions

These decisions **must be finalized before implementation begins**:

| Issue | Decision | Rationale |
|-------|----------|-----------|
| Property access over collections | **Projection (RESOURCE_ROWS)** | Matches CQL semantics; downstream can aggregate when needed |
| Forward references | **Topological sort** | Clean, well-understood; errors on cycles |
| Same CTE, multiple contexts | **Unified JOIN, most permissive** | Single JOIN, context handled at usage site |
| RowShape inference | **Per-handler + propagation rules** | Simpler than full type inference pass |
| Late column additions | **Two-pass translation** | Pass 1 collects requirements, Pass 2 generates SQL |
| Priority 0 | **Merge context classes first** | Blocking issue for all other work |

---

### F.2 The "First Qualifying Row" Problem

**Problem**: Property access over a multi-row definition is underspecified.

```cql
define Diabetes: [Condition: "Diabetes"]
define Status: Diabetes.status  -- Which Diabetes? Patient may have 3.
```

CQL semantics: property access over a list returns a **list**, not a scalar.

**Decision**: Use **projection** (per-row output), producing `RESOURCE_ROWS` shape.

```sql
-- Diabetes.status produces RESOURCE_ROWS, not PATIENT_SCALAR
"DiabetesStatus" AS (
    SELECT d.patient_id, fhirpath_text(d.resource, 'status') AS status
    FROM "Diabetes" d
)
```

**Implications**:
- `Diabetes.status` produces `RESOURCE_ROWS` shape
- Downstream must aggregate explicitly: `First(Diabetes.status)`, `Count(Diabetes.status)`
- RowShape propagates: property access on `RESOURCE_ROWS` → `RESOURCE_ROWS`

**Alternative considered**: Aggregation via `list_agg()`. Rejected because:
- Loses individual resource identity
- Harder to apply subsequent `where` filters
- Less faithful to CQL semantics

---

### F.3 Forward References Are a Silent Footgun

**Problem**: If "HasDiabetes" is defined before "Diabetes" in the CQL file:
- `definition_meta` won't have an entry for "Diabetes" yet
- Fallback to correlated subquery silently kicks in
- Correct results but O(n²) performance, with **no warning**

**Decision**: **Topological sort before translation**.

```python
def _order_definitions(self, definitions: List[Definition]) -> List[Definition]:
    """
    Topologically sort definitions by dependency order.
    
    1. Build dependency graph by walking each definition's AST
    2. Find all identifier references to other definitions
    3. Topological sort (error on cycles)
    4. Return sorted list
    """
    graph = self._build_dependency_graph(definitions)
    return topological_sort(graph)  # Raises on cycle
```

**Error handling**: Cyclic dependencies raise `TranslationError` with cycle description.

**Implementation note**: This also naturally solves the "late column additions" problem—we know all downstream usages before generating any CTE.

---

### F.4 Same CTE Referenced in Multiple Contexts

**Problem**: A single definition referenced with different usages in one expression.

```cql
define Diabetes: [Condition: "Diabetes"]
define X: exists Diabetes and Diabetes.status = 'confirmed'
```

"Diabetes" is referenced twice:
1. `exists Diabetes` → EXISTS context (wants `IS NOT NULL`)
2. `Diabetes.status` → SCALAR context (wants `j1.resource`)

Current `SQLQueryBuilder` uses `cte_name` as dict key—second registration overwrites first.

**Decision**: **Unified JOIN with most permissive usage**.

Rules:
1. Track all usages for a given CTE during expression translation
2. When building JOINs, use the **most permissive** usage:
   - `RESOURCE_ROWS` reference: JOIN full CTE (no DISTINCT)
   - `EXISTS`-only reference: May use DISTINCT optimization
3. At each usage site, generate appropriate expression:
   - EXISTS → `j1.patient_id IS NOT NULL`
   - SCALAR → `j1.resource` or `j1.value`

**Updated CTEReference**:

```python
@dataclass
class CTEReference:
    cte_name: str
    alias: str
    usages: Set[ExprUsage] = field(default_factory=set)  # Track ALL usages
    patient_correlated: bool = True
    
    @property
    def can_use_distinct(self) -> bool:
        """DISTINCT only safe if ALL usages are EXISTS/BOOLEAN."""
        return self.usages.issubset({ExprUsage.EXISTS, ExprUsage.BOOLEAN})
```

**Updated tracking**:

```python
def track_cte_reference(self, cte_name: str, usage: ExprUsage) -> str:
    if cte_name in self.cte_references:
        # Add to existing usages
        self.cte_references[cte_name].usages.add(usage)
        return self.cte_references[cte_name].alias
    else:
        # New reference
        self.join_counter += 1
        alias = f"j{self.join_counter}"
        self.cte_references[cte_name] = CTEReference(
            cte_name=cte_name,
            alias=alias,
            usages={usage},
        )
        return alias
```

---

### F.5 DISTINCT Optimization Constraints

**Problem**: The DISTINCT optimization can produce wrong results for non-boolean contexts.

```cql
define Diabetes: [Condition: "Diabetes"]
define HasTwoDiabetes: Count(Diabetes) >= 2
```

If DISTINCT is applied before `Count()`, the count is always ≤1.

**Decision**: DISTINCT-patient joins are **only** valid when:
1. The **entire** reference is EXISTS/BOOLEAN context
2. No other usage of that CTE requires resource/value access

**Enforcement**:

```python
def generate_joins(self, patient_alias: str = "p") -> List[SQLJoin]:
    joins = []
    for ref in self.cte_references.values():
        # DISTINCT only if ALL usages are existence checks
        use_distinct = ref.can_use_distinct
        
        if use_distinct:
            table = SQLSubquery(
                query=SQLSelect(
                    columns=[SQLIdentifier(name="patient_id")],
                    from_clause=SQLIdentifier(name=ref.cte_name, quoted=True),
                    distinct=True,
                )
            )
        else:
            # Full CTE join - no DISTINCT
            table = SQLIdentifier(name=ref.cte_name, quoted=True)
        
        # ... build JOIN ...
```

---

### F.6 RowShape Inference Rules

**Problem**: Shape inference is non-trivial and depends on full expression tree.

```cql
define A: [Condition: "Diabetes"]          -- RESOURCE_ROWS
define B: exists A                          -- PATIENT_SCALAR
define C: First(A)                          -- PATIENT_SCALAR
define D: A.status                          -- RESOURCE_ROWS (projection)
define E: if exists A then 'yes' else 'no'  -- PATIENT_SCALAR
define F: A union [Observation: "X"]        -- RESOURCE_ROWS
```

**Decision**: **Per-handler inference with propagation rules**.

| Expression Type | Input Shape | Output Shape |
|-----------------|-------------|--------------|
| Retrieve | N/A | RESOURCE_ROWS |
| `exists` | Any | PATIENT_SCALAR |
| `First`, `Last`, `singleton from` | RESOURCE_ROWS | PATIENT_SCALAR |
| `Count`, `Sum`, `Avg`, `Min`, `Max` | Any | PATIENT_SCALAR |
| Property access | RESOURCE_ROWS | RESOURCE_ROWS |
| Property access | PATIENT_SCALAR | PATIENT_SCALAR |
| `union`, `intersect`, `except` | RESOURCE_ROWS | RESOURCE_ROWS |
| `if`/`case` (boolean condition) | N/A | Shape of then/else branches |
| Binary comparison (`=`, `>`, etc.) | Any | PATIENT_SCALAR |
| Logical operators (`and`, `or`) | Any | PATIENT_SCALAR |

**Implementation**:

```python
def _infer_row_shape(self, ast_node: Any) -> RowShape:
    """Infer row shape from AST node type."""
    
    if isinstance(ast_node, Retrieve):
        return RowShape.RESOURCE_ROWS
    
    if isinstance(ast_node, ExistsExpression):
        return RowShape.PATIENT_SCALAR
    
    if isinstance(ast_node, (FirstExpression, LastExpression, SingletonExpression)):
        return RowShape.PATIENT_SCALAR
    
    if isinstance(ast_node, FunctionRef):
        if ast_node.name.lower() in ('count', 'sum', 'avg', 'min', 'max'):
            return RowShape.PATIENT_SCALAR
    
    if isinstance(ast_node, Property):
        source_shape = self._infer_row_shape(ast_node.source)
        return source_shape  # Propagate
    
    if isinstance(ast_node, BinaryExpression):
        if ast_node.operator in ('=', '!=', '<', '>', '<=', '>=', 'and', 'or'):
            return RowShape.PATIENT_SCALAR
        if ast_node.operator in ('union', 'intersect', 'except'):
            return RowShape.RESOURCE_ROWS
    
    if isinstance(ast_node, ConditionalExpression):
        then_shape = self._infer_row_shape(ast_node.then_expr)
        else_shape = self._infer_row_shape(ast_node.else_expr)
        # If either is RESOURCE_ROWS, result is RESOURCE_ROWS
        if then_shape == RowShape.RESOURCE_ROWS or else_shape == RowShape.RESOURCE_ROWS:
            return RowShape.RESOURCE_ROWS
        return RowShape.PATIENT_SCALAR
    
    # Default: unknown, treat conservatively
    return RowShape.UNKNOWN
```

---

### F.7 Two-Pass Translation Architecture

**Problem**: Column registry can't help if columns weren't generated in the CTE.

**Decision**: **Two-pass translation**.

**Pass 1: Analysis**
- Parse all definitions
- Topologically sort by dependencies
- For each definition, walk AST to collect:
  - Property accesses per resource type
  - Definition references and their usage contexts
  - Aggregate functions used

**Pass 2: Generation**
- Build CTEs in dependency order
- Include all precomputed columns needed by downstream definitions
- Generate JOINs with full knowledge of usage patterns

```python
def translate_library(self, library: Library) -> str:
    # Pass 1: Analyze
    definitions = library.definitions
    sorted_defs = self._topological_sort(definitions)
    
    analysis = {}
    for defn in sorted_defs:
        analysis[defn.name] = self._analyze_definition(defn)
    
    # Compute required columns per CTE
    required_columns = self._compute_required_columns(analysis)
    
    # Pass 2: Generate
    ctes = []
    for defn in sorted_defs:
        columns = required_columns.get(defn.name, set())
        cte = self._generate_cte(defn, columns, analysis)
        ctes.append(cte)
        
        # Record metadata for downstream references
        self._context.definition_meta[defn.name] = DefinitionMeta(
            name=defn.name,
            shape=self._infer_row_shape(defn.expression),
            has_resource='resource' in cte.columns,
        )
    
    return self._assemble_sql(ctes)
```

---

### F.8 Fresh Query Builder Per Definition (Clarification)

**Problem**: The original doc said "don't clear query_builder early" but the real issue is that `query_builder` is shared globally.

**Clarification**: The fix is **not** "delayed clearing"—it's **fresh builder per definition**.

```python
def _translate_definition_to_cte(self, defn: Definition) -> CTEDefinition:
    # CORRECT: Fresh builder for this definition's scope
    query_builder = SQLQueryBuilder()
    
    # Store temporarily for expression translator
    old_builder = self._context.query_builder
    self._context.query_builder = query_builder
    
    try:
        # Translate expression - registers JOINs in fresh builder
        expr = self._translate_expression(defn.expression)
        
        # Extract JOINs immediately
        joins = query_builder.generate_joins()
        
        # Build CTE with those JOINs
        return self._build_cte(defn.name, expr, joins)
    finally:
        # Restore (not clear!)
        self._context.query_builder = old_builder
```

**Key insight**: Each CTE is its own scope. JOINs from "Diabetes" translation must **not** leak into "HasDiabetes" CTE.

---

### F.9 Testing Strategy Improvements

**Problem**: String-matching tests (`assert "LEFT JOIN" in sql`) are fragile and don't validate correctness.

**Decision**: **Result-based testing with boundary cases**.

**Required test fixtures**:
| Patient | Conditions | Expected for `exists` | Expected for `Count() >= 2` |
|---------|------------|----------------------|----------------------------|
| P1 | 0 | false | false |
| P2 | 1 | true | false |
| P3 | 3 | true | true |

**Test pattern**:

```python
def test_exists_no_fanout():
    """Patients must appear exactly once regardless of resource count."""
    cql = '''
        define Diabetes: [Condition: "Diabetes"]
        define HasDiabetes: exists Diabetes
    '''
    
    # P3 has 3 diabetes conditions
    result = evaluate_cql(cql, test_db)
    
    # P3 should appear exactly once
    p3_rows = result[result['patient_id'] == 'P3']
    assert len(p3_rows) == 1
    assert p3_rows.iloc[0]['HasDiabetes'] == True

def test_count_not_affected_by_distinct():
    """Count must see all rows, not DISTINCT patient_id."""
    cql = '''
        define Diabetes: [Condition: "Diabetes"]
        define DiabetesCount: Count(Diabetes)
    '''
    
    result = evaluate_cql(cql, test_db)
    
    # P3 has 3 diabetes conditions
    p3_count = result[result['patient_id'] == 'P3']['DiabetesCount'].iloc[0]
    assert p3_count == 3  # Not 1!
```

**String tests are supplementary**, not primary:

```python
def test_join_structure():
    """Verify JOIN is generated (supplementary to result test)."""
    sql = translate_cql(cql)
    
    # Primary: result correctness (see above)
    # Secondary: structure check
    assert "LEFT JOIN" in sql
    assert "SELECT DISTINCT" not in sql  # Count needs all rows
```

---

### F.10 Clarification: Intra-CTE vs Inter-CTE Correlation

**Problem**: The O(n²) issue is about correlated subqueries **within** a CTE, not between CTEs.

**Clarification**:

```sql
-- SLOW: Correlated subquery WITHIN "HasDiabetes" CTE
"HasDiabetes" AS (
    SELECT p.patient_id,
           EXISTS (SELECT 1 FROM "Diabetes" d WHERE d.patient_id = p.patient_id)
    --     ^^^^^^^ Executes once per patient row in _patients
    FROM _patients p
)

-- FAST: JOIN WITHIN "HasDiabetes" CTE
"HasDiabetes" AS (
    SELECT p.patient_id, j1.patient_id IS NOT NULL AS value
    FROM _patients p
    LEFT JOIN "Diabetes" j1 ON j1.patient_id = p.patient_id
    --        ^^^^^^^ Single JOIN operation
)
```

DuckDB materializes CTEs, so referencing `"Diabetes"` CTE multiple times doesn't re-execute its query. The cost is the **per-row subquery execution** within a single CTE's SELECT list.

This distinction matters because engineers might incorrectly think "DuckDB materializes CTEs so subqueries only run once."

---

### F.11 Implementation Priority Order (Revised)

Based on feedback, the implementation order is:

| Priority | Task | Rationale |
|----------|------|-----------|
| **0** | Merge two `SQLTranslationContext` classes | Blocker for all other work |
| **1** | Standardize `patient_id` column | Silent JOIN failures if inconsistent |
| **2** | Topological sort for definitions | Prevents silent O(n²) fallback |
| **3** | Add `RowShape` enum and `DefinitionMeta` | Foundation for safe JOINs |
| **4** | Fresh `SQLQueryBuilder` per definition | Correct scope isolation |
| **5** | Shape-aware JOIN conversion | Core optimization |
| **6** | Multi-usage CTE tracking | Handles `exists A and A.status` |
| **7** | Two-pass translation (analysis + generation) | Enables column registry |
| **8** | Column registry integration | Performance optimization |
| **9** | Result-based test suite | Validation |

---

### F.12 Open Questions (Deferred)

These issues are noted but deferred to future iterations:

1. **List-valued outputs**: How to represent `Diabetes.status` (list of strings) in final SELECT?
   - Option A: JSON array column
   - Option B: Comma-separated string
   - Option C: Separate rows (current projection approach)

2. **Strict mode UX**: How to surface warnings in permissive mode? Logging? Return value? Callback?

3. **Cycle detection messaging**: What's the best error message format for cyclic definition dependencies?

---

## Appendix G: Additional Critical Gaps (2025-02-24)

This section captures additional critical issues identified in follow-up review.

### G.1 The Cartesian Fanout Problem (CRITICAL)

**Problem**: LEFT JOINing multiple `RESOURCE_ROWS` CTEs to `_patients` creates a Cartesian product.

```cql
define Diabetes: [Condition: "Diabetes"]        -- 3 rows for Patient A
define Hypertension: [Condition: "Hypertension"] -- 2 rows for Patient A
define Combined: Diabetes.status and Hypertension.status
```

**What current design generates**:
```sql
"Combined" AS (
    SELECT p.patient_id, (j1.status AND j2.status) AS value
    FROM _patients p
    LEFT JOIN "Diabetes" j1 ON j1.patient_id = p.patient_id
    LEFT JOIN "Hypertension" j2 ON j2.patient_id = p.patient_id
)
```

**The Bug**: Patient A gets **6 rows** (3 × 2), corrupting all downstream aggregations.

**Root Cause**: You cannot blindly LEFT JOIN multiple `RESOURCE_ROWS` into the same flat scope.

**Proposed Solutions** (choose one or combine):

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| **Pre-aggregate to LIST** | `list_agg()` resources before JOIN | No fanout; clean SQL | Loses row identity |
| **LATERAL joins** | `CROSS JOIN LATERAL (SELECT ... LIMIT 1)` | Controlled cardinality | Complex SQL |
| **Detect and warn** | Error if multiple RESOURCE_ROWS JOINed in same scope | Prevents silent bugs | Limits CQL expressiveness |
| **Correlated subquery fallback** | Keep as subqueries when multiple RESOURCE_ROWS | Correct semantics | O(n²) performance |

**Recommended Decision**: **Pre-aggregate to LIST** for boolean/scalar contexts:

```sql
"Combined" AS (
    SELECT p.patient_id,
           (SELECT bool_and(fhirpath_text(d.resource, 'status'))
            FROM "Diabetes" d WHERE d.patient_id = p.patient_id)
           AND
           (SELECT bool_and(fhirpath_text(h.resource, 'status'))
            FROM "Hypertension" h WHERE h.patient_id = p.patient_id)
           AS value
    FROM _patients p
)
```

Or use DuckDB array functions:

```sql
"Combined" AS (
    SELECT p.patient_id,
           list_bool_and(j1.statuses) AND list_bool_and(j2.statuses) AS value
    FROM _patients p
    LEFT JOIN (
        SELECT patient_id, list(fhirpath_text(resource, 'status')) AS statuses
        FROM "Diabetes" GROUP BY patient_id
    ) j1 ON j1.patient_id = p.patient_id
    LEFT JOIN (
        SELECT patient_id, list(fhirpath_text(resource, 'status')) AS statuses
        FROM "Hypertension" GROUP BY patient_id
    ) j2 ON j2.patient_id = p.patient_id
)
```

**Implementation**: Add `multi_resource_row_references` detection to `SQLQueryBuilder`:

```python
def validate_joins(self) -> None:
    """Check for Cartesian fanout risk."""
    resource_row_refs = [
        ref for ref in self.cte_references.values()
        if ref.shape == RowShape.RESOURCE_ROWS and not ref.can_use_distinct
    ]
    if len(resource_row_refs) > 1:
        if self.strict_mode:
            raise TranslationError(
                f"Multiple RESOURCE_ROWS CTEs JOINed in same scope: "
                f"{[r.cte_name for r in resource_row_refs]}. "
                f"This causes Cartesian fanout."
            )
        else:
            # Fall back to pre-aggregation or correlated subqueries
            self._use_aggregation_strategy = True
```

---

### G.2 Inter-Resource Correlation (HIGH)

**Problem**: `generate_joins()` hardcodes `ON j1.patient_id = p.patient_id`, but CQL often correlates resources to *each other*.

```cql
define Diabetes: [Condition: "Diabetes"]
define A1C: [Observation: "HbA1c"]
define DiabetesWithA1C: 
    Diabetes D with A1C O such that O.effective > D.onset
```

**Required JOIN condition**:
```sql
LEFT JOIN "A1C" j2 ON j2.patient_id = j1.patient_id 
                   AND j2.effective > j1.onset  -- Non-patient correlation!
```

**Current Limitation**: `CTEReference` lacks ability to capture non-patient predicates.

**Proposed Extension**:

```python
@dataclass
class CTEReference:
    cte_name: str
    alias: str
    usages: Set[ExprUsage] = field(default_factory=set)
    patient_correlated: bool = True
    
    # NEW: Additional correlation predicates beyond patient_id
    additional_predicates: List[SQLExpression] = field(default_factory=list)
    
    # NEW: Which alias this correlates to (if not _patients)
    correlates_to_alias: Optional[str] = None  # e.g., "j1" for inter-resource
```

**Updated `generate_joins()`**:

```python
def generate_joins(self, patient_alias: str = "p") -> List[SQLJoin]:
    joins = []
    for ref in self.cte_references.values():
        # Determine correlation target
        if ref.correlates_to_alias:
            correlation_alias = ref.correlates_to_alias
        else:
            correlation_alias = patient_alias
        
        # Build ON condition
        on_condition = SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=[ref.alias, "patient_id"]),
            right=SQLQualifiedIdentifier(parts=[correlation_alias, "patient_id"]),
        )
        
        # Add additional predicates (e.g., O.effective > D.onset)
        for predicate in ref.additional_predicates:
            on_condition = SQLBinaryOp(
                operator="AND",
                left=on_condition,
                right=predicate,
            )
        
        join = SQLJoin(join_type="LEFT", table=..., alias=ref.alias, on_condition=on_condition)
        joins.append(join)
    
    return joins
```

---

### G.3 Conditional Fanout in Logical Branches (HIGH)

**Problem**: SQL evaluates LEFT JOINs for entire table regardless of `CASE`/`IF` usage.

```cql
define HasSevereRisk: true
define SevereConditions: [Condition: "Severe"]  -- RESOURCE_ROWS
define MildConditions: [Condition: "Mild"]       -- RESOURCE_ROWS

define RelevantConditions:
    if HasSevereRisk then SevereConditions else MildConditions
```

**What current design generates**:
```sql
"RelevantConditions" AS (
    SELECT p.patient_id,
           CASE WHEN j_risk.value THEN j_severe.resource ELSE j_mild.resource END
    FROM _patients p
    LEFT JOIN "HasSevereRisk" j_risk ON ...
    LEFT JOIN "SevereConditions" j_severe ON ...  -- Always evaluated!
    LEFT JOIN "MildConditions" j_mild ON ...       -- Always evaluated!
)
```

**The Bug**: Both `SevereConditions` AND `MildConditions` are JOINed, creating massive fanout even though only one branch is logically selected.

**Root Cause**: Standard LEFT JOINs cannot be "conditionally executed."

**Proposed Solutions**:

| Approach | Description |
|----------|-------------|
| **LATERAL with CASE** | Use `CROSS JOIN LATERAL (SELECT CASE WHEN ... THEN (subquery1) ELSE (subquery2) END)` |
| **UNION with filter** | `SELECT ... WHERE risk UNION ALL SELECT ... WHERE NOT risk` |
| **Correlated subquery** | Keep RESOURCE_ROWS in conditional branches as subqueries |
| **Detect and warn** | Error/warn when RESOURCE_ROWS appear in both branches of conditional |

**Recommended**: Detect `RESOURCE_ROWS` in conditional branches and use **correlated subquery** pattern:

```sql
"RelevantConditions" AS (
    SELECT p.patient_id,
           CASE WHEN (SELECT value FROM "HasSevereRisk" WHERE patient_id = p.patient_id)
                THEN (SELECT resource FROM "SevereConditions" WHERE patient_id = p.patient_id)
                ELSE (SELECT resource FROM "MildConditions" WHERE patient_id = p.patient_id)
           END AS resource
    FROM _patients p
)
```

This is O(n) with subquery caching, not O(n²), because condition evaluation prevents unnecessary subquery execution.

---

### G.4 Self-Joins and Alias Collisions (MEDIUM)

**Problem**: Keying `CTEReference` by `cte_name` breaks deliberate self-joins.

```cql
define Encounters: [Encounter]
define BackToBack:
    from Encounters E1, Encounters E2
    where E2.start = E1.end
```

**The Bug**: If `cte_references` keys by `cte_name` ("Encounters"), `E2` overwrites `E1`.

**Required**: Two distinct JOIN aliases pointing to same CTE.

**Proposed Fix**: Key by `(cte_name, semantic_alias)`:

```python
@dataclass
class CTEReference:
    cte_name: str
    semantic_alias: str  # NEW: The CQL alias (E1, E2, etc.)
    alias: str           # SQL alias (j1, j2, etc.)
    # ...

class SQLQueryBuilder:
    def track_cte_reference(
        self, 
        cte_name: str, 
        semantic_alias: Optional[str] = None,  # NEW
        usage: ExprUsage = ExprUsage.SCALAR
    ) -> str:
        # Key by (cte_name, semantic_alias) to allow multiple refs to same CTE
        key = (cte_name, semantic_alias or cte_name)
        
        if key in self.cte_references:
            self.cte_references[key].usages.add(usage)
            return self.cte_references[key].alias
        else:
            self.join_counter += 1
            alias = f"j{self.join_counter}"
            self.cte_references[key] = CTEReference(
                cte_name=cte_name,
                semantic_alias=semantic_alias or cte_name,
                alias=alias,
                usages={usage},
            )
            return alias
```

**Query translation for self-join**:
```sql
"BackToBack" AS (
    SELECT p.patient_id, ...
    FROM _patients p
    LEFT JOIN "Encounters" j1 ON j1.patient_id = p.patient_id  -- E1
    LEFT JOIN "Encounters" j2 ON j2.patient_id = p.patient_id  -- E2
                              AND j2.start = j1.end             -- Correlation
)
```

---

### G.5 Determinism in First() and Last() (MEDIUM)

**Problem**: SQL tables are unordered. `First(A)` without `ORDER BY` is non-deterministic.

```cql
define Conditions: [Condition]
define FirstCondition: First(Conditions)
```

**Current behavior**: Generates `LIMIT 1` without `ORDER BY`.

**The Bug**: Different runs may return different "first" condition.

**CQL Semantics**: CQL spec doesn't define order, but clinical practice typically expects:
- Most recent (by `effective_date`, `onset_date`, `recorded_date`)
- Or order of appearance in source data

**Proposed Fix**: Inject `ORDER BY` based on resource type:

```python
# In types.py or config
DEFAULT_SORT_COLUMNS = {
    "Condition": ["onset_date DESC", "recorded_date DESC"],
    "Observation": ["effective_date DESC"],
    "Encounter": ["period_start DESC"],
    "Procedure": ["performed_date DESC"],
    "MedicationRequest": ["authored_on DESC"],
}

def _translate_first_expression(self, expr: FirstExpression) -> SQLExpression:
    source_sql = self.translate(expr.source)
    resource_type = self._infer_resource_type(expr.source)
    
    order_cols = DEFAULT_SORT_COLUMNS.get(resource_type, [])
    order_clause = ", ".join(order_cols) if order_cols else "1"  # Fallback
    
    return SQLSubquery(
        query=SQLSelect(
            columns=[SQLIdentifier(name="*")],
            from_clause=source_sql,
            order_by=order_clause,
            limit=1,
        )
    )
```

Or use `ROW_NUMBER()` window function:

```sql
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY onset_date DESC) AS rn
    FROM "Conditions"
) WHERE rn = 1
```

---

### G.6 The 3-Valued Logic (3VL) Null Trap (MEDIUM)

**Problem**: CQL and SQL handle NULL/missing data differently.

| Expression | CQL Result | SQL Result |
|------------|------------|------------|
| `exists {}` | `false` | N/A (no equivalent) |
| `{}.status = 'x'` | `{}` (empty) | `NULL` |
| `not (NULL = 'x')` | `NULL` | `NULL` |
| Empty list in boolean context | `false` or `null`? | `NULL` |

**The Bug**: Translating `not (Diabetes.status = 'confirmed')` when patient has no diabetes:

```sql
-- Patient has no diabetes, so j1.resource is NULL
SELECT p.patient_id, NOT (fhirpath_text(j1.resource, 'status') = 'confirmed')
-- fhirpath_text(NULL, 'status') = NULL
-- NULL = 'confirmed' = NULL
-- NOT NULL = NULL
```

CQL might expect `true` (no diabetes means "not confirmed diabetes").

**Proposed Fix**: Wrap boolean expressions in `COALESCE` when `ExprUsage.BOOLEAN`:

```python
def _wrap_for_boolean_context(self, expr: SQLExpression, usage: ExprUsage) -> SQLExpression:
    if usage == ExprUsage.BOOLEAN:
        # Ensure NULL becomes FALSE in boolean context
        return SQLFunctionCall(
            name="COALESCE",
            args=[expr, SQLLiteral(value=False)]
        )
    return expr
```

**When to apply**:
- Comparison results in WHERE clause
- NOT operand
- AND/OR operands where one side might be NULL

**Caution**: This changes semantics. Need to validate against CQL spec for null propagation rules.

---

### G.7 Updated Implementation Priority (Revised)

Based on these additional gaps, revised priority:

| Priority | Task | Severity |
|----------|------|----------|
| **0** | Merge context classes | BLOCKING |
| **1** | Standardize patient_id | HIGH |
| **2** | Topological sort | HIGH |
| **3** | RowShape + DefinitionMeta | HIGH |
| **4** | Fresh query builder per definition | HIGH |
| **5** | Multi-usage CTE tracking | HIGH |
| **6** | **Cartesian fanout detection** | CRITICAL |
| **7** | **Self-join alias keying** | MEDIUM |
| **8** | **Inter-resource correlation predicates** | HIGH |
| **9** | **Conditional RESOURCE_ROWS handling** | HIGH |
| **10** | **First()/Last() ORDER BY** | MEDIUM |
| **11** | **3VL null handling** | MEDIUM |
| **12** | Column registry | MEDIUM |
| **13** | Two-pass translation | MEDIUM |

---

### G.8 Architectural Implication: Hybrid JOIN + Subquery Strategy

The gaps in G.1-G.4 suggest that **pure JOIN conversion is not always safe**. The architecture needs a **hybrid strategy**:

```
For each definition reference:
    1. Determine source shape (RESOURCE_ROWS, PATIENT_SCALAR, etc.)
    2. Determine usage context (EXISTS, SCALAR, BOOLEAN, LIST)
    3. Check for multi-RESOURCE_ROWS in same scope
    4. Check for conditional branches with RESOURCE_ROWS
    5. Check for inter-resource correlation requirements
    
    If any complexity detected:
        → Use correlated subquery or aggregation strategy
    Else if single RESOURCE_ROWS with simple patient correlation:
        → Use JOIN (fast path)
    Else:
        → Use JOIN for PATIENT_SCALAR sources
```

This means `SQLQueryBuilder` needs a `strategy: Literal["join", "subquery", "aggregate"]` field per reference, not just usage tracking.

---

## Appendix H: Operational & Robustness Gaps (2025-02-24)

This section captures operational, security, and robustness concerns from final review.

### H.1 Database Engine Semantics & Optimizer Variability (HIGH)

**Problem**: CTE materialization, optimizer behavior, and JOIN strategies differ between engines.

| Engine | CTE Behavior | LATERAL Support | Semi-Join Optimization |
|--------|--------------|-----------------|------------------------|
| DuckDB | Materialized | Yes | Good |
| PostgreSQL | May inline | Yes (CROSS APPLY) | Good |
| BigQuery | Varies | No (use correlated) | Limited |
| SQLite | Materialized | No | Poor |

**Effects**:
- Correlated subqueries may be optimized into semi-joins (or not)
- `LEFT JOIN + IS NOT NULL` vs `EXISTS` have different plans
- LATERAL preferred on some engines, unavailable on others

**Required**: Engine capability abstraction.

```python
@dataclass
class EngineCapabilities:
    """Database engine capabilities for SQL generation."""
    name: str
    supports_lateral: bool = False
    supports_jsonb: bool = False
    supports_cte_materialization: bool = True
    supports_window_functions: bool = True
    max_identifier_length: int = 128
    prefers_exists_over_left_join: bool = False

ENGINE_CAPABILITIES = {
    "duckdb": EngineCapabilities(
        name="duckdb",
        supports_lateral=True,
        supports_jsonb=True,
        max_identifier_length=256,
    ),
    "postgresql": EngineCapabilities(
        name="postgresql",
        supports_lateral=True,
        supports_jsonb=True,
        max_identifier_length=63,
        prefers_exists_over_left_join=True,
    ),
    "sqlite": EngineCapabilities(
        name="sqlite",
        supports_lateral=False,
        supports_jsonb=False,
        max_identifier_length=128,
    ),
}
```

**Action Items**:
- [ ] Add `engine: str` parameter to translator
- [ ] Create `EngineCapabilities` config
- [ ] Branch code paths based on capabilities
- [ ] Add integration tests per engine

---

### H.2 Aggregation Correctness Rule Table (HIGH)

**Problem**: When converting RESOURCE_ROWS to JOINs, different downstream operators need different SQL patterns.

**Rule Table**:

| Downstream Op | Source Shape | SQL Pattern | GROUP BY? |
|---------------|--------------|-------------|-----------|
| `exists` | RESOURCE_ROWS | `LEFT JOIN (DISTINCT patient_id)` | No |
| `Count` | RESOURCE_ROWS | Correlated subquery OR `LEFT JOIN + GROUP BY` | Yes |
| `First` | RESOURCE_ROWS | `LATERAL (LIMIT 1)` OR `ROW_NUMBER()` | No |
| `Sum/Avg/Min/Max` | RESOURCE_ROWS | Correlated subquery OR `GROUP BY` | Yes |
| Property access | RESOURCE_ROWS | Keep as RESOURCE_ROWS (projection) | No |
| Boolean comparison | RESOURCE_ROWS | **Error** unless aggregated | N/A |

**Implementation**:

```python
def _select_aggregation_strategy(
    self, 
    source_shape: RowShape, 
    downstream_op: str
) -> AggregationStrategy:
    """Select SQL pattern based on source shape and downstream operation."""
    
    if source_shape != RowShape.RESOURCE_ROWS:
        return AggregationStrategy.DIRECT_JOIN
    
    if downstream_op == "exists":
        return AggregationStrategy.DISTINCT_JOIN
    elif downstream_op in ("Count", "Sum", "Avg", "Min", "Max"):
        return AggregationStrategy.CORRELATED_AGGREGATE
    elif downstream_op == "First":
        if self.engine.supports_lateral:
            return AggregationStrategy.LATERAL_LIMIT
        else:
            return AggregationStrategy.ROW_NUMBER_WINDOW
    elif downstream_op == "property_access":
        return AggregationStrategy.KEEP_RESOURCE_ROWS
    else:
        # Scalar comparison on multi-row - error
        raise TranslationError(
            f"Cannot use RESOURCE_ROWS in scalar context for {downstream_op}. "
            f"Use First(), Count(), or exists() to aggregate."
        )
```

---

### H.3 List-Valued Output Semantics (MEDIUM)

**Problem**: No clear default for how list-valued definitions appear in final output.

**Decision**: Default to **scalar columns** for patient-level outputs.

**Rules**:
1. If definition shape is `PATIENT_SCALAR` → scalar column
2. If definition shape is `RESOURCE_ROWS` → **require explicit aggregation**
3. If user wants list output → use explicit `collect()` or return JSON array

**Implementation**:

```python
def _validate_output_columns(self, output_columns: Dict[str, str]) -> None:
    """Ensure all output columns have scalar shape."""
    for col_name, def_name in output_columns.items():
        meta = self._context.definition_meta.get(def_name)
        if meta and meta.shape == RowShape.RESOURCE_ROWS:
            raise TranslationError(
                f"Output column '{col_name}' references '{def_name}' which has "
                f"RESOURCE_ROWS shape. Use First(), Count(), or exists() to "
                f"produce a scalar value, or use collect() for a list."
            )
```

---

### H.4 CQL Type Metadata Propagation (HIGH)

**Problem**: `RowShape` tracks cardinality but not CQL type (string, date, resource, boolean).

**Extended `DefinitionMeta`**:

```python
@dataclass
class DefinitionMeta:
    name: str
    shape: RowShape
    cql_type: str = "Any"  # NEW: Boolean, Integer, String, DateTime, Resource, List<T>
    cardinality: str = "0..*"  # NEW: 0..1, 1, 0..*
    has_resource: bool = False
    value_column: str = "value"
    patient_key_col: str = "patient_id"
    
    @property
    def is_scalar(self) -> bool:
        return self.cardinality in ("0..1", "1")
    
    @property
    def is_resource_type(self) -> bool:
        return self.cql_type.startswith("Resource") or self.cql_type in FHIR_RESOURCE_TYPES
```

**Type inference additions**:

| Expression | CQL Type | Cardinality |
|------------|----------|-------------|
| `[Condition]` | `List<Condition>` | `0..*` |
| `exists [Condition]` | `Boolean` | `1` |
| `First([Condition])` | `Condition` | `0..1` |
| `Count([Condition])` | `Integer` | `1` |
| `Condition.status` | `List<String>` | `0..*` |
| `First(Condition).status` | `String` | `0..1` |

---

### H.5 Template Security (SQL Injection Risk) (MEDIUM)

**Problem**: `_substitute_template()` uses string replacement, risking:
- Quoting/escaping bugs
- Invalid SQL if arguments contain quotes
- Security risk if user-provided strings reach templates

**Current (Unsafe)**:
```python
result = template.replace("{resource}", resource_sql)  # String substitution
```

**Recommended (Safe)**: Build templates at AST level.

```python
def _substitute_template_ast(
    self,
    template_ast: SQLExpression,  # Pre-parsed template
    substitutions: Dict[str, SQLExpression],
) -> SQLExpression:
    """Substitute at AST level - no string manipulation."""
    return template_ast.substitute(substitutions)
```

**If string substitution must remain**:

```python
def _safe_substitute(self, template: str, substitutions: Dict[str, str]) -> str:
    """Safe substitution with validation."""
    result = template
    for key, value in substitutions.items():
        # Validate that value is a safe identifier/alias
        if not self._is_safe_identifier(value):
            raise TranslationError(f"Unsafe substitution value: {value}")
        result = result.replace(f"{{{key}}}", value)
    return result

def _is_safe_identifier(self, value: str) -> bool:
    """Check if value is a safe SQL identifier."""
    # Allow: quoted identifiers, simple names, qualified names
    return bool(re.match(r'^("[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?)$', value))
```

---

### H.6 Alias Collision & Length Limits (LOW)

**Problem**: 
- `j1`, `j2` aliases may collide if translators run concurrently
- Long CTE names may exceed DB identifier limits

**Solutions**:

```python
class AliasGenerator:
    """Thread-safe, deterministic alias generation."""
    
    def __init__(self, max_length: int = 63):
        self._counter = 0
        self._lock = threading.Lock()
        self._max_length = max_length
    
    def generate(self, prefix: str = "j") -> str:
        with self._lock:
            self._counter += 1
            return f"{prefix}{self._counter}"
    
    def safe_cte_name(self, name: str) -> str:
        """Truncate and hash long names."""
        if len(name) <= self._max_length:
            return name
        # Hash suffix for uniqueness
        hash_suffix = hashlib.md5(name.encode()).hexdigest()[:8]
        truncated = name[:self._max_length - 9]
        return f"{truncated}_{hash_suffix}"
```

---

### H.7 Forward Fallback Warnings (HIGH)

**Problem**: Silent fallback to correlated subquery is a performance footgun.

**Solution**: Instrument translator to emit warnings.

```python
class TranslationWarnings:
    """Collect and report translation warnings."""
    
    def __init__(self):
        self.warnings: List[TranslationWarning] = []
    
    def add(self, category: str, message: str, definition: str, suggestion: str):
        self.warnings.append(TranslationWarning(
            category=category,
            message=message,
            definition=definition,
            suggestion=suggestion,
        ))
    
    def report(self) -> str:
        if not self.warnings:
            return ""
        lines = ["Translation Warnings:"]
        for w in self.warnings:
            lines.append(f"  [{w.category}] {w.definition}: {w.message}")
            lines.append(f"    Suggestion: {w.suggestion}")
        return "\n".join(lines)

# Usage in translator
if meta is None:
    self._warnings.add(
        category="PERFORMANCE",
        message="Forward reference caused fallback to correlated subquery",
        definition=name,
        suggestion="Reorder definitions or use topological sort"
    )
```

**CI Integration**:
```python
def translate_library(self, library: Library, strict: bool = False) -> TranslationResult:
    result = self._do_translation(library)
    
    if strict and result.warnings:
        raise TranslationError(
            f"Translation produced warnings in strict mode:\n{result.warnings.report()}"
        )
    
    return result
```

---

### H.8 Column Registry Lifecycle (MEDIUM)

**Problem**: When CTEs are unioned, precomputed columns may exist in some branches but not others.

**Solution**: Track column availability per CTE and handle unions.

```python
@dataclass
class ColumnAvailability:
    column_name: str
    fhirpath: str
    available_in_all_branches: bool = True
    branches_present: Set[str] = field(default_factory=set)

class ColumnRegistry:
    def register_cte(self, cte_name: str, columns: Dict[str, ColumnInfo]) -> None:
        self._columns[cte_name] = columns
    
    def register_union(self, union_name: str, branch_names: List[str]) -> None:
        """Register a union CTE with columns from branches."""
        # Only include columns present in ALL branches
        common_columns = None
        for branch in branch_names:
            branch_cols = set(self._columns.get(branch, {}).keys())
            if common_columns is None:
                common_columns = branch_cols
            else:
                common_columns &= branch_cols
        
        # Register only common columns for the union
        union_cols = {}
        for col in (common_columns or set()):
            # Use column info from first branch
            first_branch = branch_names[0]
            if col in self._columns.get(first_branch, {}):
                union_cols[col] = self._columns[first_branch][col]
        
        self._columns[union_name] = union_cols
    
    def lookup(self, cte_name: str, fhirpath: str) -> Optional[str]:
        """Look up column, falling back to fhirpath if not available."""
        # ... existing lookup logic ...
```

---

### H.9 Instrumentation & EXPLAIN Capture (LOW)

**Purpose**: Detect query plan regressions in CI.

```python
class ExplainHarness:
    """Capture and analyze EXPLAIN plans for generated SQL."""
    
    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn
    
    def explain(self, sql: str) -> Dict[str, Any]:
        """Get EXPLAIN plan as structured data."""
        explain_sql = f"EXPLAIN ANALYZE {sql}"
        result = self.conn.execute(explain_sql).fetchall()
        return self._parse_explain(result)
    
    def check_for_regressions(self, sql: str) -> List[str]:
        """Check for known performance anti-patterns."""
        plan = self.explain(sql)
        issues = []
        
        # Check for nested loop joins (often bad)
        if "NESTED_LOOP" in str(plan):
            issues.append("Nested loop join detected - may indicate correlated subquery")
        
        # Check for sequential scans on large tables
        if "SEQ_SCAN" in str(plan) and plan.get("rows_estimated", 0) > 10000:
            issues.append("Sequential scan on large table - consider index")
        
        return issues
```

**CI Integration**:
```yaml
# In CI workflow
- name: Check query plans
  run: |
    python -m cql_py.explain_check \
      --measures measures/*.cql \
      --db test.duckdb \
      --fail-on-regression
```

---

### H.10 Cost Model Heuristics (LOW)

**Problem**: Static rewrite policy may be suboptimal. Sometimes correlated subqueries are cheaper.

**Solution**: Add cardinality hints to `DefinitionMeta`.

```python
@dataclass
class DefinitionMeta:
    # ... existing fields ...
    estimated_rows_per_patient: Optional[float] = None  # NEW
    
    @property
    def prefer_correlated_subquery(self) -> bool:
        """Heuristic: prefer correlated subquery for small cardinalities."""
        if self.estimated_rows_per_patient is not None:
            return self.estimated_rows_per_patient < 2.0
        return False
```

**Usage**:
```python
def _select_join_strategy(self, ref: CTEReference) -> JoinStrategy:
    meta = self._context.definition_meta.get(ref.cte_name)
    
    if meta and meta.prefer_correlated_subquery:
        return JoinStrategy.CORRELATED_SUBQUERY
    
    # ... normal strategy selection ...
```

---

### H.11 Thread Safety (LOW)

**Problem**: If used in server context, shared mutable state causes bugs.

**Requirements**:
- `SQLTranslationContext` must not be shared across requests
- `SQLQueryBuilder` is per-definition (already planned)
- Document lifecycle clearly

```python
class CQLTranslator:
    """Thread-safe CQL translator - creates fresh context per translation."""
    
    def translate(self, library: Library) -> str:
        # Fresh context per translation - thread-safe
        context = SQLTranslationContext()
        translator = CQLToSQLTranslator(context)
        return translator.translate_library(library)
```

---

### H.12 Developer Ergonomics (MEDIUM)

**Requirements**:
- Error messages reference definition names and AST locations
- Provide `--explain` flag for dependency graph
- Suggested fixes in error messages

```python
class TranslationError(Exception):
    def __init__(
        self,
        message: str,
        definition: Optional[str] = None,
        ast_location: Optional[Tuple[int, int]] = None,
        suggestion: Optional[str] = None,
    ):
        self.definition = definition
        self.ast_location = ast_location
        self.suggestion = suggestion
        
        full_message = message
        if definition:
            full_message = f"[{definition}] {full_message}"
        if ast_location:
            full_message = f"{full_message} (line {ast_location[0]}, col {ast_location[1]})"
        if suggestion:
            full_message = f"{full_message}\n  Suggestion: {suggestion}"
        
        super().__init__(full_message)
```

---

### H.13 Additional Test Cases

| Test Case | Purpose |
|-----------|---------|
| Union shape propagation | `A union B` where A has `verification_status` column, B doesn't |
| Forward reference ordering | File with definitions in reverse order |
| Engine compatibility | Same CQL produces same results on DuckDB + PostgreSQL |
| LATERAL behavior | `First([Observation])` works on lateral and non-lateral backends |
| `singleton from` error | Must error when >1 row, not silently LIMIT 1 |
| Heterogeneous `if` branches | `if X then RESOURCE_ROWS else PATIENT_SCALAR` |
| Fluent function type mismatch | Template expects array but receives JSON object |

---

### H.14 Implementation Guardrails Checklist

- [ ] **Single canonical context object** - merge before other work
- [ ] **Two-pass workflow enforced** - fail if generation uses unanalyzed paths
- [ ] **Fresh SQLQueryBuilder per-definition** - never share mutable builders
- [ ] **Track full set of usages per CTE** - DISTINCT only if ALL usages permit
- [ ] **AST-level template composition** - avoid raw SQL string substitution
- [ ] **Warnings for fallbacks** - expose in CI as errors with `--strict`
- [ ] **Standardize patient_id** - compile-time assertion in `SQLRetrieveCTE`
- [ ] **Backend capability abstraction** - supports_lateral, supports_json, etc.
- [ ] **Alias length validation** - truncate + hash for long names
- [ ] **Thread-safety documented** - fresh context per request

---

### H.15 Prioritized Timeline

**Next 30 Days (Foundation)**:
- [ ] Unify context classes
- [ ] Standardize `patient_id`
- [ ] Implement topological sort
- [ ] Fresh builder per definition
- [ ] Add warnings for fallbacks

**Next 60 Days (Core Safety)**:
- [ ] RowShape + DefinitionMeta + CQL type
- [ ] Distinct-join logic
- [ ] ColumnRegistry + two-pass analysis
- [ ] Cartesian fanout detection
- [ ] Engine capability flags

**Next 90 Days (Robustness)**:
- [ ] Fluent function AST rewrite
- [ ] LATERAL support for PostgreSQL
- [ ] EXPLAIN harness and cross-engine CI
- [ ] Property-based fuzz tests
- [ ] Result-based integration tests
- [ ] Self-join alias handling
- [ ] Inter-resource correlation predicates
