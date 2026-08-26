# CQL-to-SQL Translator Technical Specification

> **Version:** 2.1
> **Date:** 2026-03-17
> **Status:** Active

---

## 1. Core Framework

### 1.1 Translation Priority

When translating CQL to SQL, follow this priority order:

```
1. FUNCTION REGISTRY - Registered SQL optimizations for known CQL functions
2. PURE SQL          - Default: use native SQL operations whenever possible
3. LIBRARY INLINER   - CQL-defined functions inlined at AST level
4. FHIRPath UDFs     - Required for all FHIR path navigation/evaluation
```

**Rationale:**
- **Function Registry** is consulted first for functions with registered SQL generation strategies (see §1.5). These are explicit, versioned optimizations — not ad-hoc special cases.
- **Pure SQL** is the default for operations that map directly to SQL expressions.
- **Library Inliner** handles all CQL-defined functions via AST-level macro expansion. No fallback to string templates for functions with a CQL body.
- **FHIRPath UDFs** are required for navigating FHIR resource structure (path evaluation).

### 1.2 Performance-Based Decision Examples

| Operation | Use | Rationale |
|-----------|-----|-----------|
| `X = Y` | SQL | Simple comparison |
| `X during day of Y` | SQL | Simple date range check |
| `AgeInYearsAt(patient, date)` | Function Registry | Birthday-aware SQL registered as an optimization |
| `X.value` | FHIRPath UDF | Path navigation required |
| `dateDiff(years, date1, date2)` | SQL | Date arithmetic via native SQL functions |
| `intervalOverlaps(A, B)` | SQL (if dates available) | Simple comparison if precomputed |
| `intervalOverlaps(A, B)` | FHIRPath UDF | If intervals are UDF results |

### 1.3 Three-Phase Transformation Approach

The translator operates in three distinct phases to ensure all context and metadata are available before SQL is generated:

**Phase 1: Translation & Analysis**
- Parse all CQL definitions
- Topologically sort by dependencies
- For each definition, collect:
  - Property accesses per resource type
  - Definition references and usage contexts
  - Aggregate functions used
- Translate each expression to SQL AST nodes
  - Resource retrieves are emitted as `RetrievePlaceholder` nodes (not yet resolved)
  - Record `DefinitionMeta` (shape, has_resource, value_column) for each definition
- Compute required precomputed columns per CTE

**Phase 2: CTE Construction**
- Build retrieve CTEs from collected property scans (precomputed columns)
- Build definition CTEs in dependency order
- For each definition:
  - Create fresh SQLQueryBuilder (scoped to this definition)
  - Use the translated SQL AST from Phase 1
  - Extract JOINs from builder
  - Build CTE with appropriate wrapping based on `DefinitionMeta`:
    - **Boolean definitions** (PATIENT_SCALAR, no resource): wrap in `SELECT p.patient_id FROM _patients AS p WHERE <expr>`
    - **Value definitions** (PATIENT_SCALAR, has value): wrap in `SELECT p.patient_id, <expr> AS <value_column> FROM _patients AS p`
    - **Resource row definitions** (RESOURCE_ROWS): use the translated SELECT directly
  - Append LEFT JOINs for referenced CTEs

**Phase 3: Placeholder Resolution**
- Walk the complete SQL AST tree
- Replace each `RetrievePlaceholder` with a `SQLIdentifier` referencing the actual CTE name
- This deferred resolution allows Phase 2 to finalize CTE names and structure before wiring up references
- Assemble final SQL string from the resolved AST

### 1.4 Function Inlining Pipeline

CQL-defined functions (those loaded from included libraries) are inlined at the AST level via `FunctionInliner`. This is macro-style expansion: the function body CQL AST is substituted with caller arguments before translation to SQL.

**Invariant**: Functions with a CQL AST body (`func_def.body is not None`) use mandatory AST inlining — no string-template fallback. This ensures `RetrievePlaceholder` nodes inside function bodies remain as Python objects visible to Phase 2's scanner.

Hardcoded functions (registered with `body_sql` string templates only, e.g. Status library functions) use the string template path. These functions do not contain `[Retrieve]` expressions so the string-template path is safe for them.

### 1.5 Function Translation Registry

`FunctionTranslationRegistry` (`cql-py/src/cql_py/translator/function_registry.py`) maps CQL function names to SQL generation strategies. It is consulted before the library inliner (§1.4) and before the general function dispatch.

**Purpose**: Register legitimate SQL optimizations for functions where a hand-crafted SQL expression is preferable to inlining the CQL definition. This is for performance reasons only — not as a workaround for inlining failures.

**Design**:
- Keyed by `(function_name_lower, arity)` — case-insensitive, with exact-arity-then-wildcard fallback
- Each entry is a callable `(args: List[SQLExpression], context: SQLTranslationContext) → SQLExpression`
- Built at `ExpressionTranslator` construction time in `_build_function_registry()`

**Currently registered functions**:

| CQL Function | Arity | Optimization |
|---|---|---|
| `Age`, `AgeInYears`, `AgeInMonths`, `AgeInDays`, `AgeInHours`, `AgeInMinutes`, `AgeInSeconds` | any | Birthday-aware date diff using `_patient_demographics` CTE |
| `AgeInYearsAt`, `AgeInMonthsAt`, `AgeInDaysAt` | any | Birthday-aware date diff with explicit reference date |

**Adding a new entry**: Call `registry.register(name, translator, arity=None)` in `_build_function_registry()`. Document the justification — registry entries must be optimizations, not workarounds.

### 1.6 Context-Dependent Transformation Philosophy

The core philosophy of this translator is that **the same CQL expression transforms into different SQL depending on its usage context and row shape**.

**Problem with naive translation:**
```sql
-- SLOW: O(n²) - Executes subquery once per patient row
SELECT p.patient_id,
       EXISTS (SELECT 1 FROM "Diabetes" d WHERE d.patient_id = p.patient_id)
FROM _patients p
```

**Context-aware translation:**
```sql
-- FAST: O(n) - Single JOIN operation
SELECT p.patient_id, j1.patient_id IS NOT NULL AS has_diabetes
FROM _patients p
LEFT JOIN (SELECT DISTINCT patient_id FROM "Diabetes") j1 ON j1.patient_id = p.patient_id
```

---

## 2. Context Analysis

> **Cross-Reference:** See `docs/DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md` Section 2 for data structure definitions (`ExprUsage`, `RowShape`, `DefinitionMeta`, `CTEReference`).

### 2.1 Usage Context (ExprUsage)

Usage context describes **how an expression's result will be consumed**.

#### Context Types

| Context | Meaning | Result Expected |
|---------|---------|-----------------|
| `LIST` | Return full collection | All rows/values |
| `SCALAR` | Need single value | One value (or NULL) |
| `BOOLEAN` | Truth test | TRUE/FALSE |
| `EXISTS` | Non-emptiness check | TRUE if non-empty, FALSE if empty |

#### Context Inference Rules

Context is inferred from the **parent expression**:

| CQL Context | ExprUsage |
|-------------|-----------|
| `[Condition]` (standalone) | LIST |
| `exists X` | X context = EXISTS |
| `Count(X)`, `Sum(X)`, `First(X)` | X context = LIST (needs all rows) |
| `X = Y` (comparison) | X context = SCALAR, Y context = SCALAR |
| `where X`, `A and B` | X, A, B context = BOOLEAN |
| `X.property` where X is RESOURCE_ROWS or PATIENT_MULTI_VALUE | X context = LIST (project across all rows) |
| `X.property` where X is PATIENT_SCALAR | X context = SCALAR (single value) |
| Standalone define reference | LIST (default CQL semantics) |

### 2.2 Row Shape

Row shape describes **what a definition produces** in terms of rows per patient.

#### Shape Types

| Shape | Meaning | Rows per Patient | Example |
|-------|---------|------------------|---------|
| `PATIENT_SCALAR` | Single value per patient | Exactly 1 | `Count(X)`, `exists X`, `First(X).status` |
| `PATIENT_MULTI_VALUE` | Multiple scalar values per patient (no `resource` column) | 0, 1, or many | `Diabetes.status`, `Patient.name.given`, `distinct(X.code)` |
| `RESOURCE_ROWS` | One row per resource (has `resource` column) | 0, 1, or many | `[Condition]`, `X where X.status = 'active'` |

