# Design Document: Context-Aware CQL-to-SQL Translation

**Version**: 3.0  
**Date**: 2026-02-27  
**Status**: Authoritative Design  
**Supersedes**: Version 2.0 (2025-02-24)  
**Cross-Reference**: `.omc/plans/cql-translator-technical-spec.md` for pattern mappings and SQL examples

---

## 1. Executive Summary

This document describes a **context-aware translation architecture** for converting CQL (Clinical Quality Language) to DuckDB SQL using FHIRPath UDFs. The architecture addresses critical performance and correctness issues in naive translation approaches.

### Key Principles

1. **Pure AST pipeline**: CQL AST → SQL AST → `to_sql()` only at the very end. **No string-based SQL inspection or manipulation.**
2. **ExprUsage tracks consumption**: How an expression result is used (EXISTS, SCALAR, BOOLEAN, LIST)
3. **RowShape tracks production**: What a definition produces (PATIENT_SCALAR, PATIENT_MULTI_VALUE, RESOURCE_ROWS)
4. **Shape-driven CTE wrapping**: `DefinitionMeta.shape` mechanically determines how each definition CTE is constructed — no heuristics, no string pattern matching
5. **Three-phase translation**: Translate → Build CTEs → Resolve placeholders
6. **Patient context only**: Only `context Patient` is supported; other contexts are rejected early
7. **Translator is library-agnostic**: The translator derives behavior from the FHIR schema and the CQL libraries themselves. No hardcoded library names (`FHIRHelpers`, `QICoreCommon`, etc.) in control flow.
8. **FHIR knowledge lives in configuration**: Version-specific extension URLs, profile mappings, and choice type paths live in versioned config files (`qicore-profiles.json`, `fhir-r4-X.Y.Z/`) — not as Python literals.
9. **Parameters are generic**: CQL parameters are bound by the caller via `parameter_bindings`. The translator does not special-case any parameter name (including "Measurement Period").
10. **Optimizations are explicit and registered**: SQL generation strategies for known CQL functions are registered in `FunctionTranslationRegistry` — not as ad-hoc `if function_name ==` branches. See `cql-py/src/cql_py/translator/function_registry.py`.

### Core Problem Solved

Naive translation creates O(n²) correlated subqueries:

```sql
-- SLOW: Executes subquery once per patient row
SELECT p.patient_id,
       EXISTS (SELECT 1 FROM "Diabetes" d WHERE d.patient_id = p.patient_id)
FROM _patients p
```

Context-aware translation produces O(n) JOINs:

```sql
-- FAST: Single JOIN operation
SELECT p.patient_id, j1.patient_id IS NOT NULL AS has_diabetes
FROM _patients p
LEFT JOIN (SELECT DISTINCT patient_id FROM "Diabetes") j1 ON j1.patient_id = p.patient_id
```

### Critical Design Rule: No String Manipulation

The translator **must never** inspect or manipulate SQL text mid-pipeline. All decisions must be made using AST metadata:

| ❌ Never do this | ✅ Do this instead |
|------------------|-------------------|
| `if "FROM resources" in sql.upper()` | Check `isinstance(expr, RetrievePlaceholder)` |
| `if "patient_id" not in sql.lower()` | Check `meta.shape == RowShape.PATIENT_SCALAR` |
| `if self._is_boolean_expression(sql)` | Check `meta.cql_type == "Boolean"` |
| `sql.replace("SELECT *", "SELECT patient_id")` | Build a new `SQLSelect` node |
| `f"SELECT p.patient_id, ({sql}) AS value"` | Compose `SQLSelect` with `SQLAlias` nodes |

The only place `to_sql()` is called is the **final assembly step** after all AST transformations are complete.

---

## 2. Core Data Structures

### 2.1 ExprUsage Enum

Tracks **how** an expression's result will be consumed.

```python
class ExprUsage(Enum):
    """How an expression result will be used."""
    LIST = auto()      # Return collection (default CQL semantics)
    SCALAR = auto()    # Need single value (property access, comparison operand)
    BOOLEAN = auto()   # Truth test (WHERE clause, AND/OR operands)
    EXISTS = auto()    # Existence check (exists() function)
```

**Usage context determination:**

| CQL Context | ExprUsage |
|-------------|-----------|
| `[Condition]` (standalone) | LIST |
| `X.property` where X is RESOURCE_ROWS or PATIENT_MULTI_VALUE | LIST (for X — project across all rows) |
| `X.property` where X is PATIENT_SCALAR | SCALAR (for X — single value) |
| `Diabetes.status = 'confirmed'` | SCALAR (for operands) |
| `where C.active` | BOOLEAN |
| `exists [Condition]` | EXISTS |
| `A and B` | BOOLEAN (for operands) |
| `Count(X)`, `Sum(X)` | LIST (for X — needs all rows) |
| `if X then A else B` | BOOLEAN (for X); parent's usage (for A, B) |
| `coalesce(X, Y)` | SCALAR (for X, Y) |

### 2.2 RowShape Enum

Tracks **what** a definition produces in terms of rows per patient.

```python
class RowShape(Enum):
    """What a definition produces."""
    PATIENT_SCALAR = auto()       # Exactly 1 row per patient (boolean, number, string)
    PATIENT_MULTI_VALUE = auto()  # 0..N scalar value rows per patient (no resource column)
    RESOURCE_ROWS = auto()        # 0..N resource rows per patient (has resource column)
    UNKNOWN = auto()              # Forward reference or complex expression
```

**Key distinction:** `PATIENT_MULTI_VALUE` vs `RESOURCE_ROWS` — both can produce multiple rows per patient, but `PATIENT_MULTI_VALUE` rows contain only projected scalar values (no `resource` JSON column). This matters for JOIN strategies, downstream consumption, and `singleton from` behavior.

**Shape inference rules:**

