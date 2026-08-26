# Implementation Plan: Context-Aware CQL-to-SQL Translation

**Version**: 1.0  
**Date**: 2025-02-24  
**Status**: Planning  
**Related**: [DESIGN-CONTEXT-AWARE-TRANSLATION.md](./DESIGN-CONTEXT-AWARE-TRANSLATION.md)

---

## Executive Summary

This plan addresses the gaps identified in the context-aware translation design. The core insight is that `ExprUsage` (how a result is used) is necessary but not sufficient—we also need **row-shape tracking** (what a definition produces) to generate correct SQL.

**Timeline**: 4-6 weeks (phased approach)  
**Risk Level**: Medium-High (correctness-critical changes)

---

## Phase 0: Foundation Cleanup (Week 1) - BLOCKING

> **Critical**: Phase 0 tasks are **blockers** for all subsequent work. Do not proceed to Phase 1 until Phase 0 is complete.

### 0.1 Consolidate SQLTranslationContext Classes

**Problem**: Two separate `SQLTranslationContext` classes cause confusion and bugs. This is a **silent footgun** - if `query_builder` lives on the wrong instance, JOIN tracking does nothing.

**Tasks**:
- [ ] Audit all imports of `SQLTranslationContext` across codebase
- [ ] Create mapping of which fields exist in each version
- [ ] Identify which class is actually instantiated and used
- [ ] Migrate `translator.py` to use `context.py` version
- [ ] Remove duplicate class from `translator.py`
- [ ] Update all call sites to use unified API
- [ ] Verify `query_builder` is on the correct instance

**Files to modify**:
| File | Change |
|------|--------|
| `translator.py:135-300` | Remove `SQLTranslationContext` class |
| `translator.py` | Import from `context.py` |
| `expressions.py` | Verify correct import |
| `queries.py` | Verify correct import |
| `fluent_functions.py` | Verify correct import |

**Acceptance Criteria**:
- [ ] Single `SQLTranslationContext` class in `context.py`
- [ ] All existing tests pass
- [ ] No import errors
- [ ] `self._context.query_builder` references same instance everywhere

**Estimated Effort**: 4-8 hours

### 0.2 Standardize patient_id Column

**Problem**: Inconsistent use of `patient_ref` vs `patient_id` causes silent JOIN failures.

**Tasks**:
- [ ] Audit all SQL generation for patient column references
- [ ] Update `SQLRetrieveCTE` to output `patient_id` (alias from `patient_ref`)
- [ ] Update `generate_joins()` to use `patient_id`
- [ ] Update all CTE building functions for consistency

**Files to modify**:
| File | Line | Change |
|------|------|--------|
| `types.py` | `SQLRetrieveCTE.to_sql()` | Output `patient_ref AS patient_id` |
| `queries.py` | 139 | Change `patient_ref` to `patient_id` |
| `translator.py` | Various | Ensure consistent column names |

**Acceptance Criteria**:
- [ ] All CTEs output `patient_id` column
- [ ] All JOINs use `patient_id` on both sides
- [ ] Existing measure queries still work

**Estimated Effort**: 2-4 hours

### 0.3 Add Topological Sort for Definitions

**Problem**: Forward references cause silent fallback to O(n²) correlated subqueries with no warning.