**Key distinction:** `PATIENT_MULTI_VALUE` vs `RESOURCE_ROWS` — both can produce multiple rows per patient, but `PATIENT_MULTI_VALUE` rows contain only projected scalar values (no `resource` JSON column). This matters for JOIN strategies and downstream consumption (e.g., `singleton from` on a multi-value set doesn't need to select a `resource` column).

#### Shape Metadata

Each definition also tracks:

| Field | Type | Purpose |
|-------|------|---------|
| `has_resource` | `bool` | Whether the definition's CTE includes a `resource` column |
| `value_column` | `Optional[str]` | Name of the primary value column (for PATIENT_SCALAR definitions) |

#### Shape Inference Rules

| Expression Type | Output Shape |
|-----------------|--------------|
| `[Resource]` (Retrieve) | RESOURCE_ROWS |
| `exists [Resource]` | PATIENT_SCALAR |
| `First([Resource])` | PATIENT_SCALAR |
| `Count([Resource])` | PATIENT_SCALAR |
| `Sum/Avg/Min/Max` | PATIENT_SCALAR |
| `X.property` where X is RESOURCE_ROWS | PATIENT_MULTI_VALUE (projection, no `resource` column) |
| `X.property` where X is PATIENT_SCALAR | PATIENT_SCALAR |
| `X.property` where X is PATIENT_MULTI_VALUE | PATIENT_MULTI_VALUE |
| `union`/`intersect`/`except` | RESOURCE_ROWS (if sources are RESOURCE_ROWS) or PATIENT_MULTI_VALUE |
| `distinct(X)` where X is RESOURCE_ROWS | RESOURCE_ROWS |
| `distinct(X)` where X is PATIENT_MULTI_VALUE | PATIENT_MULTI_VALUE |
| Binary comparison (`=`, `>`) | PATIENT_SCALAR |
| Logical operators (`and`, `or`) | PATIENT_SCALAR |
| `if/case` | Shape of branches (RESOURCE_ROWS if any branch is) |
| Query with `return` (scalar projection) | PATIENT_MULTI_VALUE |
| Query with `return` (resource passthrough) | RESOURCE_ROWS |

### 2.3 Context + Shape → SQL Pattern Matrix

The combination of shape and context determines the SQL pattern:

| Shape | Context | Safe? | SQL Pattern | Notes |
|-------|---------|-------|-------------|-------|
| PATIENT_SCALAR | EXISTS | ✓ | `LEFT JOIN cte ... WHERE cte.patient_id IS NOT NULL` | Direct JOIN |
| PATIENT_SCALAR | SCALAR / BOOLEAN | ✓ | `LEFT JOIN cte ... SELECT cte.value_column` | Direct JOIN |
| PATIENT_SCALAR | LIST | ✓ | `LEFT JOIN cte ...` | Returns 1 row max |
| PATIENT_MULTI_VALUE | EXISTS | ✓ | `LEFT JOIN (SELECT DISTINCT patient_id FROM cte) ...` | DISTINCT to prevent fanout |
| PATIENT_MULTI_VALUE | SCALAR | ⚠️ | **Error**: Use `First()`, `Last()`, or `singleton from` | Must aggregate |
| PATIENT_MULTI_VALUE | BOOLEAN | ⚠️ | **Error**: Use `exists()` or `Count() > 0` | Must aggregate |
| PATIENT_MULTI_VALUE | LIST | ✓ | `FROM cte` | Full CTE reference |
| RESOURCE_ROWS | EXISTS | ✓ | `LEFT JOIN (SELECT DISTINCT patient_id FROM cte) ...` | DISTINCT to prevent fanout |
| RESOURCE_ROWS | SCALAR | ⚠️ | **Error**: Use `First()`, `Last()`, or `singleton from` | Must aggregate |
| RESOURCE_ROWS | BOOLEAN | ⚠️ | **Error**: Use `exists()` or `Count() > 0` | Must aggregate |
| RESOURCE_ROWS | LIST | ✓ | `FROM cte` | Full CTE reference |

---

## 3. CQL Pattern → SQL Mapping Reference

> **Note:** These mappings illustrate the baseline transformations. The exact pattern used may vary depending on the Context Analysis rules defined in Section 2.

### 3.1 Path Navigation

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `X.property` | - | `fhirpath_text(X, 'property')` | - | All path evaluation → FHIRPath |
| `X.nested.path` | - | `fhirpath_text(X, 'nested.path')` | - | Nested paths |
| `X.property[index]` | - | `fhirpath_text(X, 'property[index]')` | - | Array indexing |
| `X.choiceProperty` (choice type) | - | `fhirpath_date(X, 'choiceDateTime')` | - | COALESCE for choice types |
| `X.component.where(...)` | - | `fhirpath_number(X, 'component.where(...)')` | - | FHIRPath where() predicate |

### 3.2 Comparisons

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `X = Y` | `X = Y` | - | - | Native SQL equality |
| `X != Y` | `X != Y` | - | - | Native SQL inequality |
| `X < Y` | `X < Y` | - | - | Native SQL comparison |
| `X in List` | `X IN (...)` | - | - | Native SQL IN |
| `X ~ "Code"` (valueset) | - | - | `in_valueset(X, 'code', valueset_url)` | Valueset membership |

### 3.3 Temporal Comparisons

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `X same day as Y` | `CAST(X AS DATE) = CAST(Y AS DATE)` | - | - | Precision-aligned date equality |
| `X same or before Y` | `X <= Y` | - | - | Date comparison |
| `X same or after Y` | `X >= Y` | - | - | Date comparison |
| `X before Y` | `X < Y` | - | - | Date comparison |
| `X after Y` | `X > Y` | - | - | Date comparison |
| `X during day of MP` | `X >= mp_start AND X < mp_end` | - | - | Measurement period |
| `X during day of Period` | `X BETWEEN p.start AND COALESCE(p.end, p.start)` | - | - | Resource period |
| `X starts before end of MP` | `X < mp_end` | - | - | Interval boundary |

**⚠️ Precision alignment:** CQL temporal comparisons specify a precision keyword (`day`, `month`, `year`). When the precision keyword is present, both operands must be truncated/cast to that precision before comparison:
- `same day as` → `CAST(X AS DATE) = CAST(Y AS DATE)`
- `same month as` → `DATE_TRUNC('month', X) = DATE_TRUNC('month', Y)`
- `same year as` → `EXTRACT(YEAR FROM X) = EXTRACT(YEAR FROM Y)`

When no precision keyword is present (e.g., `X before Y`), compare at the finest precision available between the two operands. If both are already DATE-typed (common with precomputed columns), no cast is needed.

### 3.4 Interval Operations

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `intervalOverlaps(A, B)` | `A.start < B.end AND COALESCE(A.end, MAX_DATE) >= B.start` | - | - | Preferred: SQL-native |
| `A includes B` | `A.start <= B.start AND A.end >= B.end` | - | - | SQL-native |
| `A starts B` | `A.start = B.start` | - | - | SQL-native |
| `A ends B` | `A.end = B.end` | - | - | SQL-native |
| `intervalStart(I)` | - | - | `intervalStart(I)` | If I is UDF result |
| `intervalEnd(I)` | - | - | `intervalEnd(I)` | If I is UDF result |
| `intervalFromBounds(s, e)` | - | - | `intervalFromBounds(s, e, true, false)` | Interval construction |

### 3.5 Aggregations

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `exists X` | `EXISTS (SELECT 1 FROM X)` | - | - | SQL EXISTS |
| `count(X)` | `COUNT(*)` | - | - | SQL COUNT |
| `sum(X)` | `SUM(X)` | - | - | SQL SUM |
| `First(X sort asc)` | `ROW_NUMBER() OVER (ORDER BY X ASC) WHERE rn=1` | - | - | Window function |
| `Last(X sort desc)` | `ROW_NUMBER() OVER (ORDER BY X DESC) WHERE rn=1` | - | - | Window function |
| `singleton from X` | `SELECT resource FROM X LIMIT 1` | - | - | Get single element (see Section 3.12) |

### 3.6 Resource Retrieve

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `[Condition]` | `SELECT ... FROM resources WHERE resourceType = 'Condition'` | - | - | Base retrieve |
| `[Condition: "Essential Hypertension"]` | `SELECT ... FROM resources WHERE resourceType = 'Condition' AND in_valueset(...)` | - | `in_valueset()` | Valueset-filtered |
| `[USCoreBloodPressureProfile]` | `SELECT ... FROM resources WHERE resourceType = 'Observation' AND profile` | `fhirpath_text(..., 'meta.profile')` | - | Profile-based |
| `[Condition] C where C.status = 'active'` | `SELECT ... WHERE resourceType = 'Condition' AND status = 'active'` | - | - | Retrieve with filter |

### 3.7 Set Operations (Union, Intersect, Except)

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `A union B` | `SELECT ... FROM A UNION SELECT ... FROM B` | - | - | CQL `union` is **set union (distinct)** by default |
| `A union B` (provably disjoint) | `SELECT ... FROM A UNION ALL SELECT ... FROM B` | - | - | Optimization: only when disjointness is proven (e.g., different resource types) |
| `A intersect B` | `SELECT ... FROM A INTERSECT SELECT ... FROM B` | - | - | SQL INTERSECT (distinct, matches CQL) |
| `A except B` | `SELECT ... FROM A EXCEPT SELECT ... FROM B` | - | - | SQL EXCEPT (distinct, matches CQL) |

**⚠️ UNION ALL Optimization Rule:** `UNION ALL` may only be used instead of `UNION` when disjointness can be **proven at translation time**. Either of the following conditions is independently sufficient:
- Sources retrieve **different resource types** (e.g., `[Encounter]` vs `[ServiceRequest]`) — structural disjointness; different resource types cannot share rows
- The definition is used only in an **existence context** (`EXISTS`/`IS NOT NULL`) — semantic safety; duplicates are harmless when only patient presence matters

Either condition alone permits `UNION ALL`. Both are not required. When same resource type is retrieved with different valuesets (e.g., `[Condition: "Diabetes"]` union `[Condition: "Hypertension"]`), the sources may overlap — use `UNION` (distinct) unless the existence-context condition applies.

### 3.8 Existence (exists, with/without)

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `exists X` | `EXISTS (SELECT 1 FROM X WHERE X.patient_id = p.patient_id)` | - | - | Correlated EXISTS |
| `exists X` (boolean define) | `LEFT JOIN X ... WHERE X.patient_id IS NOT NULL` | - | - | LEFT JOIN pattern |
| `Patient with X` | `SELECT p.* FROM patients p INNER JOIN X ON X.patient_id = p.patient_id` | - | - | INNER JOIN |
| `Patient without X` | `SELECT p.* FROM patients p LEFT JOIN X ON X.patient_id = p.patient_id WHERE X.patient_id IS NULL` | - | - | LEFT JOIN + IS NULL |

### 3.9 Let Binding

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `let x = expr` (in query) | Column alias in SELECT or CTE | - | - | Inline alias |
| `let x = expr` (top-level) | Separate CTE | - | - | CTE for reuse |

**Example - Let in Query:**
```cql
from [Condition] C
  let diagnosisDate = C.onset
  where diagnosisDate during "Measurement Period"
```
```sql
SELECT C.*, fhirpath_date(C.resource, 'onsetDateTime') AS diagnosis_date
FROM "Condition" C
WHERE diagnosis_date >= mp_start AND diagnosis_date < mp_end
```

### 3.10 Such That (Query Source Relationships)

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `from A, B such that A.date = B.date` | `FROM A CROSS JOIN B WHERE A.date = B.date` | - | - | CROSS JOIN + WHERE |
| `from A, B such that intervalOverlaps(A.period, B.period)` | `FROM A INNER JOIN B ON A.start < B.end AND A.end >= B.start` | - | - | JOIN with interval condition |
| `A B such that B.encounter = A.id` | `FROM A INNER JOIN B ON B.encounter_reference = A.id` | - | - | Reference-based JOIN |

#### `with` vs `without` + `such that`

The `with`/`without` keywords combined with `such that` are common CQL patterns for correlated existence checks:

| CQL Pattern | SQL Pattern | Notes |
|-------------|-------------|-------|
| `A with B such that <pred>` | `A WHERE EXISTS (SELECT 1 FROM B WHERE B.patient_id = A.patient_id AND <pred>)` | Keep rows of A where correlated B exists |
| `A without B such that <pred>` | `A WHERE NOT EXISTS (SELECT 1 FROM B WHERE B.patient_id = A.patient_id AND <pred>)` | Keep rows of A where correlated B does NOT exist |

**Example — `without...such that`:**
```cql
define "Encounter Without Diagnosis":
  "Qualifying Encounters" E
    without [Condition: "Diabetes"] D such that D.onset during E.period
```
```sql
SELECT E.*
FROM "Qualifying Encounters" E
WHERE NOT EXISTS (
    SELECT 1 FROM "Condition: Diabetes" D
    WHERE D.patient_id = E.patient_id
      AND D.onset_date >= E.period_start
      AND D.onset_date <= COALESCE(E.period_end, E.period_start)
)
```

**Example - Such That:**
```cql
from "Qualifying Blood Pressure Reading" BP,
     "Encounter: Encounter Inpatient" E
such that BP.effective.latest() during day of E.period
```
```sql
SELECT BP.*
FROM "Qualifying Blood Pressure Reading" BP
INNER JOIN "Encounter: Encounter Inpatient" E ON E.patient_id = BP.patient_id
WHERE BP.effective_date BETWEEN E.period_start AND COALESCE(E.period_end, E.period_start)
```

### 3.11 Query Source (from, where, return)

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `from [Condition] C` | `FROM "Condition" C` | - | - | Simple FROM |
| `from [Condition] C where C.status = 'active'` | `FROM "Condition" C WHERE C.status = 'active'` | - | - | FROM + WHERE |
| `from [Condition] C return C.code` | `SELECT C.code FROM "Condition" C` | - | - | Projection |
| `from [Condition] C return singleton from ...` | `SELECT fhirpath_number(...) FROM "Condition" C` | `fhirpath_number()` | - | Complex return |

### 3.12 Singleton From

`singleton from` has two distinct translation strategies depending on the source:

#### Case 1: Retrieve/Query Source (returns resource rows)

When `singleton from` operates on a query that returns resource rows (e.g., `singleton from [Encounter] E where ...`), it should select a single resource **and enforce CQL's singleton semantics** (return NULL if >1 element):

| CQL Pattern | SQL Pattern | Notes |
|-------------|-------------|-------|
| `singleton from ([Resource] R where ...)` | `CASE WHEN (SELECT COUNT(*) FROM ...) = 1 THEN (SELECT resource FROM ... LIMIT 1) ELSE NULL END` | Enforces CQL semantics: NULL if empty or >1 |

**⚠️ Semantic correctness:** CQL's `singleton from` must return:
- The single element if the collection has exactly 1 element
- `null` if the collection is empty
- `null` (or error in strict mode) if the collection has >1 element

A naive `LIMIT 1` silently picks one row when multiple exist, which **violates CQL semantics**. The translator must enforce cardinality via `CASE WHEN COUNT(*) = 1 THEN ... ELSE NULL END`. `LIMIT 1` is not an acceptable fallback.

**Key:** Do NOT use `LIST_EXTRACT(subquery, 1)` — DuckDB's `LIST_EXTRACT` expects a single-column array, but retrieve subqueries return multiple columns (`patient_id`, `resource`, precomputed columns). Instead, rewrite the inner SELECT to return only the `resource` column.

#### Case 2: Component/Array Source (returns scalar values)

When `singleton from` operates on a filtered component array, push the filter into a precomputed column:

| CQL Pattern | SQL Pattern | Notes |
|-------------|-------------|-------|
| `singleton from (X.component C where C.code ~ "Systolic" return C.value)` | `fhirpath_number(resource, 'component.where(code.coding.exists(code = ''8480-6'')).valueQuantity.value')` | Precomputed in retrieve CTE |

**Strategy:** When `singleton from` is used with a `where` filter on array components, push the filter into the retrieve CTE as a precomputed column rather than evaluating at runtime.

### 3.13 Type Conversions

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `date from X` | `X::DATE` | - | - | SQL cast |
| `dateTime from X` | `X::TIMESTAMP` | - | - | SQL cast |
| `ToString(X)` | `CAST(X AS VARCHAR)` | - | - | SQL cast |
| `ToInteger(X)` | `CAST(X AS INTEGER)` | - | - | SQL cast |

### 3.14 Quantity Operations

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `X < 90 'mm[Hg]'` | - | - | `quantity_lt(X, parse_quantity('{"value":90,...}'))` | Quantity comparison |
| `X.value` | - | `fhirpath_number(X, 'value')` | - | Extract quantity value |
| `X.unit` | - | `fhirpath_text(X, 'unit')` | - | Extract unit |

### 3.15 Parameters

| CQL Pattern | Pure SQL | FHIRPath UDF | CQL UDF | Notes |
|-------------|----------|--------------|---------|-------|
| `"Measurement Period"` | - | - | `getvariable('measurement_period')` | Returns interval |
| `intervalStart(getvariable('mp'))` | - | - | `intervalStart(getvariable('mp'))` | Get start |
| `intervalEnd(getvariable('mp'))` | - | - | `intervalEnd(getvariable('mp'))` | Get end |
| `AgeInYearsAt(patient, date)` | - | - | `AgeInYearsAt(patient_resource, date)` | Always use the CQL UDF; do not precompute as a SQL column |

---

## 4. Safety Transformations

> **Cross-Reference:** See `docs/DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md` Section 5 for detailed implementation of safety mechanisms.

### 4.1 Cartesian Fanout Prevention

**Problem:** JOINing any `cardinality=MANY` CTE (either `RESOURCE_ROWS` or `PATIENT_MULTI_VALUE`) into a patient-scoped query risks row multiplication.

```cql
define Diabetes: [Condition: "Diabetes"]        -- 3 rows for Patient A
define Hypertension: [Condition: "Hypertension"] -- 2 rows for Patient A
define Combined: Diabetes.status and Hypertension.status
-- BUG: Patient A gets 6 rows (3 × 2)
```

**Detection Rules (Generalized):**
- Flag as unsafe when **any** `cardinality=MANY` CTE is joined into a patient-scoped wrapper
- Flag as unsafe when **multiple** `cardinality=MANY` CTEs are referenced in the same scope
- Exception: safe when the CTE is used in an `EXISTS`-only context (only patient_id matters)

**Guardrail Rule:** Any time a patient-scoped wrapper joins a source with `cardinality=MANY`, the translator must either:
1. **Aggregate to 1 row per patient** before joining (`GROUP BY patient_id`)
2. **Join only a distinct patient_id projection** (EXISTS-style: `SELECT DISTINCT patient_id FROM cte`)
3. **Use a lateral/window-limited join** (e.g., First/Last with `ROW_NUMBER()`)

**Transformation Strategies:**

| Strategy | When to Use | Implementation |
|----------|-------------|----------------|
| DISTINCT JOIN | All usages are EXISTS/BOOLEAN | Wrap JOIN in `SELECT DISTINCT patient_id` |
| Pre-aggregation | Counts/sums needed | Enforce `GROUP BY patient_id` with aggregate before combining |
| Window-limited JOIN | First/Last needed | `ROW_NUMBER() ... WHERE rn = 1` before joining |
| Error (strict mode) | Unsafe pattern detected | Require explicit aggregation in CQL |

### 4.2 Multi-Usage Resolution

**Problem:** The same CTE can be referenced multiple times with conflicting usage contexts.

```cql
define Diabetes: [Condition: "Diabetes"]
define X: exists Diabetes and Diabetes.status = 'confirmed'
-- "Diabetes" used as EXISTS and SCALAR
```

**Resolution Rule:** Accumulate all contexts for the CTE reference and use the most permissive JOIN strategy:

| Accumulated Usages | JOIN Strategy |
|--------------------|---------------|
| `{EXISTS}` only | DISTINCT JOIN |
| `{EXISTS, SCALAR}` or `{EXISTS, LIST}` | Full CTE JOIN (no DISTINCT) |
| `{RESOURCE_ROWS, SCALAR}` | **Translation Error** (must aggregate in CQL) |

**Implementation:**
```python
def track_cte_reference(self, cte_name, semantic_alias, usage, shape):
    key = (cte_name, semantic_alias or cte_name)
    if key in self.cte_references:
        # Add to existing usages - don't overwrite
        self.cte_references[key].usages.add(usage)
        return self.cte_references[key].alias
    # ... create new reference
```

### 4.3 Conditional RESOURCE_ROWS Handling

**Problem:** `if/else` expressions with `RESOURCE_ROWS` branches cause eager evaluation of both branches in SQL.

```cql
define RelevantConditions:
    if HasSevereRisk then SevereConditions else MildConditions
```

**Transformation Strategy:**
When either branch of a conditional is `RESOURCE_ROWS`, do not use a standard `CASE` with direct JOINs. Instead, use a **correlated subquery** inside the `CASE` statement so only the selected branch is executed for the patient.

**SQL Pattern:**
```sql
SELECT
    CASE
        WHEN has_severe_risk THEN
            (SELECT ... FROM "SevereConditions" WHERE patient_id = p.patient_id)
        ELSE
            (SELECT ... FROM "MildConditions" WHERE patient_id = p.patient_id)
    END AS relevant_conditions
FROM _patients p
```

### 4.4 NULL Handling (3-Valued Logic)

**Problem:** CQL and SQL handle NULL differently in boolean contexts.

| Expression | CQL | SQL |
|------------|-----|-----|
| `exists {}` | `false` | N/A |
| `{}.status = 'x'` | `{}` (empty) | `NULL` |
| `not (NULL = 'x')` | varies | `NULL` |

**Transformation Rule:** Wrap boolean expressions in `COALESCE(expr, FALSE)` when:

1. The expression result goes to a `WHERE` clause
2. The expression is an operand to `NOT`
3. The expression is an operand to `AND`/`OR` where NULL semantics differ

**Implementation:**
```python
def _wrap_for_boolean_context(self, expr, usage):
    if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
        return SQLFunctionCall(
            name="COALESCE",
            args=[expr, SQLLiteral(value=False)]
        )
    return expr
```

#### 4.4.1 Detailed NULL Semantics Mapping

| CQL Expression | CQL Result | SQL Equivalent | Match? | Notes |
|----------------|------------|----------------|--------|-------|
| `null = 'x'` | `null` | `NULL = 'x'` → `NULL` | ✓ | Both yield NULL |
| `null != 'x'` | `null` | `NULL != 'x'` → `NULL` | ✓ | Both yield NULL |
| `not null` | `null` | `NOT NULL` → `NULL` | ✓ | Both yield NULL |
| `null and true` | `null` | `NULL AND TRUE` → `NULL` | ✓ | SQL 3VL matches |
| `null and false` | `false` | `NULL AND FALSE` → `FALSE` | ✓ | SQL 3VL matches |
| `null or true` | `true` | `NULL OR TRUE` → `TRUE` | ✓ | SQL 3VL matches |
| `null or false` | `null` | `NULL OR FALSE` → `NULL` | ✓ | SQL 3VL matches |
| `if null then A else B` | `B` | `CASE WHEN NULL THEN A ELSE B END` → `B` | ✓ | Both take else branch |

**Key rule:** CQL and SQL 3-valued logic are largely compatible. The primary danger is `WHERE` clauses silently filtering out NULL results — hence the COALESCE wrapping rule above.

#### 4.4.2 Patient Context Assumption

This translator assumes **Patient context** for all definitions. CQL supports other contexts (e.g., `Practitioner`, `Unfiltered`), but these are **not supported** and should be rejected early in Phase 1 with a clear `TranslationError`:

```python
if context_def.context_type != 'Patient':
    raise TranslationError(
        f"Only Patient context is supported, got: {context_def.context_type}"
    )
```

---

## 5. Efficiency Transformations

### 5.1 Pre-Compute Strategy

The translator uses a **property usage scanner** during Phase 1 to detect which properties are accessed on each resource type. These properties are then **precomputed as columns** in the retrieve CTEs for efficiency.

#### Property Usage Detection

The scanner detects property access from CQL patterns:

| CQL Pattern | Detected Property | Precomputed Column |
|-------------|-------------------|-------------------|
| `X.effective` | `effective[x]` | `effective_date` |
| `X.effective.latest()` | `effective[x]` | `effective_date` |
| `X.onset` | `onset[x]` | `onset_date` |
| `X.abatement` | `abatement[x]` | `abatement_date` |
| `X.status` | `status` | `status` |
| `X.period` | `period.start`, `period.end` | `period_start`, `period_end` |
| `X.verificationStatus.coding[0].code` | `verificationStatus.coding[0].code` | `verification_status` |
| `singleton from(X.component where code ~ "Systolic")` | `component.where(code = '8480-6').value` | `systolic_value` |

#### Benefits of Pre-Computation

| Benefit | Description |
|---------|-------------|
| **Avoid repeated FHIRPath calls** | Same path not evaluated multiple times |
| **Enable SQL-native comparisons** | Precomputed columns can use `=`, `<`, `BETWEEN` |
| **Simplify JOIN conditions** | Use column names instead of nested FHIRPath |
| **Better query plan** | DuckDB can optimize on known columns |

> **See Appendix C.2** for detailed examples of precomputed column generation.

### 5.2 JOIN vs. Subquery Selection

**JOINs are the preferred standard** for O(n) efficiency, but correlated subqueries are used as fallbacks:

| Use JOIN | Use Correlated Subquery |
|----------|------------------------|
| PATIENT_SCALAR sources | Forward references |
| RESOURCE_ROWS with DISTINCT | Conditional RESOURCE_ROWS branching |
| Single RESOURCE_ROWS reference | Strict isolation required |
| | Small cardinality heuristic (`< 2.0 rows/patient`) |

### 5.3 CTE Organization

CTEs are organized structurally to separate concerns:

```
_patients
    ↓
_patient_demographics
    ↓
RETRIEVES (resource-type CTEs)
    ↓
EXTERNAL LIBRARY DEFINES
    ↓
MAIN LIBRARY DEFINES
    ↓
FINAL OUTPUT
```

#### CTE Naming Rules

| CTE Type | Naming Pattern | Example |
|----------|----------------|---------|
| Base patients | `_patients` | `_patients` |
| Demographics | `_patient_demographics` | `_patient_demographics` |
| Retrieve (no valueset) | `"ResourceType"` | `"Encounter"`, `"Observation"` |
| Retrieve (with valueset) | `"ResourceType: ValueSet Name"` | `"Condition: Essential Hypertension"` |
| External library define | `"Library.DefineName"` | `"Hospice.Has Hospice Services"` |
| Main library define | `"Define Name"` | `"Initial Population"` |

#### Alias Conventions

When wrapping boolean/value definitions in a patient-scoped SELECT, always use the `_patients AS p` alias:

```sql
-- Boolean definition wrapping pattern
"Some Boolean Define" AS (
    SELECT p.patient_id
    FROM _patients AS p
    WHERE <boolean_expression>
)

-- Value definition wrapping pattern
"Some Value Define" AS (
    SELECT p.patient_id, <expr> AS <value_column>
    FROM _patients AS p
    LEFT JOIN "SomeCTE" j1 ON j1.patient_id = p.patient_id
)
```

The `p` alias is the standard convention used throughout the translator. All patient-scoped wrapping must use `FROM _patients AS p` (not bare `_patients`).

> **See Appendix C.1** for the full CTE Target Structure example.

---

## 6. Profile Handling

### 6.1 Profile Detection (Inferred from CQL Usage)

Profiles are **inferred from CQL usage patterns**, not from a hardcoded registry. The translator:

1. **Scans CQL for property access patterns** during Phase 1 translation
2. **Detects which properties are accessed** on each resource type
3. **Generates precomputed columns** based on actual usage

**Example:**
```cql
// CQL accesses these properties on Observation:
BPReading.effective.latest()           -- needs effective_date
BPReading.status                        -- needs status
BPReading.component where code ~ "..." -- needs systolic/diastolic values
```

The translator infers this is a US Core Blood Pressure Profile observation and generates the appropriate precomputed columns.

> **See Appendix C.4** for the full Profile-Specific CTE example.

### 6.2 Profile → Precomputed Columns (Inferred)

Precomputed columns are inferred from CQL property access:

| CQL Property Access | Precomputed Column | FHIRPath |
|---------------------|-------------------|----------|
| `X.effective` or `X.effective.latest()` | `effective_date` | `COALESCE(effectiveDateTime, effectivePeriod.start, effectiveInstant)` |
| `X.status` | `status` | `status` |
| `X.onset` | `onset_date` | `COALESCE(onsetDateTime, onsetPeriod.start)` |
| `X.abatement` | `abatement_date` | `COALESCE(abatementDateTime, abatementPeriod.end)` |
| `X.period` | `period_start`, `period_end` | `period.start`, `period.end` |
| `singleton from(X.component where code ~ "Systolic")` | `systolic_value` | `component.where(code.coding.exists(code = '8480-6')).valueQuantity.value` |

### 6.3 Component Lookup (FHIRPath where())

For profiles with array elements that need filtering (e.g., BP components):

**CQL Pattern:**
```cql
singleton from(BPReading.component BPComponent
  where BPComponent.code ~ "Systolic blood pressure"
  return BPComponent.value as Quantity
)
```

**Translation:**
1. Detect `singleton from` with `where` clause on `.code`
2. Resolve code display ("Systolic blood pressure") via valueset lookup
3. Generate FHIRPath `where()` predicate

**SQL Generation (in retrieve CTE):**
```sql
fhirpath_number(resource,
    'component.where(code.coding.exists(code = ''8480-6'')).valueQuantity.value'
) AS systolic_value
```

### 6.4 Code Resolution (Valueset Lookup)

Code displays are resolved via valueset lookup at translation time:

| Code Display | Valueset | Resolved Code |
|--------------|----------|---------------|
| "Systolic blood pressure" | LOINC | 8480-6 |
| "Diastolic blood pressure" | LOINC | 8462-4 |

The translator:
1. Parses the `where BPComponent.code ~ "Code Display"` pattern
2. Looks up the code display in the referenced valueset
3. Substitutes the resolved code into the FHIRPath expression

---

## 7. Choice Type Handling

### 7.1 Choice Type Mapping

| Resource | Property | FHIRPath Alternatives | SQL Type |
|----------|----------|----------------------|----------|
| Observation | effective[x] | `effectiveDateTime`, `effectivePeriod.start`, `effectiveInstant` | DATE |
| Condition | onset[x] | `onsetDateTime`, `onsetPeriod.start` | DATE |
| Condition | abatement[x] | `abatementDateTime`, `abatementPeriod.end` | DATE |
| Procedure | performed[x] | `performedDateTime`, `performedPeriod.start` | DATE |
| Encounter | period | `period.start`, `period.end` | DATE |

### 7.2 COALESCE Generation

**Rule:** Generate COALESCE chain for all alternatives when choice type is accessed.

```sql
COALESCE(
    fhirpath_date(t1.resource, 'effectiveDateTime'),
    fhirpath_date(t1.resource, 'effectivePeriod.start'),
    fhirpath_date(t1.resource, 'effectiveInstant')
)::DATE AS effective_date
```

### 7.3 Detection Strategy

Choice types are detected by:

1. **Property ends with `[x]` in FHIR spec** - Known choice types
2. **CQL usage** - If CQL accesses `X.effective` without specifying type
3. **Usage inference** - Scan CQL for all property access patterns

---

## 8. External Library Handling

### 8.1 Library Resolution

1. Parse `include` statements to identify external libraries
2. Load each library's CQL file
3. Extract all `define` statements and `fluent function` definitions
4. Track which defines/functions are referenced from main CQL
5. Inline function bodies when called

### 8.2 Function Translation Strategy

Functions are translated using two distinct strategies depending on complexity:

#### Strategy 1: AST-Level Inlining (via FunctionInliner)

For user-defined functions (from external libraries), the **CQL AST** is inlined before SQL translation:

1. Parse function definition from library CQL into AST
2. Substitute formal parameters with actual argument AST nodes (`FunctionInliner._substitute_parameters`)
3. Translate the substituted CQL AST body to SQL AST
4. Insert resulting SQL AST at call site

**Supported substitutions:** `ExpressionRef`, `Property`, `FunctionRef`, `UnaryExpression`, `Literal`, `BinaryExpression`, `Query`, `Retrieve`, `If`, `And`, `Or`, `Not`, `IsNull`, `As`

**Example - AST Inlining:**
```cql
// In Status.cql
define fluent function verified(resource Resource):
  resource.verificationStatus is null
    or resource.verificationStatus in "Condition Verification Status"
```
```cql
[Condition: "Essential Hypertension"] C where C.verified()
```
```sql
SELECT ...
FROM "Condition: Essential Hypertension" C
WHERE (C.verification_status IS NULL
       OR C.verification_status IN ('confirmed', 'unconfirmed', 'provisional', 'differential'))
```

#### Strategy 2: String Templates (Registered Functions — Transitional)

For a narrow set of common fluent functions with known SQL patterns (e.g., `latest()`, `getId()`, `toInterval()`), the translator may use **registered string templates** with a single `{resource}` substitution point:

```python
# Example: latest() template
FLUENT_FUNCTIONS = {
    "latest": {
        "body_sql": "COALESCE(fhirpath_date({resource}, 'effectiveDateTime'), ...)",
        "return_type": "date"
    }
}
```

The `{resource}` placeholder is replaced with the actual SQL expression for the calling resource at translation time.

**Scope limitations:**
- Only permitted for the **pre-registered set** of fluent functions in `fluent_functions.py`. New fluent functions must use Strategy 1 (AST-level inlining).
- Templates must contain exactly **one `{resource}` substitution point** — no conditional logic, no computed SQL structure.
- The template body must be a **fixed SQL expression** (not constructed at runtime). This distinguishes it from the prohibited f-string pattern in design doc §14.5.

**Migration:** This is a transitional pattern. All Strategy 2 templates should be migrated to Strategy 1 (AST-level inlining via `FunctionInliner`) incrementally. No new Strategy 2 entries are permitted.

**Important:** String template functions that need to appear in a `FROM` clause require special handling — see Section 13.1 (Known Pitfalls) for the UNNEST/table source issue.

### 8.3 CTE Generation for External Library Defines

For each referenced external library define:

1. **Generate retrieves** from the library (if not already present)
2. **Generate the define CTE** with prefixed name
3. **Use UNION ALL** for multi-source defines (e.g., "Has Hospice Services")

> **See Appendix C.3** for the full Hospice UNION ALL example.

---

## 9. First/Last with Sorting

### 9.1 Pattern

**CQL:**
```cql
First(X sort asc)
Last(X sort desc)
```

### 9.2 SQL Generation

Use `ROW_NUMBER()` window function:

```sql
SELECT patient_id, value
FROM (
    SELECT
        t1.patient_id,
        t1.value,
        ROW_NUMBER() OVER (
            PARTITION BY t1.patient_id
            ORDER BY t1.value ASC NULLS LAST
        ) AS rn
    FROM "Some CTE" t1
    WHERE ...
) ranked
WHERE rn = 1
```

### 9.3 Default Sort Columns

When no explicit sort is provided, use resource-type defaults:

| Resource Type | Default Sort |
|---------------|--------------|
| Condition | `onset_date DESC`, `recorded_date DESC` |
| Observation | `effective_date DESC` |
| Encounter | `period_start DESC` |
| Procedure | `performed_date DESC` |
| MedicationRequest | `authored_on DESC` |

### 9.4 Sorting Determinism and Tie-Breaking

**⚠️ Determinism requirement:** `First`/`Last` with `ROW_NUMBER()` produce **non-deterministic** results when multiple rows share the same sort key value. The translator must ensure deterministic tie-breaking.

**Tie-breaking strategy:** Always append a secondary sort column to guarantee deterministic ordering:

```sql
ROW_NUMBER() OVER (
    PARTITION BY t1.patient_id
    ORDER BY t1.effective_date DESC NULLS LAST,
             json_extract_string(t1.resource, '$.id') ASC  -- tie-breaker
) AS rn
```

**Tie-breaker column selection:**
- If the resource has a FHIR `id`, use `json_extract_string(resource, '$.id')` as the secondary sort
- If the CTE has a precomputed `resource_id` column, use that
- Fallback: use `ROWID` or `resource::VARCHAR` hash for last-resort determinism

**NULL ordering:** Always use `NULLS LAST` for ascending sorts and `NULLS FIRST` for descending sorts to match CQL's expectation that nulls sort to the end of the collection.

---

## 10. Measurement Period Access

### 10.1 Pattern

```sql
-- Start of measurement period
CAST(intervalStart(getvariable('measurement_period')) AS DATE)

-- End of measurement period
CAST(intervalEnd(getvariable('measurement_period')) AS DATE)
```

### 10.2 Common Patterns

| CQL | SQL |
|-----|-----|
| `X during day of "Measurement Period"` | `X >= mp_start AND X < mp_end` |
| `X before end of "Measurement Period"` | `X < mp_end` |
| `X on or after start of "Measurement Period"` | `X >= mp_start` |

---

## 11. Context-Dependent Examples (Step-by-Step)

### 11.1 Example: exists vs Count

**CQL:**
```cql
define Diabetes: [Condition: "Diabetes"]
define HasDiabetes: exists Diabetes
define DiabetesCount: Count(Diabetes)
```

**Step 1: Shape Analysis**
- `Diabetes` = `RESOURCE_ROWS`
- `HasDiabetes` = `PATIENT_SCALAR`
- `DiabetesCount` = `PATIENT_SCALAR`

**Step 2: Context Analysis**
- `Diabetes` is used in `{EXISTS, LIST}` contexts

**Step 3: Resolution & Generation**
Because `LIST` is present (for the count), we cannot use a `DISTINCT` join on the base `Diabetes` CTE.

```sql
"HasDiabetes" AS (
    SELECT p.patient_id FROM patients p
    WHERE EXISTS (SELECT 1 FROM "Diabetes" d WHERE d.patient_id = p.patient_id)
),
"DiabetesCount" AS (
    SELECT p.patient_id, (SELECT COUNT(*) FROM "Diabetes" d WHERE d.patient_id = p.patient_id) AS count
    FROM patients p
)
```

### 11.2 Example: Property Access on RESOURCE_ROWS

**CQL:**
```cql
define Diabetes: [Condition: "Diabetes"]
define DiabetesStatuses: Diabetes.status
define FirstDiabetesStatus: First(Diabetes).status
```

**Step 1 & 2: Shape & Context Analysis**
- `Diabetes.status` produces `PATIENT_MULTI_VALUE` (property projection on RESOURCE_ROWS drops the `resource` column)
- `First(Diabetes).status` aggregates to `PATIENT_SCALAR` first, then accesses property

**Step 3: Generation**
```sql
"DiabetesStatuses" AS (
    SELECT patient_id, status FROM "Diabetes" -- Projection
),
"FirstDiabetesStatus" AS (
    SELECT patient_id, status FROM (
        SELECT patient_id, status, ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY onset_date DESC) AS rn
        FROM "Diabetes"
    ) ranked WHERE rn = 1
)
```

### 11.3 Example: Multi-Usage with Different Contexts

**CQL:**
```cql
define Conditions: [Condition]
define ActiveConditions: Conditions C where C.status = 'active'
define HasActive: exists ActiveConditions
define ActiveCount: Count(ActiveConditions)
```

**Resolution:**
`ActiveConditions` is `RESOURCE_ROWS` used in `{EXISTS, LIST}` contexts. The translator tracks the accumulated context and forces the full `LIST` strategy (preventing data loss from an eager `DISTINCT`). The `HasActive` boolean is calculated using `EXISTS` at the point of use rather than altering the base CTE.

### 11.4 Example: Boolean Definition with UNION ALL

**CQL:**
```cql
define "Has Hospice Services":
  exists ([Encounter: "Hospice Encounter"] E where E.period ends during "MP")
  or exists ([ServiceRequest: "Hospice Order"] S where S.authoredOn during "MP")
```

**Generation:**
Boolean definitions that are `or`-ed `exists` checks are translated as `UNION ALL` of patient_id sets. Each branch contributes patient_ids independently — the final CTE contains all patients matching any branch. Duplicate patient_ids are acceptable because the final output uses `LEFT JOIN ... IS NOT NULL` which handles duplicates naturally.

```sql
"Hospice.Has Hospice Services" AS (
    SELECT t1.patient_id FROM "Encounter: Hospice Encounter" t1
    WHERE COALESCE(t1.period_end, t1.period_start) >= mp_start
      AND COALESCE(t1.period_end, t1.period_start) < mp_end
    UNION ALL
    SELECT t1.patient_id FROM "ServiceRequest: Hospice Order" t1
    WHERE t1.authored_on >= mp_start AND t1.authored_on < mp_end
)
```

**Key:** `UNION ALL` is safe here because: (1) the sources are **different resource types** (Encounter vs ServiceRequest), proving disjointness, and (2) the definition is consumed only via **existence check** (`LEFT JOIN ... IS NOT NULL`), where duplicates are harmless. See §3.7 for the general UNION ALL optimization rule.

### 11.5 Example: with...such that Correlation

**CQL:**
```cql
define DiabetesWithRecentA1C:
  Diabetes D with A1C O such that O.effective within 30 days after D.onset
```

**Generation:**
The `such that` predicate becomes part of an `EXISTS` subquery `WHERE` clause bridging the two `RESOURCE_ROWS` structures.

```sql
"DiabetesWithRecentA1C" AS (
    SELECT d.* FROM "Diabetes" d
    WHERE EXISTS (
        SELECT 1 FROM "A1C" o
        WHERE o.patient_id = d.patient_id
          AND o.effective_date > d.onset_date
          AND o.effective_date <= d.onset_date + INTERVAL 30 DAY
    )
)
```

### 11.6 Example: Self-Join

**CQL:**
```cql
define BackToBack:
  from Encounters E1, Encounters E2
  where E2.period starts same day as E1.period ends
```

**Generation:**
Self-joins use semantic aliases (`E1`, `E2`) in the context tracker. The builder tracks `(cte_name, semantic_alias)` to generate dual `INNER JOIN` operations safely against the same base table.

```sql
"BackToBack" AS (
    SELECT e1.patient_id, e1.encounter_id AS e1_id, e2.encounter_id AS e2_id
    FROM "Encounter" e1
    INNER JOIN "Encounter" e2 ON e2.patient_id = e1.patient_id
    WHERE e2.period_start = e1.period_end
)
```

### 11.7 Full Walkthrough: CMS165 Measure

> **Cross-Reference:** See `docs/DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md` for the detailed translation pipeline of CMS165, illustrating usage inference for `Initial Population`, `Denominator`, and branching demographics logic.

---

## 12. Files to Modify

| File | Purpose |
|------|---------|
| `translator.py` | Main orchestrator: three-phase pipeline, CTE construction, definition wrapping, final SQL assembly |
| `expressions.py` | Expression translation, identifier resolution, `singleton from`, context-aware transformations |
| `types.py` | Enums (`ExprUsage`, `RowShape`, `CTEReference`), SQL AST nodes, `DefinitionMeta` |
| `cte_builder.py` | CTE section organization, retrieve CTE generation, fresh scoping |
| `fluent_functions.py` | Fluent function translation (string templates + registered functions). **Migration note:** Long-term, migrate string template functions to AST-level inlining (via `function_inliner.py`) to avoid UNNEST/correlated-reference pitfalls (see §13.1) |
| `function_inliner.py` | CQL AST-level function inlining (parameter substitution) |
| `placeholder.py` | Phase 3: `RetrievePlaceholder` → `SQLIdentifier` resolution |
| `property_scanner.py` | Phase 1: property usage detection for precomputed columns |
| `context.py` | Translation context: `definition_meta`, alias tracking, query builder state |
| `library_resolver.py` | Parse library CQL, generate prefixed CTEs |
| `column_registry.py` | Column registry for precomputed column tracking and deduplication |
| `queries.py` | `SQLQueryBuilder`, `CTEReference` tracking, JOIN construction |
| `operators.py` | CQL operator to SQL operator mapping |
| `patterns/temporal.py` | SQL-native temporal comparisons |
| `patterns/interval.py` | SQL-native interval operations |
| `patterns/aggregation.py` | Aggregate function patterns (Count, Sum, First/Last with ROW_NUMBER) |
| `patterns/joins.py` | JOIN pattern selection (LEFT, INNER, DISTINCT) |
| `patterns/retrieve.py` | Retrieve CTE patterns, US Core profile mapping |
| `patterns/quantity.py` | Quantity comparison and parsing patterns |

---

## 13. Known Pitfalls (DuckDB-Specific)

### 13.1 UNNEST and Correlated References

**Problem:** DuckDB cannot resolve correlated column references from outer queries when they appear inside `UNNEST` expressions. This affects fluent functions that use `_wrap_for_table_source` to convert scalar expressions into table sources.

**Example of broken pattern:**
```sql
-- BPExam is from an outer query scope
SELECT t.resource FROM UNNEST(
    CASE WHEN fhirpath_text(BPExam.resource, 'effective') IS NULL
         THEN [] ELSE [fhirpath_text(BPExam.resource, 'effective')] END
) AS t(resource)
-- ERROR: Referenced table "BPExam" not found!
```

**Root cause:** `_wrap_for_table_source` in `fluent_functions.py` wraps scalar expressions in `UNNEST(CASE WHEN ... IS NULL THEN [] ELSE [...] END)` to create a table source. When the scalar expression references a correlated alias from an outer scope, DuckDB cannot resolve it through the UNNEST boundary.

**Recommended solutions:**
1. **Avoid UNNEST for correlated expressions:** Detect when the expression contains correlated references and use a direct scalar approach instead
2. **Precompute in CTE:** Move the fluent function result into the retrieve CTE as a precomputed column
3. **Use LATERAL JOIN:** DuckDB supports `LATERAL` which may allow correlated references (needs testing)

### 13.2 Subquery Column Count in LIST_EXTRACT

**Problem:** `LIST_EXTRACT(subquery, 1)` requires the subquery to return exactly one column. Retrieve CTEs return multiple columns (`patient_id`, `resource`, precomputed columns), so `LIST_EXTRACT((SELECT * FROM "Encounter" WHERE ...), 1)` fails.

**Solution:** See Section 3.12 — use `SELECT resource ... LIMIT 1` instead of `LIST_EXTRACT` for retrieve sources.

### 13.3 Query Alias Scoping in Nested Contexts

**Problem:** When CQL queries define aliases (e.g., `from [Encounter] E`), these aliases must be properly scoped. In nested contexts (e.g., `return` clauses that contain sub-queries), inner aliases can shadow outer aliases, and correlated references to outer aliases may fail depending on nesting depth.

**Recommendation:** The translator should track alias scoping depth and, for deeply nested contexts, consider materializing intermediate results as CTEs rather than relying on correlated subqueries.

### 13.4 CTE Materialization Strategy

**Problem:** `MATERIALIZED` CTEs prevent DuckDB's optimizer from inlining them, which can increase memory usage and slow down queries when the CTE is small or used only once.

**Recommendation:** Make materialization selective rather than blanket:

| Scenario | Materialized? | Rationale |
|----------|---------------|-----------|
| Retrieve CTE reused by >1 definition | ✓ Yes | Avoid repeated FHIRPath JSON scans |
| Retrieve CTE used by only 1 definition | ✗ No | Let DuckDB inline for potential pushdown |
| Definition CTE with expensive computation | ✓ Yes | Avoid re-evaluation |
| Simple boolean/value definition | ✗ No | Inlining is often faster |

### 13.5 NULL Ordering in Window Functions

**Problem:** DuckDB defaults to `NULLS LAST` for ASC and `NULLS FIRST` for DESC. CQL expects nulls to sort to the "end" of collections.

**Recommendation:** Always specify `NULLS LAST` for ASC and `NULLS FIRST` for DESC explicitly in `ORDER BY` clauses within `ROW_NUMBER()` and other window functions to ensure consistent behavior across DuckDB versions.

---

## 14. SQL AST Node Reference

The translator uses an intermediate SQL AST representation. Key node types:

| Node Type | Purpose | Key Fields |
|-----------|---------|------------|
| `SQLSelect` | SELECT statement | `columns`, `from_clause`, `where`, `joins`, `group_by`, `order_by`, `limit`, `qualify` |
| `SQLIdentifier` | Table/column name | `name` |
| `SQLQualifiedIdentifier` | Table.column reference | `table`, `column` |
| `SQLAlias` | Aliased expression | `expr`, `alias` |
| `SQLBinaryOp` | Binary operation | `left`, `op`, `right` |
| `SQLFunctionCall` | Function invocation | `name`, `args` |
| `SQLLiteral` | Literal value | `value` |
| `SQLSubquery` | Wrapped subquery | `query` (SQLSelect) |
| `SQLUnion` | UNION / UNION ALL | `queries` (list of SQLSelect), `distinct` (bool, default False) |
| `RetrievePlaceholder` | Unresolved retrieve reference | `resource_type`, `valueset`, resolved in Phase 3 |
| `SQLCase` | CASE/WHEN | `when_clauses`, `else_clause` |
| `SQLExists` | EXISTS subquery | `query` |
| `SQLCast` | Type cast | `expr`, `type_name` |
| `SQLWindowFunction` | Window function | `func`, `partition_by`, `order_by` |
| `SQLJoin` | JOIN clause | `table`, `condition`, `join_type` |
| `SQLRetrieveCTE` | Retrieve CTE definition | `name`, `resource_type`, `columns`, `materialized` |

**Important:** `SQLSelect.limit` is `Optional[int]` (not a SQL expression). `SQLFunctionCall.to_sql()` automatically wraps `SQLSelect` arguments in parentheses.

**Design guideline:** Avoid using raw SQL strings (`SQLRaw`) in the AST except for very constrained, non-user-influenced cases. All type casts should use `SQLCast` nodes, not string concatenation with `::`. The `SQLUnion` node now supports a `distinct` flag to differentiate `UNION` (distinct=True) from `UNION ALL` (distinct=False), reflecting the corrected set operation semantics from §3.7.

---

## Appendix A: FHIRPath Functions Supported

The `duckdb-fhirpath-py` extension supports:

| Function | Description |
|----------|-------------|
| `where(predicate)` | Filter collection by predicate |
| `exists(predicate)` | Check if any element matches |
| `extension(url)` | Get extension by URL |
| `first()` | Get first element |
| `last()` | Get last element |
| `code`, `coding`, `system` | Navigate code structures |

---

## Appendix B: CQL UDFs Available

The `duckdb-cql-py` extension provides:

| UDF | Purpose |
|-----|---------|
| `getvariable(name)` | Get runtime parameter |
| `setvariable(name, value)` | Set runtime parameter |
| `in_valueset(resource, path, url)` | Valueset membership |
| `intervalStart(interval)` | Get interval start |
| `intervalEnd(interval)` | Get interval end |
| `intervalFromBounds(s, e, lowClosed, highClosed)` | Create interval |
| `intervalOverlaps(a, b)` | Check interval overlap |
| `parse_quantity(json)` | Parse quantity from JSON |
| `quantity_lt(a, b)` | Quantity less than |
| `AgeInYearsAt(patient, date)` | Calculate age at date |
| `Latest(resources, datePath)` | Get resource with latest date |
| `Earliest(resources, datePath)` | Get resource with earliest date |

---

## Appendix C: Full SQL Examples

### C.1 CTE Target Structure (Full SQL)

```sql
WITH
-- ============================================================================
-- PATIENTS
-- ============================================================================
_patients AS (
    SELECT DISTINCT patient_ref AS patient_id
    FROM resources
    WHERE patient_ref IS NOT NULL
),
_patient_demographics AS (
    SELECT
        t1.patient_id,
        fhirpath_date(t2.resource, 'birthDate')::DATE AS birth_date,
        -- Birthday-aware age (precomputed for efficiency)
        (...)::INTEGER AS age_at_mp_end
    FROM _patients t1
    INNER JOIN resources t2 ON t2.patient_ref = t1.patient_id AND t2.resourceType = 'Patient'
),

-- ============================================================================
-- RETRIEVES (all resource-type CTEs - with or without valueset, includes indexes)
-- ============================================================================
"Observation" AS (
    -- May include profile-specific precomputed columns
    SELECT t1.patient_ref AS patient_id, t1.resource,
           fhirpath_date(t1.resource, 'effectiveDateTime')::DATE AS effective_date,
           ...
    FROM resources t1
    WHERE t1.resourceType = 'Observation'
),
"Encounter" AS (
    -- Includes encounter index columns (id, class) for efficient joins
    SELECT t1.patient_ref AS patient_id, t1.resource,
           json_extract_string(t1.resource, '$.id') AS encounter_id,
           json_extract_string(t1.resource, '$.class.code') AS class_code,
           ...
    FROM resources t1
    WHERE t1.resourceType = 'Encounter'
),
"Condition: Essential Hypertension" AS (
    -- Valueset-filtered retrieve with precomputed columns
    SELECT t1.patient_ref AS patient_id, t1.resource, ...
    FROM resources t1
    WHERE t1.resourceType = 'Condition'
      AND in_valueset(t1.resource, 'code', 'http://...')
),
...

-- ============================================================================
-- EXTERNAL LIBRARY DEFINES (before main library)
-- ============================================================================
"Hospice.Has Hospice Services" AS (...),
"AdultOutpatientEncounters.Qualifying Encounters" AS (...),
"PalliativeCare.Has Palliative Care in the Measurement Period" AS (...),
"AIFrailLTCF.Is Age 66-80 with Advanced Illness and Frailty or Age 81+ with Frailty" AS (...),
"SupplementalDataElements.SDE Ethnicity" AS (...),
...

-- ============================================================================
-- MAIN LIBRARY DEFINES
-- ============================================================================
"Essential Hypertension Diagnosis" AS (...),
"Initial Population" AS (...),
"Denominator" AS (...),
"Numerator" AS (...),
...

-- ============================================================================
-- FINAL OUTPUT
-- ============================================================================
SELECT
    t1.patient_id,
    CASE WHEN t2.patient_id IS NOT NULL THEN TRUE ELSE FALSE END AS "Initial Population",
    ...
FROM _patients t1
LEFT JOIN "Initial Population" t2 ON t2.patient_id = t1.patient_id
...
ORDER BY t1.patient_id
```

### C.2 Precomputed Column Generation Examples

**Simple Property:**
```
Detected: X.status
Column: fhirpath_text(t1.resource, 'status') AS status
```

**Choice Type Property:**
```
Detected: X.effective (choice type)
Column: COALESCE(
            fhirpath_date(t1.resource, 'effectiveDateTime'),
            fhirpath_date(t1.resource, 'effectivePeriod.start'),
            fhirpath_date(t1.resource, 'effectiveInstant')
        )::DATE AS effective_date
```

**Filtered Array Access:**
```
Detected: singleton from(X.component C where C.code ~ "Systolic")
Column: fhirpath_number(t1.resource, 'component.where(code.coding.exists(code = ''8480-6'')).valueQuantity.value') AS systolic_value
```

**Full Example - Essential Hypertension Diagnosis:**

**CQL:**
```cql
define "Essential Hypertension Diagnosis":
  [Condition: "Essential Hypertension"] C
    where C.verified()
      and C.onset during day of "Measurement Period"
```

**Phase 1 Scan Detects:**
- Condition.verificationStatus (from verified() function body)
- Condition.onset (from interval comparison)

**Phase 2 Generate CTE:**
```sql
"Condition: Essential Hypertension" AS (
    SELECT
        t1.patient_ref AS patient_id,
        t1.resource,
        COALESCE(
            fhirpath_date(t1.resource, 'onsetDateTime'),
            fhirpath_date(t1.resource, 'onsetPeriod.start')
        )::DATE AS onset_date,
        fhirpath_text(t1.resource, 'verificationStatus.coding[0].code') AS verification_status
    FROM resources t1
    WHERE t1.resourceType = 'Condition'
      AND in_valueset(t1.resource, 'code', 'http://...')
)
```

**Definition CTE uses precomputed columns:**
```sql
"Essential Hypertension Diagnosis" AS (
    SELECT t1.patient_id
    FROM "Condition: Essential Hypertension" t1
    WHERE (t1.verification_status IS NULL OR t1.verification_status IN (...))
      AND t1.onset_date >= mp_start
      AND t1.onset_date < mp_end
)
```

### C.3 Hospice UNION ALL Example

**CQL (Hospice.cql):**
```cql
define "Has Hospice Services":
  exists ([Encounter: "Hospice Encounter"] E
    where E.period ends during day of "Measurement Period")
  or exists ([Condition: "Hospice Diagnosis"] D
    where prevalenceInterval(D) overlaps day of "Measurement Period")
  or ...
```

**SQL:**
```sql
"Hospice.Has Hospice Services" AS (
    SELECT t1.patient_id FROM "Encounter: Hospice Encounter" t1
    WHERE t1.status = 'finished'
      AND COALESCE(t1.period_end, t1.period_start) >= mp_start
      AND COALESCE(t1.period_end, t1.period_start) < mp_end
    UNION ALL
    SELECT t1.patient_id FROM "Condition: Hospice Diagnosis" t1
    WHERE (... verified() ...)
      AND t1.onset_date < mp_end
      AND COALESCE(t1.abatement_date, DATE '9999-12-31') >= mp_start
    UNION ALL
    ...
),
```

### C.4 Profile-Specific CTE Example (Blood Pressure)

**CQL Usage:**
```cql
// CQL accesses these properties on Observation:
BPReading.effective.latest()           -- needs effective_date
BPReading.status                        -- needs status
BPReading.component where code ~ "..." -- needs systolic/diastolic values
```

**Generated CTE:**
```sql
"Observation" AS (
    SELECT
        t1.patient_ref AS patient_id,
        t1.resource,
        COALESCE(
            fhirpath_date(t1.resource, 'effectiveDateTime'),
            fhirpath_date(t1.resource, 'effectivePeriod.start'),
            fhirpath_date(t1.resource, 'effectiveInstant')
        )::DATE AS effective_date,
        fhirpath_text(t1.resource, 'status') AS status,
        fhirpath_number(t1.resource, 'component.where(code.coding.exists(code = ''8480-6'')).valueQuantity.value') AS systolic_value,
        fhirpath_number(t1.resource, 'component.where(code.coding.exists(code = ''8462-4'')).valueQuantity.value') AS diastolic_value
    FROM resources t1
    WHERE t1.resourceType = 'Observation'
      AND (... profile or LOINC code filter ...)
)
```

---

## Appendix D: Out-of-Scope CQL Features

The following CQL features are **not currently supported** by this translator. They are documented here for completeness and to prevent confusion when encountering them in CQL libraries.

### D.1 Not Supported (Reject with Error)

| Feature | CQL Example | Reason |
|---------|-------------|--------|
| Non-Patient context | `context Practitioner` | Translator assumes Patient context exclusively (see §4.4.2) |
| `Any` / `All` quantifiers | `Any([Condition] C where ...)` | Requires predicate-scoped list evaluation |
| `flatten` | `flatten(ListOfLists)` | Nested list flattening not modeled in SQL AST |
| `collapse` | `collapse(IntervalList)` | Interval merging requires procedural logic |
| `expand` | `expand(IntervalList, per 1 day)` | Interval expansion to discrete points |
| `Combine` / `Split` | `Combine(StringList, ',')` | String list operations |
| Tuple construction | `Tuple { x: 1, y: 2 }` | Arbitrary tuple types not mapped to SQL |
| Related context queries | `[Condition] C where C.encounter.reference = ...` | Cross-resource graph traversal |

### D.2 Partially Supported (Known Limitations)

| Feature | CQL Example | Limitation |
|---------|-------------|------------|
| `distinct` | `distinct(X.code)` | Supported via `SELECT DISTINCT`, but not fully tested for all source shapes |
| `contains` (list membership) | `X contains 'value'` | Supported as `IN` for simple cases; not supported for list-typed columns |
| `skip` / `take` | `X skip 5 take 10` | Not commonly used in measures; can map to `OFFSET`/`LIMIT` if needed |
| List indexing | `X[0]` | Supported in FHIRPath paths; not supported as standalone CQL expression |
| Implicit type conversions | `Integer` to `Decimal` promotion | Basic casts supported; full CQL type promotion rules not implemented |
| Interval boundary inclusivity | `Interval[1, 10)` | Open/closed boundaries partially handled; null endpoint = "ongoing" is handled via `COALESCE(..., '9999-12-31')` |
| `singleton from` cardinality enforcement | `singleton from X` | Fully supported via `CASE WHEN COUNT(*) = 1 THEN ... ELSE NULL END` (see §3.12) |

### D.3 Future Consideration

| Feature | CQL Example | Notes |
|---------|-------------|-------|
| `Avg` / `StdDev` / `Variance` | `Avg(X.value)` | Standard SQL aggregates; straightforward to add |
| `ToList` / `ToInterval` | `ToList(X)` | Conversion functions; map to DuckDB LIST type |
| Message / Trace | `Message(expr, ...)` | Debugging functions; no SQL equivalent |
| Concept equivalence | `X ~ ConceptValue` | Full Code/Concept matching beyond valueset membership |