| Expression Type | Output Shape |
|-----------------|--------------|
| `[Resource]` (Retrieve) | RESOURCE_ROWS |
| `exists [Resource]` | PATIENT_SCALAR |
| `First([Resource])` | PATIENT_SCALAR |
| `Count([Resource])` | PATIENT_SCALAR |
| `Sum/Avg/Min/Max` | PATIENT_SCALAR |
| `X.property` where X is RESOURCE_ROWS | PATIENT_MULTI_VALUE (projection) |
| `X.property` where X is PATIENT_SCALAR | PATIENT_SCALAR |
| `X.property` where X is PATIENT_MULTI_VALUE | PATIENT_MULTI_VALUE |
| `union`/`intersect`/`except` | Shape of sources (RESOURCE_ROWS if any source is) |
| `distinct(X)` | Same shape as X |
| Binary comparison (`=`, `>`) | PATIENT_SCALAR |
| Logical operators (`and`, `or`) | PATIENT_SCALAR |
| `if/case` | Shape of branches (RESOURCE_ROWS if any branch is) |
| Query with `return` (scalar projection) | PATIENT_MULTI_VALUE |
| Query with `return` (resource passthrough) | RESOURCE_ROWS |

### 2.3 DefinitionMeta

Metadata tracked per translated definition. This is the **single source of truth** for CTE wrapping decisions.

```python
@dataclass
class DefinitionMeta:
    """Metadata about a translated definition."""
    name: str
    shape: RowShape
    cql_type: str = "Any"           # Boolean, Integer, String, Resource, List<T>
    has_resource: bool = False      # CTE includes resource column
    value_column: str = "value"     # Column containing scalar result
    patient_key_col: str = "patient_id"

    @property
    def is_multi_row(self) -> bool:
        """True if this definition can produce multiple rows per patient."""
        return self.shape in (RowShape.RESOURCE_ROWS, RowShape.PATIENT_MULTI_VALUE)
```

### 2.4 CTEReference

Tracks references to CTEs for JOIN generation.

```python
@dataclass
class CTEReference:
    """Tracks a CTE reference that may need to be JOINed."""
    cte_name: str
    semantic_alias: str              # CQL alias (E1, E2 for self-joins)
    alias: str                       # SQL alias (j1, j2, etc.)
    usages: Set[ExprUsage] = field(default_factory=set)
    shape: RowShape = RowShape.UNKNOWN

    # For inter-resource correlation (with...such that)
    correlates_to_alias: Optional[str] = None
    additional_predicates: List[SQLExpression] = field(default_factory=list)

    @property
    def can_use_distinct(self) -> bool:
        """DISTINCT only safe if ALL usages are EXISTS/BOOLEAN."""
        return self.usages.issubset({ExprUsage.EXISTS, ExprUsage.BOOLEAN})

    @property
    def needs_full_cte(self) -> bool:
        """Needs full CTE (not DISTINCT) if any usage requires resource/value."""
        return ExprUsage.SCALAR in self.usages or ExprUsage.LIST in self.usages
```

### 2.5 Context + Shape → SQL Pattern Matrix

The combination of shape and context **mechanically** determines the SQL pattern:

| Shape | Context | Safe? | SQL Pattern |
|-------|---------|-------|-------------|
| PATIENT_SCALAR | EXISTS | ✓ | `LEFT JOIN cte ... WHERE cte.patient_id IS NOT NULL` |
| PATIENT_SCALAR | SCALAR / BOOLEAN | ✓ | `LEFT JOIN cte ... SELECT cte.value_column` |
| PATIENT_SCALAR | LIST | ✓ | `LEFT JOIN cte ...` |
| PATIENT_MULTI_VALUE | EXISTS | ✓ | `LEFT JOIN (SELECT DISTINCT patient_id FROM cte) ...` |
| PATIENT_MULTI_VALUE | SCALAR | ⚠️ | **Error**: Use `First()`, `Last()`, or `singleton from` |
| PATIENT_MULTI_VALUE | BOOLEAN | ⚠️ | **Error**: Use `exists()` or `Count() > 0` |
| PATIENT_MULTI_VALUE | LIST | ✓ | `FROM cte` |
| RESOURCE_ROWS | EXISTS | ✓ | `LEFT JOIN (SELECT DISTINCT patient_id FROM cte) ...` |
| RESOURCE_ROWS | SCALAR | ⚠️ | **Error**: Use `First()`, `Last()`, or `singleton from` |
| RESOURCE_ROWS | BOOLEAN | ⚠️ | **Error**: Use `exists()` or `Count() > 0` |
| RESOURCE_ROWS | LIST | ✓ | `FROM cte` |

---

## 3. Three-Phase Translation Pipeline

### 3.1 Overview

Translation proceeds in three distinct phases. Each expression is translated **exactly once** in Phase 1. No re-translation occurs.

```
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 1: TRANSLATION & ANALYSIS                 │
├─────────────────────────────────────────────────────────────────┤
│  1. Parse all definitions                                        │
│  2. Topologically sort by dependencies                           │
│  3. For each definition:                                         │
│     a. Translate CQL AST → SQL AST (retrieves → placeholders)   │
│     b. Scan for property accesses per resource type               │
│     c. Collect definition references and usage contexts           │
│     d. Infer RowShape and record DefinitionMeta                  │
│  4. Compute required precomputed columns per retrieve             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 2: CTE CONSTRUCTION                       │
├─────────────────────────────────────────────────────────────────┤
│  1. Build retrieve CTEs with precomputed columns                 │
│  2. Build definition CTEs in dependency order:                   │
│     a. Create fresh SQLQueryBuilder (scoped to this definition)  │
│     b. Use the SQL AST from Phase 1 (not re-translated)          │
│     c. Wrap in patient-scoped SELECT based on DefinitionMeta:    │
│        - PATIENT_SCALAR boolean → SELECT p.patient_id WHERE expr │
│        - PATIENT_SCALAR value   → SELECT p.patient_id, expr AS v │
│        - RESOURCE_ROWS          → use translated SELECT directly │
│        - PATIENT_MULTI_VALUE    → use translated SELECT directly │
│     d. Append LEFT JOINs for referenced CTEs                     │
│  3. Record final CTE names                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 3: PLACEHOLDER RESOLUTION                 │
├─────────────────────────────────────────────────────────────────┤
│  1. Walk the complete SQL AST tree                               │
│  2. Replace each RetrievePlaceholder with SQLIdentifier          │
│     referencing the actual CTE name                              │
│  3. Replace fhirpath_*(resource, 'path') calls with              │
│     precomputed column references where available                │
│  4. Assemble final SQL string via to_sql()                       │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Phase 1: Translation & Analysis

```python
def _phase1_translate_and_analyze(self, library: Library) -> Phase1Result:
    """Phase 1: Translate all definitions, collecting metadata."""
    result = Phase1Result()

    definitions = library.definitions
    sorted_defs = self._topological_sort(definitions)

    for defn in sorted_defs:
        # Translate CQL AST → SQL AST (retrieves become placeholders)
        sql_ast = self._translate_expression(defn.expression)

        # Infer shape from CQL expression structure
        shape = self._infer_row_shape(defn.expression)
        cql_type = self._infer_cql_type(defn.expression)

        # Record metadata — this drives all CTE wrapping in Phase 2
        self._context.definition_meta[defn.name] = DefinitionMeta(
            name=defn.name,
            shape=shape,
            cql_type=cql_type,
            has_resource=(shape == RowShape.RESOURCE_ROWS),
            value_column=self._infer_value_column(defn.expression),
        )

        # Store AST for Phase 2
        result.definition_asts[defn.name] = sql_ast

        # Find placeholders and scan for property accesses
        placeholders = find_all_placeholders(sql_ast)
        result.placeholders.extend(placeholders)
        property_map = scan_definition_for_properties(sql_ast, placeholders)
        for key, props in property_map.items():
            result.property_usage.setdefault(key, set()).update(props)

    return result