**Tasks**:
- [ ] Implement `_build_dependency_graph()` to walk AST and find definition references
- [ ] Implement `_topological_sort()` using standard algorithm (Kahn's or DFS)
- [ ] Add cycle detection with descriptive error message
- [ ] Integrate into `translate_library()` before definition translation

**New code in `translator.py`**:

```python
def _build_dependency_graph(self, definitions: List[Definition]) -> Dict[str, Set[str]]:
    """Build directed graph of definition dependencies."""
    graph = {d.name: set() for d in definitions}
    def_names = set(graph.keys())
    
    for defn in definitions:
        refs = self._find_definition_references(defn.expression, def_names)
        graph[defn.name] = refs
    
    return graph

def _topological_sort(self, definitions: List[Definition]) -> List[Definition]:
    """Sort definitions so dependencies come before dependents."""
    graph = self._build_dependency_graph(definitions)
    
    # Kahn's algorithm
    in_degree = {name: 0 for name in graph}
    for deps in graph.values():
        for dep in deps:
            in_degree[dep] += 1
    
    queue = [name for name, degree in in_degree.items() if degree == 0]
    result = []
    
    while queue:
        name = queue.pop(0)
        result.append(name)
        for dependent, deps in graph.items():
            if name in deps:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
    
    if len(result) != len(definitions):
        # Cycle detected
        remaining = set(graph.keys()) - set(result)
        raise TranslationError(f"Cyclic dependency detected among: {remaining}")
    
    # Return definitions in sorted order
    name_to_def = {d.name: d for d in definitions}
    return [name_to_def[name] for name in result]
```

**Acceptance Criteria**:
- [ ] Definitions translated in dependency order
- [ ] Cyclic dependencies raise `TranslationError`
- [ ] Forward references no longer cause silent fallback

**Estimated Effort**: 4-6 hours

---

## Phase 1: Row-Shape Tracking (Week 1-2)

### 1.1 Add RowShape Enum and DefinitionMeta

**Purpose**: Track what each definition produces to enable safe JOIN decisions.

**New types in `context.py`**:

```python
class RowShape(Enum):
    """What a definition produces in terms of rows per patient."""
    PATIENT_SCALAR = auto()   # 1 row/patient: boolean, number, string
    PATIENT_LIST = auto()     # 1 row/patient: list-valued column
    RESOURCE_ROWS = auto()    # N rows/patient: one per resource
    UNKNOWN = auto()          # Forward reference or complex expression

@dataclass
class DefinitionMeta:
    """Metadata about a translated definition."""
    name: str
    shape: RowShape
    has_resource: bool = False
    value_column: str = "value"  # Column containing the result
    patient_key_col: str = "patient_id"
```

**Tasks**:
- [ ] Add `RowShape` enum to `context.py`
- [ ] Add `DefinitionMeta` dataclass to `context.py`
- [ ] Add `definition_meta: Dict[str, DefinitionMeta]` to `SQLTranslationContext`
- [ ] Export new types in `__init__.py`

**Files to modify**:
| File | Change |
|------|--------|
| `context.py` | Add `RowShape`, `DefinitionMeta` |
| `context.py:104` | Add `definition_meta` field to context |
| `__init__.py` | Export new types |

**Estimated Effort**: 2-3 hours

### 1.2 Implement Shape Inference

**Purpose**: Determine the row-shape of each translated expression.

**New function in `translator.py`**:

```python
def _infer_row_shape(self, expr: SQLExpression, ast_node: Optional[Any] = None) -> RowShape:
    """
    Infer the row shape of a translated expression.
    
    Rules:
    - Retrieve without aggregation → RESOURCE_ROWS
    - exists/Count/Sum/etc. → PATIENT_SCALAR
    - First/Last/singleton from → PATIENT_SCALAR (with resource)
    - Union of RESOURCE_ROWS → RESOURCE_ROWS
    - Property access on RESOURCE_ROWS → RESOURCE_ROWS (projection)
    - list_agg/collect → PATIENT_LIST
    """
```

**Tasks**:
- [ ] Implement `_infer_row_shape()` in `translator.py`
- [ ] Handle common patterns: Retrieve, exists, First, aggregates
- [ ] Add shape to `DefinitionMeta` after translation
- [ ] Add tests for shape inference

**Inference rules**:
| CQL Pattern | AST Node | Shape |
|-------------|----------|-------|
| `[Resource]` | Retrieve | RESOURCE_ROWS |
| `exists [Resource]` | ExistsExpression | PATIENT_SCALAR |
| `First([Resource])` | FirstExpression | PATIENT_SCALAR |
| `Count([Resource])` | FunctionRef("Count") | PATIENT_SCALAR |
| `Definition.property` | Property(source=RESOURCE_ROWS) | RESOURCE_ROWS |
| `Definition.property` | Property(source=PATIENT_SCALAR) | PATIENT_SCALAR |

**Estimated Effort**: 6-8 hours

### 1.3 Populate DefinitionMeta During Translation

**Tasks**:
- [ ] After each definition is translated, record its metadata
- [ ] Store in `context.definition_meta[name]`
- [ ] Handle forward references (use UNKNOWN shape)

**Modification to `translate_definition()`**:
```python
def translate_definition(self, defn: Definition) -> Tuple[str, SQLExpression]:
    name = defn.name
    expr = self._translate_expression(defn.expression)
    
    # Record metadata
    shape = self._infer_row_shape(expr, defn.expression)
    has_resource = self._expr_has_resource_column(expr)
    
    self._context.definition_meta[name] = DefinitionMeta(
        name=name,
        shape=shape,
        has_resource=has_resource,
    )
    
    return name, expr
```

**Estimated Effort**: 3-4 hours

---

## Phase 2: Scoped Query Builder (Week 2)

### 2.1 Fresh Query Builder Per Definition

**Problem**: Global query builder causes JOINs to leak between CTEs.

**Tasks**:
- [ ] Remove global `query_builder` from context
- [ ] Create fresh builder at start of each definition translation
- [ ] Pass builder through expression translator
- [ ] Extract JOINs immediately after translation, before building CTE

**New pattern**:
```python
def _translate_definition_to_cte(self, name: str, defn: Definition) -> CTEDefinition:
    # Fresh builder for this definition's scope
    query_builder = SQLQueryBuilder()
    
    # Store temporarily
    old_builder = self._context.query_builder
    self._context.query_builder = query_builder
    
    try:
        # Translate - may register JOINs
        expr = self._translate_expression(defn.expression)
        
        # Build CTE with registered JOINs
        joins = query_builder.generate_joins()
        cte = self._build_cte(name, expr, joins)
        
        return cte
    finally:
        self._context.query_builder = old_builder
```

**Files to modify**:
| File | Change |
|------|--------|
| `translator.py` | Implement scoped builder pattern |
| `translator.py:1133` | Remove premature `clear()` call |

**Estimated Effort**: 4-6 hours

### 2.2 Update CTEReference for Multi-Usage Tracking

**Problem**: Same CTE may be referenced multiple times with different usages (e.g., `exists Diabetes and Diabetes.status = 'confirmed'`). Current implementation uses `cte_name` as dict key, so second usage overwrites first.

**Tasks**:
- [ ] Change `usage: ExprUsage` to `usages: Set[ExprUsage]`
- [ ] Add `can_use_distinct` property
- [ ] Update `track_cte_reference()` to add to existing usages
- [ ] Update `generate_joins()` to check `can_use_distinct`

**Updated `CTEReference`**:
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
        # Add to existing usages - don't overwrite!
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

**Acceptance Criteria**:
- [ ] `exists A and A.status` generates single JOIN (not two)
- [ ] JOIN uses full CTE (no DISTINCT) when any usage needs resource
- [ ] DISTINCT only applied when all usages are EXISTS/BOOLEAN

**Estimated Effort**: 3-4 hours

---

## Phase 3: Shape-Aware JOIN Conversion (Week 2-3)

### 3.1 Update _translate_identifier() for Shape Checking

**Purpose**: Use definition metadata to decide JOIN strategy.

**Tasks**:
- [ ] Look up `DefinitionMeta` when translating identifier
- [ ] For RESOURCE_ROWS shape with EXISTS/BOOLEAN usage: use DISTINCT JOIN
- [ ] For RESOURCE_ROWS shape with SCALAR usage: warn or error
- [ ] For PATIENT_SCALAR/BOOLEAN: JOIN directly

**Modified logic**:
```python
def _translate_identifier(self, ident: Identifier, usage: ExprUsage) -> SQLExpression:
    name = ident.name
    
    # Check if this is a definition reference
    if name in self.context.definition_meta or name in self.context.definitions:
        meta = self.context.definition_meta.get(name)
        
        if meta and meta.shape == RowShape.RESOURCE_ROWS:
            return self._handle_resource_rows_reference(name, meta, usage)
        else:
            return self._handle_patient_level_reference(name, meta, usage)
    
    # ... rest of existing logic ...
```

**Estimated Effort**: 6-8 hours

### 3.2 Add Strict Mode Option

**Tasks**:
- [ ] Add `strict_mode: bool` parameter to translator
- [ ] In strict mode, raise `TranslationError` for unsafe patterns
- [ ] In permissive mode, log warning and use fallback
- [ ] Document strict vs permissive behavior

**Strict mode checks**:
| Pattern | Strict Mode | Permissive Mode |
|---------|-------------|-----------------|
| RESOURCE_ROWS as SCALAR | Error | Warning + LIMIT 1 |
| singleton from multi-row | Error | Warning + pick first |
| Forward reference JOIN | Error | Correlated subquery |

**Estimated Effort**: 3-4 hours

---

## Phase 4: Column Registry (Week 3)

### 4.1 Implement ColumnRegistry Class

**Purpose**: Track precomputed columns to avoid redundant FHIRPath calls.

**New class in `context.py`**:
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
        """Register columns for a CTE."""
        self._columns[cte_name] = columns
    
    def lookup(self, cte_name: str, fhirpath: str) -> Optional[str]:
        """Look up column name for a FHIRPath expression."""
        cte_cols = self._columns.get(cte_name, {})
        for col_info in cte_cols.values():
            if col_info.fhirpath == fhirpath:
                return col_info.column_name
        return None
```

**Tasks**:
- [ ] Implement `ColumnRegistry` class
- [ ] Add to `SQLTranslationContext`
- [ ] Register columns when building `SQLRetrieveCTE`

**Estimated Effort**: 3-4 hours

### 4.2 Integrate with Property Access

**Tasks**:
- [ ] In `_translate_property()`, check column registry first
- [ ] If column exists, use direct column reference
- [ ] Otherwise, generate FHIRPath call as before

**Modified `_translate_property()`**:
```python
def _translate_property(self, prop: Property, usage: ExprUsage) -> SQLExpression:
    source = prop.source
    path = prop.path
    
    # If source is a CTE reference, check column registry
    if isinstance(source, Identifier):
        source_name = source.name
        col_name = self.context.column_registry.lookup(source_name, path)
        if col_name:
            # Use precomputed column
            alias = self._get_join_alias(source_name)
            return SQLQualifiedIdentifier(parts=[alias, col_name])
    
    # Fall back to FHIRPath call
    return self._generate_fhirpath_property(source, path, usage)
```

**Estimated Effort**: 4-6 hours

---

## Phase 5: Fluent Function Improvements (Week 3-4)

### 5.1 Template Resource Type Declarations

**Tasks**:
- [ ] Add `resource_expects: Literal["json", "array", "table"]` to function definitions
- [ ] Update `_substitute_template()` to check expected type
- [ ] Generate appropriate wrapper/conversion when types don't match

**Estimated Effort**: 4-6 hours

### 5.2 Integration with JOINed CTEs

**Tasks**:
- [ ] When resource is a JOIN alias, use qualified reference
- [ ] Check column registry for precomputed columns
- [ ] Handle array vs JSON context correctly

**Estimated Effort**: 4-6 hours

---

## Phase 6: Testing & Validation (Week 4-5)

> **Important**: Testing strategy emphasizes **result-based tests** over string-matching. String tests are fragile and don't validate correctness.

### 6.1 Test Fixtures with Boundary Cases

**Required fixture data** (create in `tests/fixtures/`):

| Patient | Conditions | Observations | Expected for `exists` | Expected for `Count() >= 2` |
|---------|------------|--------------|----------------------|----------------------------|
| P1 | 0 | 0 | false | false |
| P2 | 1 | 2 | true | false |
| P3 | 3 | 5 | true | true |

**Purpose**: Test boundary cases that expose fanout bugs:
- P1: No matches (tests NULL handling)
- P2: Single match (no fanout possible)
- P3: Multiple matches (fanout will cause wrong results)

**Estimated Effort**: 2-3 hours

### 6.2 Result-Based Integration Tests (PRIMARY)

**New test file**: `tests/integration/test_correctness.py`

```python
import pytest
import pandas as pd

class TestExistsCorrectness:
    """Primary tests: validate RESULTS, not SQL structure."""
    
    def test_exists_no_fanout(self, test_db):
        """Patients must appear exactly once regardless of resource count."""
        cql = '''
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        '''
        result = evaluate_cql(cql, test_db)
        
        # P3 has 3 diabetes conditions - must appear exactly once
        p3_rows = result[result['patient_id'] == 'P3']
        assert len(p3_rows) == 1, f"P3 appeared {len(p3_rows)} times (expected 1)"
        assert p3_rows.iloc[0]['HasDiabetes'] == True
        
        # P1 has 0 conditions - must appear once with false
        p1_rows = result[result['patient_id'] == 'P1']
        assert len(p1_rows) == 1
        assert p1_rows.iloc[0]['HasDiabetes'] == False

    def test_count_sees_all_rows(self, test_db):
        """Count must see all rows, not be affected by DISTINCT optimization."""
        cql = '''
            define Diabetes: [Condition: "Diabetes"]
            define DiabetesCount: Count(Diabetes)
        '''
        result = evaluate_cql(cql, test_db)
        
        # P3 has 3 diabetes conditions
        p3_count = result[result['patient_id'] == 'P3']['DiabetesCount'].iloc[0]
        assert p3_count == 3, f"Count was {p3_count} (expected 3)"

    def test_multi_usage_same_cte(self, test_db):
        """Same CTE used in EXISTS and SCALAR context."""
        cql = '''
            define Diabetes: [Condition: "Diabetes"]
            define HasConfirmedDiabetes: exists Diabetes and First(Diabetes.status) = 'confirmed'
        '''
        result = evaluate_cql(cql, test_db)
        
        # Each patient appears exactly once
        assert len(result) == len(result['patient_id'].unique())

class TestPropertyAccessCorrectness:
    """Property access over collections returns correct cardinality."""
    
    def test_property_projection(self, test_db):
        """Property access on RESOURCE_ROWS produces RESOURCE_ROWS."""
        cql = '''
            define Diabetes: [Condition: "Diabetes"]
            define Statuses: Diabetes.status
        '''
        result = evaluate_cql(cql, test_db)
        
        # P3 has 3 conditions, should have 3 status rows (or 1 row with list)
        p3_rows = result[result['patient_id'] == 'P3']
        # Depends on decision: projection vs aggregation
        # If projection: len(p3_rows) == 3
        # If aggregation: len(p3_rows) == 1 and len(p3_rows['Statuses'].iloc[0]) == 3
```

**Estimated Effort**: 6-8 hours

### 6.3 Structure Tests (SUPPLEMENTARY)

**New test file**: `tests/unit/test_sql_structure.py`

```python
class TestSQLStructure:
    """Supplementary tests: verify SQL structure after result tests pass."""
    
    def test_join_generated_for_exists(self):
        """Verify JOIN is generated (secondary to result test)."""
        cql = '''
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        '''
        sql = translate_cql(cql)
        
        # Check structure (fragile - only after results verified)
        assert "LEFT JOIN" in sql
        
    def test_no_correlated_subquery(self):
        """Verify no correlated subquery in SELECT list."""
        cql = '''
            define Diabetes: [Condition: "Diabetes"]
            define HasDiabetes: exists Diabetes
        '''
        sql = translate_cql(cql)
        
        # Should not have correlated subquery pattern
        # This is heuristic - not foolproof
        has_diabetes_cte = extract_cte(sql, "HasDiabetes")
        assert "WHERE d.patient_id = p.patient_id" not in has_diabetes_cte
```

**Estimated Effort**: 3-4 hours

### 6.4 Unit Tests for Row Shape Inference

**New test file**: `tests/unit/test_row_shape.py`

```python
class TestRowShapeInference:
    def test_retrieve_is_resource_rows(self):
        """[Condition] should have RESOURCE_ROWS shape."""
        ast = parse_cql('define X: [Condition]')
        shape = infer_shape(ast.definitions[0].expression)
        assert shape == RowShape.RESOURCE_ROWS
        
    def test_exists_is_patient_scalar(self):
        """exists [Condition] should have PATIENT_SCALAR shape."""
        ast = parse_cql('define X: exists [Condition]')
        shape = infer_shape(ast.definitions[0].expression)
        assert shape == RowShape.PATIENT_SCALAR
        
    def test_property_propagates_shape(self):
        """Property access propagates source shape."""
        # This test requires context with Diabetes as RESOURCE_ROWS
        ast = parse_cql('''
            define Diabetes: [Condition: "Diabetes"]
            define Status: Diabetes.status
        ''')
        # Status should be RESOURCE_ROWS because Diabetes is RESOURCE_ROWS
```

**Estimated Effort**: 4-6 hours

### 6.5 Golden Tests for CMS Measures

**Tasks**:
- [ ] Create reference results for CMS165 (from known-good implementation)
- [ ] Run CMS165 with new translator
- [ ] Compare results row-by-row
- [ ] Fix any discrepancies
- [ ] Add as regression test with `pytest.mark.golden`

**Test pattern**:
```python
@pytest.mark.golden
def test_cms165_matches_reference(test_db, golden_results):
    """CMS165 produces identical results to reference implementation."""
    result = evaluate_cms165(test_db)
    
    pd.testing.assert_frame_equal(
        result.sort_values('patient_id').reset_index(drop=True),
        golden_results.sort_values('patient_id').reset_index(drop=True),
        check_dtype=False,  # Allow int vs float differences
    )
```

**Estimated Effort**: 8-12 hours

---

## Phase 7: Advanced JOIN Safety (Week 5-6)

> **Note**: These phases address critical gaps identified in follow-up review (Appendix G of design doc).

### 7.1 Cartesian Fanout Detection and Mitigation

**Problem**: Multiple RESOURCE_ROWS JOINs create Cartesian products (G.1).

**Tasks**:
- [ ] Add `shape: RowShape` field to `CTEReference`
- [ ] Implement `validate_joins()` to detect multiple RESOURCE_ROWS
- [ ] Add `_use_aggregation_strategy` flag
- [ ] Implement pre-aggregation pattern for multi-RESOURCE_ROWS

**New validation in `SQLQueryBuilder`**:
```python
def validate_joins(self) -> List[str]:
    """Check for Cartesian fanout risk. Returns list of warnings."""
    warnings = []
    resource_row_refs = [
        ref for ref in self.cte_references.values()
        if ref.shape == RowShape.RESOURCE_ROWS and not ref.can_use_distinct
    ]
    if len(resource_row_refs) > 1:
        names = [r.cte_name for r in resource_row_refs]
        warnings.append(
            f"Multiple RESOURCE_ROWS CTEs in same scope: {names}. "
            f"Using aggregation strategy to avoid Cartesian fanout."
        )
        self._use_aggregation_strategy = True
    return warnings
```

**Acceptance Criteria**:
- [ ] `Diabetes.status and Hypertension.status` doesn't create 6 rows for patient with 3+2 conditions
- [ ] Warning logged when aggregation strategy used
- [ ] Strict mode raises error

**Estimated Effort**: 6-8 hours

### 7.2 Self-Join Alias Keying

**Problem**: Same CTE referenced twice with different aliases overwrites (G.4).

**Tasks**:
- [ ] Add `semantic_alias: str` field to `CTEReference`
- [ ] Change `cte_references` key from `cte_name` to `(cte_name, semantic_alias)`
- [ ] Update `track_cte_reference()` signature
- [ ] Update all call sites to pass semantic alias

**Updated `CTEReference`**:
```python
@dataclass
class CTEReference:
    cte_name: str
    semantic_alias: str  # E1, E2, etc.
    alias: str           # j1, j2, etc.
    usages: Set[ExprUsage] = field(default_factory=set)
    shape: RowShape = RowShape.UNKNOWN
```

**Acceptance Criteria**:
- [ ] `from Encounters E1, Encounters E2 where E2.start = E1.end` produces two JOINs
- [ ] Each alias gets distinct SQL alias (j1, j2)

**Estimated Effort**: 3-4 hours

### 7.3 Inter-Resource Correlation Predicates

**Problem**: `with ... such that` needs non-patient correlation (G.2).

**Tasks**:
- [ ] Add `additional_predicates: List[SQLExpression]` to `CTEReference`
- [ ] Add `correlates_to_alias: Optional[str]` to `CTEReference`
- [ ] Update `_translate_with_clause()` to capture `such that` predicates
- [ ] Update `generate_joins()` to include additional predicates

**Acceptance Criteria**:
- [ ] `Diabetes D with A1C O such that O.effective > D.onset` produces correct JOIN
- [ ] JOIN condition includes `j2.effective > j1.onset`

**Estimated Effort**: 6-8 hours

### 7.4 Conditional RESOURCE_ROWS Handling

**Problem**: `if/else` with RESOURCE_ROWS branches causes eager evaluation (G.3).

**Tasks**:
- [ ] Detect RESOURCE_ROWS in conditional branches during translation
- [ ] Fall back to correlated subquery pattern for conditional RESOURCE_ROWS
- [ ] Add test for conditional fanout case

**Acceptance Criteria**:
- [ ] `if HasRisk then SevereConditions else MildConditions` doesn't JOIN both
- [ ] Only the selected branch is evaluated

**Estimated Effort**: 4-6 hours

---

## Phase 8: Determinism and Null Handling (Week 6)

### 8.1 First()/Last() Ordering

**Problem**: `First()` without ORDER BY is non-deterministic (G.5).

**Tasks**:
- [ ] Add `DEFAULT_SORT_COLUMNS` config per resource type
- [ ] Update `_translate_first_expression()` to inject ORDER BY
- [ ] Consider ROW_NUMBER() window function pattern

**Acceptance Criteria**:
- [ ] `First([Condition])` returns same result across runs
- [ ] Uses appropriate date column for ordering

**Estimated Effort**: 3-4 hours

### 8.2 3-Valued Logic Null Handling

**Problem**: NULL propagation differs between CQL and SQL (G.6).

**Tasks**:
- [ ] Research CQL spec for null propagation rules
- [ ] Add `_wrap_for_boolean_context()` helper
- [ ] Apply COALESCE where appropriate
- [ ] Add comprehensive null handling tests

**Acceptance Criteria**:
- [ ] `not (Diabetes.status = 'confirmed')` returns expected result for patients without diabetes
- [ ] Boolean expressions don't unexpectedly return NULL

**Estimated Effort**: 4-6 hours

---

## Phase 9: Documentation & Cleanup (Week 6-7)

### 9.1 Update Design Document

**Tasks**:
- [ ] Mark completed items in validation checklist
- [ ] Document final architecture
- [ ] Add examples of generated SQL

### 9.2 API Documentation

**Tasks**:
- [ ] Document `RowShape` enum usage
- [ ] Document `DefinitionMeta` structure
- [ ] Document strict vs permissive mode
- [ ] Document hybrid JOIN/subquery strategy
- [ ] Update README with new features

### 9.3 Migration Guide

**Tasks**:
- [ ] Document breaking changes (if any)
- [ ] Provide upgrade path for existing code
- [ ] Note deprecated patterns

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Row shape inference incorrect | High | Medium | Extensive testing, fallback to UNKNOWN |
| Breaking existing measures | High | Medium | Run full test suite before merge |
| Performance regression | Medium | Low | Benchmark before/after |
| Forward reference handling | Medium | Medium | Use UNKNOWN shape, correlated subquery fallback |
| Complex union handling | Medium | Medium | Test union-heavy measures |
| **Cartesian fanout** | **Critical** | **Medium** | Aggregation strategy, strict mode |
| **Self-join alias collision** | **High** | **Low** | Semantic alias keying |
| **Inter-resource correlation** | **High** | **Medium** | Additional predicates in CTEReference |
| **Conditional fanout** | **High** | **Low** | Subquery fallback for conditional RESOURCE_ROWS |
| **Non-deterministic First()** | **Medium** | **High** | Default ORDER BY per resource type |
| **3VL null bugs** | **Medium** | **Medium** | COALESCE wrapping, CQL spec validation |

---

## Success Criteria

### Correctness
- [ ] No fanout: patients appear exactly once in boolean/scalar results
- [ ] No Cartesian fanout from multiple RESOURCE_ROWS JOINs
- [ ] Correct NULL handling in boolean logic
- [ ] CMS165 produces identical results to reference
- [ ] Self-joins work correctly
- [ ] Inter-resource correlations work correctly

### Performance
- [ ] No O(n²) correlated subqueries for common patterns
- [ ] Precomputed columns used when available
- [ ] JOINs preferred over subqueries (when safe)
- [ ] Aggregation strategy used when JOINs would cause fanout

### Maintainability
- [ ] Single `SQLTranslationContext` class
- [ ] Clear separation of concerns
- [ ] Comprehensive test coverage (>80%)
- [ ] Hybrid JOIN/subquery strategy documented

---

## Appendix: File Change Summary

| File | Phase | Changes |
|------|-------|---------|
| `context.py` | 0, 1, 4 | Consolidate classes, add RowShape, DefinitionMeta, ColumnRegistry |
| `translator.py` | 0, 1, 2, 3, 7, 8 | Remove duplicate class, scoped builder, shape inference, fanout detection |
| `queries.py` | 0, 2, 7 | Fix patient_id, DISTINCT join support, semantic aliases, additional predicates |
| `expressions.py` | 3, 8 | Shape-aware identifier translation, null handling |
| `fluent_functions.py` | 5 | Resource type declarations, JOIN integration |
| `types.py` | 0, 8 | patient_id standardization, DEFAULT_SORT_COLUMNS |

---

## Appendix: Test Plan Summary

| Test Category | Count | Priority |
|---------------|-------|----------|
| Row shape inference | 10-15 | High |
| JOIN correctness | 8-10 | High |
| **Cartesian fanout prevention** | 5-8 | **Critical** |
| **Self-join handling** | 3-5 | **High** |
| **Inter-resource correlation** | 3-5 | **High** |
| **Conditional RESOURCE_ROWS** | 3-5 | **High** |
| **First()/Last() determinism** | 3-5 | **Medium** |
| **NULL/3VL semantics** | 5-8 | **Medium** |
| Column registry | 5-8 | Medium |
| Fluent functions | 5-8 | Medium |
| CMS measure golden tests | 3-5 | High |
| Strict mode | 5-8 | Low |

---

## Appendix: Hybrid Strategy Decision Tree

```
For each CTE reference in expression:
    │
    ├─ Is source shape PATIENT_SCALAR/PATIENT_BOOLEAN?
    │   └─ YES → Use JOIN (safe, no fanout possible)
    │
    ├─ Is source shape RESOURCE_ROWS?
    │   │
    │   ├─ Is usage EXISTS/BOOLEAN only?
    │   │   └─ YES → Use DISTINCT JOIN (no fanout)
    │   │
    │   ├─ Are there OTHER RESOURCE_ROWS refs in same scope?
    │   │   └─ YES → Use AGGREGATION strategy (list_agg)
    │   │
    │   ├─ Is this inside a conditional branch?
    │   │   └─ YES → Use CORRELATED SUBQUERY
    │   │
    │   ├─ Is this a self-join (same CTE, different alias)?
    │   │   └─ YES → Use multiple JOINs with semantic aliases
    │   │
    │   └─ Otherwise → Use single JOIN (fast path)
    │
    └─ Is source shape UNKNOWN?
        └─ Use CORRELATED SUBQUERY (safe fallback)
```

---

## Appendix: 30/60/90 Day Timeline

### Days 1-30: Foundation (BLOCKING)

| Week | Task | Deliverable |
|------|------|-------------|
| 1 | Unify `SQLTranslationContext` | Single class in `context.py` |
| 1 | Standardize `patient_id` | All CTEs output `patient_id` |
| 2 | Topological sort | Definitions ordered by dependency |
| 2 | Fresh builder per definition | Scoped `SQLQueryBuilder` |
| 3 | Add fallback warnings | `TranslationWarnings` class |
| 3 | Basic result tests | 0/1/3 resource boundary tests |
| 4 | Integration testing | All existing tests pass |

**Exit Criteria**:
- [ ] Single context class
- [ ] No silent fallbacks (warnings emitted)
- [ ] Topological sort prevents forward reference issues
- [ ] All existing CMS measure tests pass

### Days 31-60: Core Safety

| Week | Task | Deliverable |
|------|------|-------------|
| 5 | `RowShape` + `DefinitionMeta` | Shape inference for all expression types |
| 5 | CQL type propagation | `cql_type` and `cardinality` in meta |
| 6 | Multi-usage CTE tracking | `usages: Set[ExprUsage]` in CTEReference |
| 6 | DISTINCT-join logic | Safe EXISTS optimization |
| 7 | Cartesian fanout detection | Warning/error for multiple RESOURCE_ROWS |
| 7 | `ColumnRegistry` | Precomputed column lookup |
| 8 | Two-pass analysis | Pass 1 collects, Pass 2 generates |

**Exit Criteria**:
- [ ] No Cartesian fanout bugs
- [ ] `exists` on multi-row CTE uses DISTINCT
- [ ] Property access uses precomputed columns when available
- [ ] Strict mode errors on unsafe patterns

### Days 61-90: Robustness & Engine Support

| Week | Task | Deliverable |
|------|------|-------------|
| 9 | Engine capability flags | `EngineCapabilities` abstraction |
| 9 | Self-join alias keying | `semantic_alias` in CTEReference |
| 10 | Inter-resource correlation | `additional_predicates` for `with...such that` |
| 10 | Conditional RESOURCE_ROWS | Subquery fallback for `if/else` |
| 11 | `First()`/`Last()` ordering | `DEFAULT_SORT_COLUMNS` config |
| 11 | 3VL null handling | `COALESCE` wrapping in boolean context |
| 12 | EXPLAIN harness | CI plan regression detection |
| 12 | Cross-engine tests | DuckDB + PostgreSQL compatibility |

**Exit Criteria**:
- [ ] Self-joins work correctly
- [ ] `with...such that` generates correct JOIN predicates
- [ ] `First()` returns deterministic results
- [ ] CI catches query plan regressions
- [ ] Same results on DuckDB and PostgreSQL

---

## Appendix: Implementation Guardrails Checklist

Copy this checklist to your PR template:

```markdown
### Translation Safety Checklist

**Context & Scope**
- [ ] Single `SQLTranslationContext` used (not duplicate in translator.py)
- [ ] Fresh `SQLQueryBuilder` created per definition
- [ ] `query_builder` not shared across definitions

**Patient ID Consistency**
- [ ] All CTEs output `patient_id` column
- [ ] JOINs use `patient_id` on both sides
- [ ] No mixing of `patient_ref` and `patient_id`

**Shape Safety**
- [ ] `RowShape` inferred for all definitions
- [ ] DISTINCT used only when ALL usages are EXISTS/BOOLEAN
- [ ] Cartesian fanout detected and handled

**Forward References**
- [ ] Definitions topologically sorted
- [ ] Warning emitted for fallback to correlated subquery
- [ ] Strict mode errors on fallbacks

**Template Safety**
- [ ] No raw SQL string substitution for identifiers
- [ ] Alias lengths validated against engine limits
- [ ] Thread-safe alias generation

**Testing**
- [ ] Result-based tests (not just string matching)
- [ ] Boundary cases: 0, 1, 3+ resources per patient
- [ ] NULL handling tests
```

---

## Appendix: Quick Reference - SQL Patterns by Context

| CQL Expression | Source Shape | Usage | SQL Pattern |
|----------------|--------------|-------|-------------|
| `exists [Condition]` | RESOURCE_ROWS | EXISTS | `LEFT JOIN (DISTINCT patient_id) ... IS NOT NULL` |
| `Count([Condition])` | RESOURCE_ROWS | SCALAR | `(SELECT COUNT(*) FROM ... WHERE patient_id = p.patient_id)` |
| `First([Condition])` | RESOURCE_ROWS | SCALAR | `LATERAL (SELECT * FROM ... LIMIT 1)` or `ROW_NUMBER()` |
| `[Condition].status` | RESOURCE_ROWS | LIST | Keep as RESOURCE_ROWS, SELECT per row |
| `exists Definition` | PATIENT_SCALAR | EXISTS | `LEFT JOIN ... IS NOT NULL` |
| `Definition.value` | PATIENT_SCALAR | SCALAR | `LEFT JOIN ... .value` |
| `A and B` (both RESOURCE_ROWS) | RESOURCE_ROWS | BOOLEAN | **Error** or pre-aggregate |
| `if X then A else B` (A=RESOURCE_ROWS) | RESOURCE_ROWS | varies | Correlated subquery in CASE |
