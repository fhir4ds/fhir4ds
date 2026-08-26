# Design Decisions: Retrieve Optimization with Precomputed Columns

## Document Purpose

This document captures all architectural decisions made for implementing retrieve optimization with precomputed columns. It explains the options considered, the decisions made, and the rationale behind each decision.

**Related Documents:**
- Implementation Plan: `IMPLEMENTATION_PLAN_RETRIEVE_OPTIMIZATION.md`
- Original Design: `DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md`
- Status Reports: `FLUENT_FUNCTION_AST_STATUS.md`, `JOIN_OPTIMIZATION_RESULTS.md`

---

## Background and Problem Statement

### Current State

The CQL-to-SQL translator currently generates SQL with:
- **Correlated subqueries** for retrieve expressions (e.g., 649 in CMS165)
- **Inline FHIRPath calls** for property access (repeated for same properties)
- **No precomputed columns** in retrieve CTEs
- **Mixed AST/String approach** - some code uses AST, some uses string manipulation

Example of current inefficient SQL:
```sql
-- Repeated correlated subqueries with same FHIRPath calls
WHERE fhirpath_date(
    (SELECT resource FROM resources WHERE resourceType = 'Condition' AND ...),
    'onsetDateTime'
) IS NOT NULL
  AND fhirpath_date(
    (SELECT resource FROM resources WHERE resourceType = 'Condition' AND ...),
    'onsetDateTime'
  ) > @start
```

### Goals