```

### 3.3 Phase 2: CTE Construction

CTE wrapping is **mechanically determined** by `DefinitionMeta.shape`. No string inspection.

```python
def _phase2_build_ctes(self, phase1: Phase1Result) -> Phase2Result:
    """Phase 2: Build retrieve and definition CTEs."""
    result = Phase2Result()

    # Build retrieve CTEs with precomputed columns
    for (resource_type, valueset) in phase1.all_retrieve_keys():
        properties = phase1.get_properties_for_retrieve(resource_type, valueset)
        cte_name, cte_ast, col_info = build_retrieve_cte(
            resource_type, valueset, properties, self._context
        )
        result.register_cte(resource_type, valueset, cte_name, cte_ast, col_info)

    # Build definition CTEs
    for name, sql_ast in phase1.definition_asts.items():
        meta = self._context.definition_meta[name]
        cte_ast = self._wrap_definition_cte(name, sql_ast, meta)
        result.definition_ctes[name] = cte_ast

    return result

def _wrap_definition_cte(
    self,
    name: str,
    sql_ast: SQLExpression,
    meta: DefinitionMeta,
) -> SQLSelect:
    """
    Wrap a definition's SQL AST in a patient-scoped CTE.

    The wrapping strategy is ENTIRELY determined by DefinitionMeta.shape.
    No string inspection. No heuristics.
    """
    if meta.shape == RowShape.PATIENT_SCALAR and meta.cql_type == "Boolean":
        # Boolean definition: SELECT p.patient_id FROM _patients AS p WHERE <expr>
        return SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["p", "patient_id"])],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name="_patients"),
                alias="p",
            ),
            where=sql_ast,
            joins=self._generate_joins_for_definition(name),
        )

    elif meta.shape == RowShape.PATIENT_SCALAR:
        # Value definition: SELECT p.patient_id, <expr> AS <value_col> FROM _patients AS p
        return SQLSelect(
            columns=[
                SQLQualifiedIdentifier(parts=["p", "patient_id"]),
                SQLAlias(expr=sql_ast, alias=meta.value_column),
            ],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name="_patients"),
                alias="p",
            ),
            joins=self._generate_joins_for_definition(name),
        )

    elif meta.shape in (RowShape.RESOURCE_ROWS, RowShape.PATIENT_MULTI_VALUE):
        # Resource/multi-value: use the translated SELECT directly
        # It already has patient_id from the retrieve CTE or query source
        if isinstance(sql_ast, SQLSelect):
            # Add any needed JOINs
            joins = self._generate_joins_for_definition(name)
            if joins:
                existing = sql_ast.joins or []
                sql_ast = sql_ast.with_joins(existing + joins)
            return sql_ast
        else:
            # Non-SELECT expression producing rows — wrap with retrieve source
            return sql_ast

    else:
        raise TranslationError(
            f"Cannot build CTE for definition '{name}' with shape {meta.shape}"
        )
```

### 3.4 Phase 3: Placeholder Resolution

```python
def _phase3_resolve(
    self,
    phase1: Phase1Result,
    phase2: Phase2Result,
) -> Dict[str, SQLExpression]:
    """Phase 3: Resolve placeholders and optimize property access."""
    resolved = {}

    for name, ast in phase1.definition_asts.items():
        # Replace RetrievePlaceholder → SQLIdentifier (CTE name)
        resolved_ast = resolve_placeholders(ast, phase2.cte_name_map)

        # Replace fhirpath calls with precomputed column references
        resolved_ast = optimize_property_access(resolved_ast, phase2.column_registry)

        resolved[name] = resolved_ast

    return resolved
```

### 3.5 Scoped Query Builder

Each definition gets a **fresh** `SQLQueryBuilder` to prevent JOIN leakage between CTEs.

```python
def _translate_definition(self, defn: Definition) -> SQLExpression:
    """Translate a single definition with its own scoped builder."""
    # Fresh builder — prevents JOIN leakage
    query_builder = SQLQueryBuilder(context=self._context)
    old_builder = self._context.query_builder
    self._context.query_builder = query_builder

    try:
        # Translate expression — registers JOINs in fresh builder
        sql_ast = self._translate_expression(defn.expression)

        # Validate for unsafe patterns
        warnings = query_builder.validate_joins()
        for w in warnings:
            self._context.warnings.add(w)

        return sql_ast
    finally:
        # Restore previous builder
        self._context.query_builder = old_builder
```

---

## 4. Translation Rules

### 4.1 Hybrid JOIN Strategy

Pure JOIN conversion is not always safe. The strategy is determined by source shape and usage context.

```
For each CTE reference in expression:
    │
    ├─ Is source shape PATIENT_SCALAR?
    │   └─ YES → Use LEFT JOIN (safe, no fanout possible)
    │
    ├─ Is source shape RESOURCE_ROWS or PATIENT_MULTI_VALUE?
    │   │
    │   ├─ Is usage EXISTS/BOOLEAN only?
    │   │   └─ YES → Use DISTINCT JOIN (no fanout)
    │   │
    │   ├─ Are there OTHER multi-row refs in same scope?
    │   │   └─ YES → Use AGGREGATION strategy or ERROR
    │   │
    │   ├─ Is this inside a conditional branch?
    │   │   └─ YES → Use CORRELATED SUBQUERY
    │   │
    │   ├─ Is this a self-join (same CTE, different alias)?
    │   │   └─ YES → Use multiple JOINs with semantic aliases
    │   │
    │   └─ Otherwise → Use single JOIN
    │
    └─ Is source shape UNKNOWN?
        └─ Use CORRELATED SUBQUERY (safe fallback)
```

### 4.2 SQL Pattern Selection

| CQL Expression | Source Shape | Usage | SQL Pattern |
|----------------|--------------|-------|-------------|
| `exists [Condition]` | RESOURCE_ROWS | EXISTS | `LEFT JOIN (SELECT DISTINCT patient_id) ... IS NOT NULL` |
| `Count([Condition])` | RESOURCE_ROWS | SCALAR | `(SELECT COUNT(*) FROM ... WHERE patient_id = p.patient_id)` |
| `First([Condition])` | RESOURCE_ROWS | SCALAR | `ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY ... ) WHERE rn=1` |
| `[Condition].status` | RESOURCE_ROWS | LIST | PATIENT_MULTI_VALUE projection |
| `exists Definition` | PATIENT_SCALAR | EXISTS | `LEFT JOIN ... IS NOT NULL` |
| `Definition.value` | PATIENT_SCALAR | SCALAR | `LEFT JOIN ... SELECT value` |
| `A and B` (both multi-row) | multi-row | BOOLEAN | Pre-aggregate or error |
| `if X then A else B` | RESOURCE_ROWS in branch | varies | Correlated subquery in CASE |

### 4.3 Identifier Translation with Shape Checking

```python
def _translate_identifier(self, ident: Identifier, usage: ExprUsage) -> SQLExpression:
    name = ident.name
    meta = self.context.definition_meta.get(name)

    if meta is None:
        # Forward reference or unknown — safe fallback.
        #
        # When does this occur? CQL prohibits circular dependencies, so
        # topological sort (Phase 1) eliminates all same-library forward
        # references. The only cases where meta is None at translation time:
        #   1. Cross-library references to external library defines not yet
        #      processed (e.g., a define that references Hospice before the
        #      Hospice library CTEs have been registered).
        #   2. Built-in system functions that resolve to defines at runtime.
        # In both cases a correlated subquery is the safe fallback.
        self._context.warnings.add(
            category="PERFORMANCE",
            message="Forward reference caused fallback to correlated subquery",
            definition=name,
        )
        return self._build_correlated_subquery(name)

    # Route based on shape
    if meta.is_multi_row:
        return self._handle_multi_row_reference(name, meta, usage)
    else:
        return self._handle_scalar_reference(name, meta, usage)

def _handle_multi_row_reference(
    self, name: str, meta: DefinitionMeta, usage: ExprUsage
) -> SQLExpression:
    """Handle reference to RESOURCE_ROWS or PATIENT_MULTI_VALUE definition."""

    if usage in (ExprUsage.EXISTS, ExprUsage.BOOLEAN):
        # Safe: JOIN against DISTINCT patient_id
        alias = self.context.query_builder.track_cte_reference(
            name, usage=usage, shape=meta.shape
        )
        return SQLBinaryOp(
            operator="IS NOT",
            left=SQLQualifiedIdentifier(parts=[alias, "patient_id"]),
            right=SQLNull(),
        )

    elif usage == ExprUsage.SCALAR:
        # Unsafe: multi-row used as scalar — error
        raise TranslationError(
            f"Definition '{name}' returns multiple rows per patient "
            f"but is used in scalar context.",
            definition=name,
            suggestion="Use First(), Last(), or singleton from to select a single value",
        )

    else:  # LIST
        return self._build_correlated_subquery(name)

def _handle_scalar_reference(
    self, name: str, meta: DefinitionMeta, usage: ExprUsage
) -> SQLExpression:
    """Handle reference to PATIENT_SCALAR definition."""

    alias = self.context.query_builder.track_cte_reference(
        name, usage=usage, shape=meta.shape
    )

    if usage == ExprUsage.SCALAR:
        return SQLQualifiedIdentifier(parts=[alias, meta.value_column])
    else:  # EXISTS/BOOLEAN
        return SQLBinaryOp(
            operator="IS NOT",
            left=SQLQualifiedIdentifier(parts=[alias, "patient_id"]),
            right=SQLNull(),
        )
```

---

## 5. Critical Safety Mechanisms

### 5.1 Cartesian Fanout Prevention

**Problem**: JOINing any `cardinality=MANY` CTE into a patient-scoped query risks row multiplication.

```cql
define Diabetes: [Condition: "Diabetes"]        -- 3 rows for Patient A
define Hypertension: [Condition: "Hypertension"] -- 2 rows for Patient A
define Combined: Diabetes.status and Hypertension.status
-- BUG: Patient A gets 6 rows (3 × 2)
```

**Detection**: Flag as unsafe when any multi-row CTE is joined into a patient-scoped wrapper, or when multiple multi-row CTEs are referenced in the same scope.

**Guardrail rule**: Any time a patient-scoped wrapper joins a source with `is_multi_row=True`, the translator must either:
1. **Aggregate to 1 row per patient** (`GROUP BY patient_id`)
2. **Join only a DISTINCT patient_id projection** (EXISTS-style)
3. **Use a window-limited join** (`ROW_NUMBER() WHERE rn = 1`)

```python
class SQLQueryBuilder:
    def validate_joins(self) -> List[TranslationWarning]:
        """Check for Cartesian fanout risk."""
        warnings = []

        multi_row_refs = [
            ref for ref in self.cte_references.values()
            if ref.shape in (RowShape.RESOURCE_ROWS, RowShape.PATIENT_MULTI_VALUE)
            and not ref.can_use_distinct
        ]

        if len(multi_row_refs) > 1:
            names = [r.cte_name for r in multi_row_refs]
            raise TranslationError(
                f"Multiple multi-row CTEs in same scope: {names}. "
                f"This causes Cartesian fanout.",
                suggestion="Use exists() or Count() to aggregate before combining",
            )

        return warnings