1. **Reduce correlated subqueries** - Convert retrieves to CTEs that can be JOINed
2. **Precompute commonly accessed properties** - Add columns to retrieve CTEs
3. **Use pure AST approach** - No string manipulation or regex
4. **Dynamic property detection** - Automatically identify which properties to precompute based on usage
5. **Improve SQL performance** - Not translator performance (translation time doesn't matter)

---

## Decision 1: Pure AST Throughout Translation

### Options Considered

**Option A: Mixed AST/String (Current)**
```python
# Some code returns AST objects
result = SQLSelect(...)

# Some code returns strings
result = SQLExpression(sql="SELECT ...")

# String manipulation happens
sql = sql.replace("foo", "bar")
```

**Option B: Pure AST Until Final Generation**
```python
# Everything is AST
result = SQLSelect(...)

# Transformations are AST → AST
optimized = transform_ast(result)

# String generation only at the end
sql = result.to_sql()
```

**Option C: Gradual Migration**
```python
# Support both during transition
if hasattr(result, 'sql'):
    sql = result.sql  # Old way
else:
    sql = result.to_sql()  # New way
```

### Decision: Option B - Pure AST (No Gradual Migration)

**Rationale:**
1. **No working product yet** - No backward compatibility needed, can make breaking changes
2. **Cleaner architecture** - Single approach, no mixed patterns
3. **Maintainable** - AST transformations are structured and type-safe
4. **No regex needed** - AST walking is explicit and correct
5. **Easier to optimize** - Can walk/transform AST without string parsing

**Trade-offs Accepted:**
- Breaking changes to existing code (must update all `.sql` property access)
- All code must be updated at once (no gradual transition)

**Implementation Impact:**
- Remove `SQLExpression.sql` property
- All translation methods return AST objects
- Add `to_sql()` method as only string generation point
- Update all code that accesses `.sql` to use AST operations instead

---

## Decision 2: Dynamic Column Detection Based on Usage

### Options Considered

**Option A: Hardcoded Column List**
```python
PRECOMPUTED_COLUMNS = {
    "Condition": ["onset_date", "abatement_date", "verification_status"],
    "Observation": ["effective_date", "value_quantity"],
}
```

**Option B: Detect All Property Access, Precompute Based on Reuse Threshold**
```python
# Scan definitions, count property usage
property_usage = {
    ("Condition", "onsetDateTime"): 3,  # Used 3x
    ("Condition", "abatementDateTime"): 1,  # Used 1x
}

# Precompute only if usage >= threshold (e.g., 2)
if usage >= 2:
    add_column(property)
```

**Option C: Always Precompute All Accessed Properties (threshold=1)**
```python
# Scan definitions for property access
properties = scan_for_properties()

# Precompute everything that's accessed at least once
for prop in properties:
    add_column(prop)
```

### Decision: Option C - Always Precompute (threshold=1)

**Rationale:**
1. **Simpler code** - No counting logic, no threshold tuning
2. **Uniform handling** - All properties treated the same way
3. **Small overhead** - Extra columns are cheap (just metadata in CTE)
4. **Future-proof** - If definition is enabled later, column already exists
5. **Not about reuse** - Even single use benefits from cleaner SQL structure

**Why Not Threshold-Based:**
- Adds complexity (counting, threshold configuration)
- Marginal benefit (unused columns are cheap)
- Could miss optimization opportunities (threshold too high)

**Implementation Impact:**
- No usage counting needed
- Simple set of properties per retrieve
- Cleaner scanning logic

---

## Decision 3: Translation Approach - Placeholder-Based Single Pass

### Options Considered

**Option A: CQL AST Scanning (2 pass)**
```
Pass 1: Scan CQL AST (before translation)
  - Walk CQL AST to find retrieves and property accesses
  - Requires handling all CQL node types
  - Need metadata about what fluent functions access

Pass 2: Translate with CTEs
  - Create CTEs based on Pass 1 data
  - Translate CQL to SQL with CTE references
```

**Option B: SQL AST Scanning with Double Translation (2 pass)**
```
Pass 1: Translate + Scan
  - Translate CQL → SQL AST (retrieves are inline subqueries)
  - Scan SQL AST for fhirpath_* calls (uniform structure)
  - Build property usage map

Pass 2: Re-translate with CTEs
  - Create CTEs based on Pass 1 data
  - Translate CQL → SQL AST again (retrieves return CTE refs)
  - Apply optimizations
```

**Option C: Placeholder-Based Single Translation (1.5 pass)**
```
Pass 1: Translate with Placeholders + Scan
  - Translate CQL → SQL AST (retrieves return placeholders)
  - Scan SQL AST for fhirpath_* calls
  - Build property usage map

Pass 1.5: Build CTEs + Resolve Placeholders
  - Create CTEs based on Pass 1 data
  - Walk AST, replace placeholders with CTE references
  - Apply optimizations
```

### Decision: Option C - Placeholder-Based

**Rationale:**
1. **Correctness** - Scan the actual AST we'll optimize (no divergence between translations)
2. **Simpler retrieve translator** - Always returns placeholder (no mode switching)
3. **Clean phase separation** - Placeholder resolution is explicit and contained
4. **Translation performance doesn't matter** - User confirmed this, but single translation still cleaner
5. **No consistency issues** - Can't have mismatch between scanned properties and actual usage

**Why Not Double Translation (Option B):**
- Retrieve translator needs two modes (inline vs CTE ref) - more complex
- Risk of divergence between translations
- Scanning one AST, optimizing a different one - less clean

**Why Not CQL AST Scanning (Option A):**
- CQL AST has many node types (harder to walk)
- Need metadata about fluent function property access
- SQL AST is uniform (just look for fhirpath_* calls)

**Trade-offs Accepted:**
- New concept (RetrievePlaceholder) to understand
- Placeholder resolution step needed
- Must handle unresolved placeholders (error case)

**Implementation Impact:**
- New `RetrievePlaceholder` class
- Retrieve translator always returns placeholder
- Placeholder resolution transformer needed
- Clear error handling for unresolved placeholders

---

## Decision 4: Property Extraction - Automatic at Scan Time

### Options Considered

**Option A: Manual Annotation**
```python
FunctionDefinition(
    name="verified",
    accesses_properties=["verificationStatus.coding.code"],  # Manual
    builder=lambda resource: ...
)
```

**Option B: Extract from Builder at Registration Time**
```python
def extract_properties_from_builder(builder):
    dummy = SQLIdentifier("__dummy__")
    ast = builder(dummy)  # Call builder
    return scan_ast_for_fhirpath(ast)  # Extract properties

# At registration:
properties = extract_properties_from_builder(builder)
```

**Option C: Extract at Scan Time (Automatic)**
```python
# During Phase 1:
sql_ast = translate(definition)  # Fluent functions expanded
properties = scan_ast_for_fhirpath(sql_ast)  # Find all properties
# Properties from fluent functions found automatically!
```

### Decision: Option C - Automatic at Scan Time

**Rationale:**
1. **No special handling** - Fluent functions are just AST that gets scanned like everything else
2. **DRY** - Don't duplicate property information
3. **Always correct** - Finds actual usage, can't get out of sync
4. **Simpler** - No extra step at registration time
5. **Uniform** - All property access detected the same way (fluent functions, direct access, nested, etc.)

**Why Not Manual Annotation (Option A):**
- Maintenance burden (must keep in sync with code)
- Easy to forget or make mistakes
- Redundant with actual code

**Why Not Extract from Builder (Option B):**
- Magic (calling builder at registration)
- Need to handle edge cases (builders with side effects, multiple args, etc.)
- Extra complexity for no benefit (we're scanning anyway)

**Implementation Impact:**
- No special property extraction logic needed
- Fluent function builders just build AST
- Scanning finds all fhirpath_* calls naturally
- Simpler FunctionDefinition class

---

## Decision 5: Fluent Function Definition Format

### Options Considered

**Option A: Direct AST Construction in Lambda**
```python
FunctionDefinition(
    name="verified",
    builder=lambda resource: SQLFunctionCall(
        name="list_filter",
        args=[
            resource,
            SQLLambda(
                param="r",
                body=SQLBinaryOp(
                    operator="IN",
                    left=SQLFunctionCall(
                        name="fhirpath_text",
                        args=[SQLIdentifier("r"), SQLLiteral("verificationStatus.coding.code")]
                    ),
                    right=SQLList([SQLLiteral("confirmed"), SQLLiteral("provisional")])
                )
            )
        ]
    )
)
```

**Option B: Builder Method in Class**
```python
class FluentFunctionTranslator:
    def build_verified(self, resource):
        return SQLFunctionCall(...)

    def build_prevalence_interval(self, resource):
        return SQLCase(...)

registry.register("verified", translator.build_verified)
```

**Option C: DSL Helpers**
```python
FunctionDefinition(
    name="verified",
    builder=lambda r: list_filter(
        r,
        lambda_expr("r", in_op(
            fhirpath("r", "verificationStatus.coding.code"),
            ["confirmed", "provisional"]
        ))
    )
)
```

### Decision: Option A - Direct AST Construction

**Rationale:**
1. **No new abstractions** - Uses existing AST classes
2. **Explicit** - Clear what AST is being built
3. **Less code** - No extra builder methods or DSL
4. **Flexible** - Full power of Python and AST classes
5. **Debuggable** - Can inspect lambda code directly

**Why Not Builder Methods (Option B):**
- More boilerplate (method per function)
- Extra class structure
- Less flexible (methods are separate from definitions)

**Why Not DSL (Option C):**
- Need to build and maintain DSL functions
- Another layer of abstraction
- Not significantly more readable than Option A

**Trade-offs Accepted:**
- More verbose (but manageable with good formatting)
- Harder to read at first glance (but explicit)

**Implementation Impact:**
- FunctionDefinition just has `builder` callable
- No extra builder infrastructure needed
- Simple registration: `registry.register(FunctionDefinition(...))`

---

## Decision 6: Error Handling for Unresolved Placeholders

### Options Considered

**Option A: Hard Error (Fail Fast)**
```python
if placeholder not in cte_map:
    raise UnresolvedPlaceholderError(
        f"No CTE for {placeholder.resource_type}"
    )
```

**Option B: Fallback to Inline SQL**
```python
if placeholder not in cte_map:
    # Generate inline subquery as fallback
    return generate_inline_retrieve(placeholder)
```

**Option C: Warning + Skip Optimization**
```python
if placeholder not in cte_map:
    warnings.warn(f"Skipping optimization for {placeholder}")
    return placeholder  # Leave unresolved, handle later
```

### Decision: Option A - Hard Error

**Rationale:**
1. **Catch bugs early** - Unresolved placeholder indicates translator bug
2. **Clear feedback** - Explicit error message helps debugging
3. **No silent failures** - Don't generate suboptimal SQL quietly
4. **Development time** - Better to fail during development than production

**Why Not Fallback (Option B):**
- Hides bugs (might not notice optimization didn't work)
- Inconsistent behavior (some retrieves optimized, some not)
- Harder to debug (no clear indication of problem)

**Why Not Warning (Option C):**
- Warnings can be ignored
- Leaves system in invalid state
- Unclear what "handle later" means

**Implementation Impact:**
- `UnresolvedPlaceholderError` exception class
- Clear error messages with context
- Fail translation if placeholder can't be resolved

---

## Decision 7: CTE Naming and Deduplication

### Options Considered

**Option A: Friendly Names**
```sql
"Condition: Essential Hypertension" AS (...)
"Condition: Diabetes" AS (...)
```

**Option B: Generated Names**
```sql
"cte_retrieve_1" AS (...)
"cte_retrieve_2" AS (...)
```

**Option C: Hash-Based Names**
```sql
"cte_abc123" AS (...)  -- Hash of (resource_type, valueset)
```

### Decision: Option A - Friendly Names

**Rationale:**
1. **Debuggability** - Easy to identify CTEs in generated SQL
2. **Readable** - Humans can understand SQL without decoder
3. **Traceable** - Can match CTE to CQL definition visually
4. **Existing pattern** - Already used in current implementation

**Name Format:**
```
"{ResourceType}: {ValueSetName}"
```

**Deduplication Strategy:**
One CTE per unique `(resource_type, valueset)` pair:
- Same retrieve used multiple times → reuse same CTE
- Different valuesets → different CTEs (different filters)
- CTE includes ALL properties accessed across ALL usages

**Implementation Impact:**
- CTE name derived from resource type + valueset name
- Registry maps `(resource_type, valueset)` → CTE name
- Property set is union of all usages

---

## Decision 8: Phase Result Objects

### Options Considered

**Option A: Store State in Context**
```python
context.property_usage = {...}
context.retrieve_ctes = {...}
```

**Option B: Explicit Phase Result Objects**
```python
@dataclass
class Phase1Result:
    property_usage: Dict
    definition_asts: Dict
    placeholders: List

phase1_result = run_phase1()
phase2_result = run_phase2(phase1_result)
```

**Option C: Return Tuples**
```python
property_usage, asts, placeholders = run_phase1()
ctes, registry = run_phase2(property_usage)
```

### Decision: Option B - Explicit Phase Result Objects

**Rationale:**
1. **Clear interfaces** - Each phase has well-defined input/output
2. **Type safety** - Can type-hint and validate
3. **Testable** - Easy to construct test inputs
4. **Documentable** - Structure is self-documenting
5. **Maintainable** - Adding fields doesn't break function signatures

**Why Not Context Storage (Option A):**
- Implicit state (hard to track what's available when)
- No clear ownership (who sets what?)
- Harder to test (need full context setup)

**Why Not Tuples (Option C):**
- Positional arguments (easy to mix up)
- No field names (unclear what each value is)
- Hard to extend (adding field breaks all calls)

**Implementation Impact:**
- Define dataclass for each phase result
- Clear type hints on phase functions
- Easy to serialize/debug (can print result objects)

---

## Decision 9: Placeholder Design

### Options Considered

**Option A: Unique ID Per Instance**
```python
@dataclass
class RetrievePlaceholder:
    resource_type: str
    valueset: Optional[str]
    placeholder_id: str  # UUID or counter
```

Each retrieve in AST gets unique ID, needs tracking map.

**Option B: Deterministic Key**
```python
@dataclass
class RetrievePlaceholder:
    resource_type: str
    valueset: Optional[str]

    @property
    def key(self):
        return (self.resource_type, self.valueset)
```

All retrieves with same resource+valueset have same key.

### Decision: Option B - Deterministic Key

**Rationale:**
1. **Simpler** - No ID generation or tracking needed
2. **Natural mapping** - Key directly maps to CTE
3. **Deduplication built-in** - Same key = same CTE automatically
4. **Less state** - No ID-to-CTE mapping needed

**Why Not Unique IDs (Option A):**
- Extra complexity (ID generation, tracking)
- Need separate map: `placeholder_id → CTE_name`
- No benefit over deterministic key

**Implementation Impact:**
- `RetrievePlaceholder` has just resource_type and valueset
- Key is `(resource_type, valueset)` tuple
- CTE registry maps same key to CTE name
- No ID tracking infrastructure needed

---

## Summary of All Decisions

| Decision | Chosen Approach | Key Rationale |
|----------|----------------|---------------|
| **AST vs String** | Pure AST throughout | No working product yet, cleaner architecture |
| **Column Detection** | Precompute all accessed (threshold=1) | Simpler code, marginal overhead |
| **Translation Approach** | Placeholder-based single pass | Correctness, simpler retrieve translator |
| **Property Extraction** | Automatic at scan time | No special handling, always correct |
| **Fluent Function Format** | Direct AST construction in lambda | No new abstractions, explicit |
| **Error Handling** | Hard error on unresolved placeholder | Catch bugs early, clear feedback |
| **CTE Naming** | Friendly names (ResourceType: ValueSet) | Debuggability, readability |
| **Phase Results** | Explicit dataclass objects | Clear interfaces, testable |
| **Placeholder Design** | Deterministic key (no IDs) | Simpler, natural mapping |

---

## Risks and Mitigations

### Risk 1: Placeholder Complexity
**Concern:** New concept might be hard to understand/maintain

**Mitigation:**
- Clear documentation with examples
- Simple design (deterministic keys, no tracking)
- Explicit error messages
- Good test coverage

### Risk 2: AST Walking Performance
**Concern:** Multiple AST walks might be slow

**Mitigation:**
- User confirmed translation performance doesn't matter
- If needed: combine walks (scan + transform in one pass)
- Profile before optimizing

### Risk 3: Breaking Changes
**Concern:** Removing `.sql` property breaks existing code

**Mitigation:**
- No working product yet (user confirmed)
- Update all code at once
- Clear error messages if `.sql` accessed

### Risk 4: Property Detection Completeness
**Concern:** Might miss some property accesses

**Mitigation:**
- Comprehensive AST walker that handles all node types
- Test with complex expressions
- Fallback to FHIRPath if column not found (optimization, not correctness)

---

## Success Criteria

This implementation will be successful if:

1. **SQL Performance Improved**
   - Fewer correlated subqueries in generated SQL
   - Retrieves converted to CTEs with JOINs
   - Precomputed columns used instead of repeated FHIRPath calls

2. **No Regex or String Manipulation**
   - All transformations use AST operations
   - String generation only at final `to_sql()` call

3. **Dynamic Property Detection**
   - Properties detected automatically from usage
   - No hardcoded column lists needed
   - Works across different CQL libraries

4. **Maintainable Code**
   - Clear phase separation
   - Type-safe with good type hints
   - Well-tested with good coverage
   - Documented for future developers

5. **Correct Translation**
   - All placeholders resolve successfully
   - Generated SQL is valid and equivalent to input CQL
   - No silent optimization failures

---

## Future Considerations

### Beyond This Implementation

**Items NOT included in this design** (future work):

1. **Column usage statistics** - Track which precomputed columns are actually used
2. **Adaptive optimization** - Tune strategy based on query patterns
3. **Cross-definition optimization** - Share retrieves across multiple definitions
4. **User-defined fluent functions** - Support for library-defined functions beyond built-ins
5. **Property path simplification** - Optimize complex FHIRPath expressions
6. **Index hints** - Suggest indexes for precomputed columns

### Extensibility Points

This design supports future enhancements:

- **New AST transformations** - Easy to add new optimizers
- **Different CTE strategies** - Can swap out CTE building logic
- **Alternative property detection** - Can enhance scanner for special cases
- **Pluggable builders** - Can register custom fluent function builders

---

## References

- Architecture discussions in conversation history
- Original design: `DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md`
- Status report: `FLUENT_FUNCTION_AST_STATUS.md`
- Join optimization: `JOIN_OPTIMIZATION_RESULTS.md`
- Column registry: `COLUMN_REGISTRY_STATUS.md`