```

### 5.2 Multi-Usage CTE Tracking

**Problem**: Same CTE referenced with different usages.

```cql
define Diabetes: [Condition: "Diabetes"]
define X: exists Diabetes and Diabetes.status = 'confirmed'
-- "Diabetes" used as EXISTS and SCALAR
```

**Solution**: Track set of usages, use most permissive JOIN strategy.

```python
def track_cte_reference(
    self,
    cte_name: str,
    semantic_alias: Optional[str] = None,
    usage: ExprUsage = ExprUsage.SCALAR,
    shape: RowShape = RowShape.UNKNOWN,
) -> str:
    """Track CTE reference, accumulating usages."""
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
            shape=shape,
        )
        return alias
```

### 5.3 Self-Join Support

**Problem**: Same CTE with different aliases.

```cql
define Encounters: [Encounter]
define BackToBack:
    from Encounters E1, Encounters E2
    where E2.start = E1.end
```

**Solution**: Key by `(cte_name, semantic_alias)`.

```python
alias1 = builder.track_cte_reference("Encounters", semantic_alias="E1", ...)
alias2 = builder.track_cte_reference("Encounters", semantic_alias="E2", ...)
# alias1 != alias2, both JOINs generated
```

### 5.4 Inter-Resource Correlation

**Problem**: `with...such that` needs predicates beyond patient_id.

```cql
define DiabetesWithA1C:
    Diabetes D with A1C O such that O.effective > D.onset
```

**Solution**: Store additional predicates in CTEReference.

```python
def generate_joins(self, patient_alias: str = "p") -> List[SQLJoin]:
    joins = []

    for ref in self.cte_references.values():
        correlation_alias = ref.correlates_to_alias or patient_alias

        on_condition = SQLBinaryOp(
            operator="=",
            left=SQLQualifiedIdentifier(parts=[ref.alias, "patient_id"]),
            right=SQLQualifiedIdentifier(parts=[correlation_alias, "patient_id"]),
        )

        for predicate in ref.additional_predicates:
            on_condition = SQLBinaryOp(
                operator="AND",
                left=on_condition,
                right=predicate,
            )

        if ref.can_use_distinct and ref.shape in (RowShape.RESOURCE_ROWS, RowShape.PATIENT_MULTI_VALUE):
            table = SQLSubquery(
                query=SQLSelect(
                    columns=[SQLIdentifier(name="patient_id")],
                    from_clause=SQLIdentifier(name=ref.cte_name, quoted=True),
                    distinct=True,
                )
            )
        else:
            table = SQLIdentifier(name=ref.cte_name, quoted=True)

        joins.append(SQLJoin(
            join_type="LEFT",
            table=table,
            alias=ref.alias,
            on_condition=on_condition,
        ))

    return joins
```

### 5.5 Conditional RESOURCE_ROWS Handling

**Problem**: `if/else` with RESOURCE_ROWS branches causes eager evaluation of both.

**Solution**: Detect RESOURCE_ROWS in conditional branches, use correlated subquery.

```python
def _translate_conditional(self, expr: ConditionalExpression, usage: ExprUsage) -> SQLExpression:
    then_shape = self._infer_row_shape(expr.then_expr)
    else_shape = self._infer_row_shape(expr.else_expr)

    if then_shape == RowShape.RESOURCE_ROWS or else_shape == RowShape.RESOURCE_ROWS:
        return self._translate_conditional_with_subqueries(expr, usage)

    return self._translate_conditional_with_joins(expr, usage)
```

### 5.6 NULL Handling (3-Valued Logic)

CQL and SQL 3-valued logic are largely compatible:

| CQL Expression | CQL Result | SQL Equivalent | Match? |
|----------------|------------|----------------|--------|
| `null = 'x'` | `null` | `NULL = 'x'` → `NULL` | ✓ |
| `null and true` | `null` | `NULL AND TRUE` → `NULL` | ✓ |
| `null and false` | `false` | `NULL AND FALSE` → `FALSE` | ✓ |
| `null or true` | `true` | `NULL OR TRUE` → `TRUE` | ✓ |
| `if null then A else B` | `B` | `CASE WHEN NULL THEN A ELSE B END` → `B` | ✓ |

**Transformation rule**: Wrap boolean expressions in `COALESCE(expr, FALSE)` when the result goes to a `WHERE` clause, is an operand to `NOT`, or is an operand to `AND`/`OR` where NULL semantics could differ.

```python
def _wrap_for_boolean_context(self, expr: SQLExpression, usage: ExprUsage) -> SQLExpression:
    if usage in (ExprUsage.BOOLEAN, ExprUsage.EXISTS):
        return SQLFunctionCall(name="COALESCE", args=[expr, SQLLiteral(value=False)])
    return expr
```

---

## 6. Set Operation Semantics

### 6.1 Union

CQL `union` is **set union (distinct)** by default. The default translation is `UNION` (not `UNION ALL`).

`UNION ALL` may only be used when disjointness can be **proven at translation time**. Either of the following conditions is independently sufficient:
- Sources retrieve **different resource types** (structural disjointness — different resource types cannot share rows)
- The definition is consumed only in an **existence context** (`EXISTS`/`IS NOT NULL`) (semantic safety — duplicates are harmless when only patient presence matters)

Either condition alone is sufficient to permit `UNION ALL`. Both conditions together are not required. The default remains `UNION` (distinct) when neither condition is proven.

```python
def _translate_union(self, left: SQLExpression, right: SQLExpression) -> SQLUnion:
    left_type = self._infer_resource_type(left)
    right_type = self._infer_resource_type(right)

    # Only use UNION ALL when provably disjoint
    is_disjoint = (left_type is not None and right_type is not None
                   and left_type != right_type)

    return SQLUnion(
        queries=[left, right],
        distinct=not is_disjoint,  # True = UNION, False = UNION ALL
    )
```

### 6.2 Singleton From

CQL's `singleton from` must return null if the collection has >1 element. A naive `LIMIT 1` violates CQL semantics.

```python
def _translate_singleton_from(self, source: SQLExpression) -> SQLExpression:
    # Enforce: exactly 1 → return it; 0 or >1 → NULL
    return SQLCase(
        when_clauses=[(
            SQLBinaryOp(
                operator="=",
                left=SQLFunctionCall(name="COUNT", args=[SQLLiteral(value="*")]),
                right=SQLLiteral(value=1),
            ),
            SQLSelect(
                columns=[SQLIdentifier(name="resource")],
                from_clause=source,
                limit=1,
            ),
        )],
        else_clause=SQLNull(),
    )
```

---

## 7. Determinism

### 7.1 First()/Last() Ordering

SQL tables are unordered; `First()` without ORDER BY is non-deterministic.

**Solution**: Inject ORDER BY with tie-breaking.

```python
DEFAULT_SORT_COLUMNS = {
    "Condition": ["onset_date DESC NULLS FIRST", "resource_id ASC"],
    "Observation": ["effective_date DESC NULLS FIRST", "resource_id ASC"],
    "Encounter": ["period_start DESC NULLS FIRST", "resource_id ASC"],
    "Procedure": ["performed_date DESC NULLS FIRST", "resource_id ASC"],
    "MedicationRequest": ["authored_on DESC NULLS FIRST", "resource_id ASC"],
}
```

The `resource_id` column (or `json_extract_string(resource, '$.id')`) serves as a deterministic tie-breaker.

### 7.2 Temporal Precision Alignment

CQL temporal comparisons specify precision. Both operands must be truncated to the specified precision:

| CQL | SQL |
|-----|-----|
| `same day as` | `CAST(X AS DATE) = CAST(Y AS DATE)` |
| `same month as` | `DATE_TRUNC('month', X) = DATE_TRUNC('month', Y)` |
| `same year as` | `EXTRACT(YEAR FROM X) = EXTRACT(YEAR FROM Y)` |
| `before` (no precision) | `X < Y` (compare at finest available precision) |

---

## 8. Column Registry

### 8.1 Purpose

Track precomputed columns in retrieve CTEs to avoid redundant FHIRPath calls.

```python
@dataclass
class ColumnInfo:
    """Information about a precomputed column."""
    column_name: str
    fhirpath: str
    sql_type: str
    is_choice_type: bool = False

class ColumnRegistry:
    """Tracks precomputed columns available in each CTE."""

    def __init__(self):
        self._columns: Dict[str, Dict[str, ColumnInfo]] = {}

    def register_cte(self, cte_name: str, columns: Dict[str, ColumnInfo]) -> None:
        self._columns[cte_name] = columns

    def lookup(self, cte_name: str, fhirpath: str) -> Optional[str]:
        """Look up column name for a FHIRPath expression."""
        cte_cols = self._columns.get(cte_name, {})
        for col_info in cte_cols.values():
            if col_info.fhirpath == fhirpath:
                return col_info.column_name
        return None
```

### 8.2 Integration with Property Access

```python
def _translate_property(self, prop: Property, usage: ExprUsage) -> SQLExpression:
    source = prop.source
    path = prop.path

    # Check column registry first — avoid FHIRPath call
    if isinstance(source, Identifier):
        source_name = source.name
        col_name = self.context.column_registry.lookup(source_name, path)
        if col_name:
            alias = self._get_join_alias(source_name)
            return SQLQualifiedIdentifier(parts=[alias, col_name])

    # Fall back to FHIRPath UDF call
    return self._generate_fhirpath_property(source, path, usage)
```

---

## 9. Error Handling and Warnings

### 9.1 Translation Warnings

```python
@dataclass
class TranslationWarning:
    category: str        # PERFORMANCE, SEMANTICS, DEPRECATED
    message: str
    definition: Optional[str] = None
    suggestion: Optional[str] = None

class TranslationWarnings:
    def __init__(self):
        self.warnings: List[TranslationWarning] = []

    def add(self, category: str, message: str,
            definition: Optional[str] = None,
            suggestion: Optional[str] = None):
        self.warnings.append(TranslationWarning(
            category=category, message=message,
            definition=definition, suggestion=suggestion,
        ))
```

### 9.2 Early Rejection

Non-Patient contexts are rejected in Phase 1:

```python
if context_def.context_type != 'Patient':
    raise TranslationError(
        f"Only Patient context is supported, got: {context_def.context_type}"
    )
```

---

## 10. Unified SQLTranslationContext

Single source of truth for translation state.

```python
@dataclass
class SQLTranslationContext:
    """Context for CQL to SQL translation."""

    # Symbol management
    scopes: List[Scope] = field(default_factory=list)
    current_scope_level: int = 0

    # Definition metadata — drives CTE wrapping in Phase 2
    definition_meta: Dict[str, DefinitionMeta] = field(default_factory=dict)

    # Column registry — drives property optimization in Phase 3
    column_registry: ColumnRegistry = field(default_factory=ColumnRegistry)

    # Terminology
    valuesets: Dict[str, str] = field(default_factory=dict)
    codesystems: Dict[str, str] = field(default_factory=dict)
    codes: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Parameters
    parameters: Dict[str, ParameterInfo] = field(default_factory=dict)

    # Libraries
    includes: Dict[str, LibraryInfo] = field(default_factory=dict)

    # Current query context
    resource_alias: Optional[str] = None
    resource_type: Optional[str] = None

    # Query builder (scoped per definition — set temporarily during translation)
    query_builder: Optional[SQLQueryBuilder] = None

    # Warnings
    warnings: TranslationWarnings = field(default_factory=TranslationWarnings)

    def __post_init__(self):
        if not self.scopes:
            self.scopes.append(Scope(level=0))
```

---

## 11. CTE Organization

CTEs are organized structurally:

```
_patients
    ↓
_patient_demographics (if birth_date is accessed directly)
    ↓
RETRIEVE CTEs (resource-type CTEs with precomputed columns)
    ↓
EXTERNAL LIBRARY DEFINES
    ↓
MAIN LIBRARY DEFINES (in dependency order)
    ↓
FINAL OUTPUT (LEFT JOINs for population output)
```

### CTE Naming Rules

| CTE Type | Naming Pattern | Example |
|----------|----------------|---------|
| Base patients | `_patients` | `_patients` |
| Demographics | `_patient_demographics` | `_patient_demographics` — provides `birth_date`; age calculations use `AgeInYearsAt(patient_resource, date)` CQL UDF, not a precomputed column |
| Retrieve (no valueset) | `"ResourceType"` | `"Encounter"` |
| Retrieve (with valueset) | `"ResourceType: ValueSet Name"` | `"Condition: Essential Hypertension"` |
| External library define | `"Library.DefineName"` | `"Hospice.Has Hospice Services"` |
| Main library define | `"Define Name"` | `"Initial Population"` |

---

## 12. Testing Strategy

### 12.1 Result-Based Tests (Primary)

```python
class TestExistsCorrectness:
    def test_exists_no_fanout(self, test_db):
        """Patients must appear exactly once regardless of resource count."""
        cql = '''
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        '''
        result = evaluate_cql(cql, test_db)

        p3_rows = result[result['patient_id'] == 'P3']
        assert len(p3_rows) == 1
        assert p3_rows.iloc[0]['HasDiabetes'] == True

    def test_count_sees_all_rows(self, test_db):
        """Count must see all rows, not be affected by DISTINCT."""
        cql = '''
            define Diabetes: [Condition: "Diabetes"]
            define DiabetesCount: Count(Diabetes)
        '''
        result = evaluate_cql(cql, test_db)

        p3_count = result[result['patient_id'] == 'P3']['DiabetesCount'].iloc[0]
        assert p3_count == 3
```

### 12.2 Required Test Cases

| Test Case | Purpose |
|-----------|---------|
| `exists` on multi-row CTE | No fanout, DISTINCT used |
| `Count` on multi-row CTE | All rows counted |
| `First` determinism | Same result across runs |
| Multi-usage same CTE | Single JOIN, correct expression |
| Self-join | Two JOINs to same CTE |
| Union distinctness | `UNION` default, `UNION ALL` only when proven disjoint |
| `singleton from` with >1 | Returns NULL, not arbitrary row |
| NULL in boolean context | Correct COALESCE |
| Precision-aware date comparison | `same day as` truncates to DATE |
| PATIENT_MULTI_VALUE projection | `X.status` on RESOURCE_ROWS yields value rows |
| Non-Patient context | Rejected with clear error |
| No string manipulation | `to_sql()` called only in final assembly |

---

## 13. Validation Checklist

### Before Implementation Complete

- [ ] Pure AST pipeline — no string-based SQL inspection anywhere
- [ ] `DefinitionMeta.shape` drives all CTE wrapping decisions
- [ ] Three-phase translation (translate → build CTEs → resolve placeholders)
- [ ] Each expression translated exactly once (no re-translation)
- [ ] `RowShape` has three states: PATIENT_SCALAR, PATIENT_MULTI_VALUE, RESOURCE_ROWS
- [ ] `union` maps to `UNION` by default (not `UNION ALL`)
- [ ] `singleton from` enforces cardinality (not `LIMIT 1`)
- [ ] Fanout prevention generalized to any multi-row CTE join
- [ ] Single `SQLTranslationContext` class
- [ ] `patient_id` standardized across all CTEs
- [ ] Topological sort for definitions
- [ ] Fresh `SQLQueryBuilder` per definition
- [ ] Multi-usage CTE tracking (usages set)
- [ ] DISTINCT used only when all usages are EXISTS/BOOLEAN
- [ ] Self-join alias keying works
- [ ] Inter-resource correlation predicates
- [ ] `First()`/`Last()` with tie-breaking ORDER BY
- [ ] Temporal precision alignment
- [ ] NULL handling with COALESCE
- [ ] Non-Patient context rejected early
- [ ] Warnings for fallbacks
- [ ] Column registry integrated
- [ ] Phase 3 property optimization implemented
- [ ] Result-based tests pass
- [ ] No measure-specific hardcoding (CMS165, QICoreCommon, etc.)

---

## 14. Prohibited Anti-Patterns (Audit Registry)

This section catalogs architectural anti-patterns that violate the pure AST pipeline principle. These patterns were identified during Phase 3 architectural audits and **must not** be introduced into the codebase.

> **Reference:** See `plans/ARCHITECTURAL_AUDIT_INVENTORY_PHASE_3.md` for the complete inventory with file locations and line numbers.

### 14.1 Measure/Library/Profile-Specific Hardcoding

**Violation:** Logic explicitly tied to specific clinical measures, library names, or profile URLs that makes the transpiler non-generalizable.

| ❌ Never do this | ✅ Do this instead |
|------------------|-------------------|
| `if library_name == "QICoreCommon":` | Load library behavior from configuration |
| `lib_names = ["Status", "QICoreCommon", "FHIRHelpers"]` | Discover libraries dynamically from CQL includes |
| Hardcoded profile URLs in conditionals | Use `ProfileRegistry` to resolve profiles |

### 14.2 Unauthorized `.to_sql()` Calls

**Violation:** Calling `.to_sql()` mid-pipeline for control flow, state inspection, or template building. The only valid use is at the final rendering boundary.

| ❌ Never do this | ✅ Do this instead |
|------------------|-------------------|
| `resource_sql = resource_expr.to_sql()` | Pass `resource_expr` as SQLExpression AST node |
| `param_map[param_name] = arg.to_sql()` | Store SQLExpression nodes in param_map |
| `if "EXISTS" in expr.to_sql():` | Use `isinstance(expr, SQLExists)` or `ast_has_node_type()` |
| `result = template.replace("{x}", expr.to_sql())` | Build template substitution with AST nodes |

**Exception:** `to_sql()` is permitted in:
- Final CTE assembly (`translator.py` render methods)
- Debug/print statements (not production code)
- `SQLExpression.to_sql()` method implementations (these ARE the rendering boundary)

### 14.3 Regex on Rendered SQL

**Violation:** Using regex or string operations on rendered SQL strings instead of traversing the AST.

| ❌ Never do this | ✅ Do this instead |
|------------------|-------------------|
| `re.search(r"code = '(\d+-\d+)'", sql_string)` | Extract code from CQL/SQL AST nodes before rendering |
| `"SELECT" in sql.upper()` | Check `isinstance(expr, SQLSelect)` |
| Parsing temporal operator strings with regex | Decompose operators in CQL parser into structured fields |

**Exception:** Regex for identifier transformation (e.g., `camel_to_snake`) is acceptable as it operates on names, not SQL text.

### 14.4 Hardcoded Dictionaries

**Violation:** FHIR schema knowledge, profile URLs, terminology constants, or function dispatch tables hardcoded in Python dictionaries instead of using dynamic registries.

| ❌ Never do this | ✅ Do this instead |
|------------------|-------------------|
| `_TERMINOLOGY_PROPERTY_DEFAULTS = {"Condition": "code", ...}` | Query `FHIRSchemaRegistry` for element types |
| `FHIR_TYPE_TO_UDF = {"dateTime": "fhirpath_date", ...}` | Load from configuration file |
| `bp_codes = {"8480-6": "systolic_value"}` | Load from terminology/column mapping config |
| `if name.lower() in ("ageinyearsat", ...): return _translate_age_at(...)` | Register in `FunctionTranslationRegistry` |
| Hardcoded extension URLs as Python string literals | Add to `qicore-profiles.json` `property_extensions` section; look up via `ProfileRegistry.get_extension_info()` |

**Acceptable pattern:** Configuration loaded from JSON files at startup (not inline Python dicts). Function optimizations registered in `FunctionTranslationRegistry` at construction time.

### 14.5 String-based SQL Construction

**Violation:** Building SQL logic using Python f-strings instead of AST node composition.

| ❌ Never do this | ✅ Do this instead |
|------------------|-------------------|
| `f"SELECT * FROM {table_name}"` | `SQLSelect(columns=[...], from_clause=SQLIdentifier(table_name))` |
| `f"EXISTS {subquery.to_sql()}"` | `SQLExists(subquery=subquery_ast)` |
| `f"meta.profile.contains('{url}')"` | Use `FHIRPathBuilder` to construct FHIRPath expressions |

**Exceptions:**
- Within `to_sql()` implementations, f-strings are used for final string assembly (this IS the rendering boundary).
- **Registered fluent function string templates** (see tech spec §8.2 Strategy 2): A narrow set of well-known fluent functions (`latest()`, `getId()`, `toInterval()`, etc.) may use string templates with a single `{resource}` substitution point. This is a transitional pattern — the template body is a fixed SQL expression, not constructed logic. New fluent functions must use AST-level inlining (Strategy 1). Existing templates should be migrated to AST nodes incrementally.

### 14.6 `list_filter` Lambda Generation

**Violation:** Generating `list_filter(..., lambda)` strings instead of standard SQL WHERE clauses or proper AST construction.

| ❌ Never do this | ✅ Do this instead |
|------------------|-------------------|
| `"list_filter({resource}, r -> condition)"` as string | `SQLFunctionCall("list_filter", [resource, SQLLambda(...)])` |
| String detection: `"list_filter" in sql_string` | AST check: `isinstance(expr, SQLFunctionCall) and expr.name == "list_filter"` |

**Context:** `list_filter` is sometimes necessary for DuckDB list operations, but must be constructed as AST nodes, not strings.

### 14.7 Improper `SQLRaw` Usage

**Violation:** Using `SQLRaw` to inject structured SQL constructs that should be proper AST nodes.

| ❌ Never do this | ✅ Do this instead |
|------------------|-------------------|
| `SQLRaw("SELECT p.patient_id FROM _patients p")` | Build `SQLSelect` with proper AST nodes |
| `SQLRaw(raw_sql=predicate)` for lambda body | Build predicate as `SQLBinaryOp` or similar |
| `SQLRaw("EXISTS (SELECT ...)")` | `SQLExists(subquery=...)` |

**Acceptable uses of `SQLRaw`:**
- Quoted identifiers extracted from user input (with sanitization)
- Database-specific syntax that has no AST representation
- Migration/transitional code (with TODO to replace)

### 14.8 Dead Code

**Violation:** Unused functions, imports, or legacy fallback code that is no longer called by the main execution pipeline.

| Pattern | Action |
|---------|--------|
| Unused imports | Remove them |
| Fallback dictionaries "just in case" | Delete if registry replaces them |
| Commented-out code blocks | Delete (git preserves history) |
| `# Hardcoded maps removed - see Task X` | Clean up after migration complete |

### 14.9 Pending TODOs

**Violation:** Unresolved `TODO`, `FIXME`, `HACK`, or `XXX` comments that represent incomplete migrations.

| Action | When |
|--------|------|
| Convert to tracked issue | If complex, requires planning |
| Implement immediately | If small, self-contained |
| Delete | If obsolete or already addressed |

---

## 15. Validation Checklist (Automated Enforcement)

The following checks should be enforced by CI/CD:

```bash
# Prohibited patterns - should return 0 matches
grep -r "\.to_sql()" --include="*.py" cql-py/src/ | grep -v "def to_sql" | grep -v "# permitted"
grep -r "re\\.search\\|re\\.match\\|re\\.sub" --include="*.py" cql-py/src/cql_py/translator/ | grep -v "camel_to_snake"
grep -r "CMS165\\|CMS124\\|QICoreCommon" --include="*.py" cql-py/src/cql_py/translator/ | grep -v "# example" | grep -v "docstring"
grep -r "TODO\\|FIXME\\|HACK\\|XXX" --include="*.py" cql-py/src/cql_py/translator/
```
