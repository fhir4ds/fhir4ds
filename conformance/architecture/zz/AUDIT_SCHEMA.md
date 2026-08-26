# Audit Evidence Schema Reference

> Single source of truth for the Glass Box Audit evidence contract.

## Evidence Struct (DuckDB)

Each evidence item is a DuckDB STRUCT with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `target` | VARCHAR | What was checked — FHIR resource ID (e.g., `Observation/123`) or definition name |
| `attribute` | VARCHAR | Clinical attribute evaluated (nullable) |
| `value` | VARCHAR | Observed value from the resource (nullable) |
| `operator` | VARCHAR | Comparison operator (`=`, `<`, `>`, `exists`, `absent`) |
| `threshold` | VARCHAR | Expected/comparison value or ValueSet name |
| `trace` | VARCHAR[] | Breadcrumb trail of CQL definition names |

```sql
-- Raw evidence struct (before compact_audit)
struct_pack(
  target    := 'Observation/bp-1',
  attribute := 'value.ofType(Quantity).value',
  value     := '135.0',
  operator  := '<',
  threshold := '140.0',
  trace     := ['Blood Pressure', 'Most Recent BP Day', 'Has Systolic BP < 140']
)
```

## Audit Result Struct

Each population column becomes a result + evidence pair:

```sql
struct_pack(
  result   := TRUE,
  evidence := [<evidence_struct>, ...]
)
```

## Compact (Grouped) Evidence

After `compact_audit()`, evidence is grouped by `(trace, attribute, operator, threshold)`:

```json
[
  {
    "trace": ["Blood Pressure", "Most Recent BP Day", "Has Systolic BP < 140", "Numerator"],
    "attribute": "value.ofType(Quantity).value",
    "operator": "<",
    "threshold": "140.0",
    "findings": [
      {"target": "Observation/bp-1", "value": "135.0"},
      {"target": "Observation/bp-2", "value": "138.0"}
    ]
  }
]
```

## Evidence Lifecycle

```
1. CREATION     - _audit_item in Retrieve CTEs
2. PROPAGATION  - audit_and/or/not merge evidence through boolean logic
3. BREADCRUMB   - audit_breadcrumb appends definition names to trace
4. GROUPING     - compact_audit groups by (trace, attribute, operator, threshold)
5. PRUNING      - AuditEngine.prune_evidence filters by population persona
6. NARRATIVE    - NarrativeGenerator.generate produces human-readable text
```

### Stage 1: Creation

Evidence items are created at Retrieve CTEs:

```sql
-- EXISTS evidence: resource was found
struct_pack(
  target := r.resourceType || '/' || id,
  attribute := NULL, value := NULL,
  operator := 'exists',
  threshold := '[Encounter]',
  trace := []
)

-- ABSENT sentinel: no matching resource
struct_pack(
  target := 'Encounter',
  attribute := NULL, value := NULL,
  operator := 'absent',
  threshold := 'Encounter',
  trace := []
)
```

### Stage 2: Propagation

Boolean macros merge evidence without inspecting fields:

| Macro | Behavior |
|-------|----------|
| `audit_and(a, b)` | `list_concat(a.evidence, b.evidence)` |
| `audit_or(a, b)` | True branch only; both if neither true |
| `audit_or_all(a, b)` | Always both branches |
| `audit_not(a)` | Invert result, preserve evidence |
| `audit_leaf(val)` | Wrap scalar with empty evidence |

### Stage 3: Breadcrumb

`audit_breadcrumb(aud, def_name)` appends the definition name to each item's trace:

```sql
trace := list_append(COALESCE(_ev.trace, []), 'Definition Name')
```

### Stage 4: Grouping

`compact_audit(aud)` groups evidence by key `(trace, attribute, operator, threshold)` and nests findings:

```sql
-- Input: flat list of evidence items
-- Output: list of groups, each with findings array
-- count is derivable from len(findings)
```

### Stage 5: Pruning

`AuditEngine.prune_evidence()` filters evidence based on population persona:

| Persona | Behavior |
|---------|----------|
| INCLUSION | Always return evidence |
| EXCLUSION | Return evidence only if result is True (patient excluded) |
| NUMERATOR | Always return evidence |

### Stage 6: Narrative

`NarrativeGenerator.generate()` produces human-readable fragments from grouped evidence.

## Scalar Attribution

When CQL aggregate functions select a single resource from a query, the winning
resource's ID is propagated to the `target` field in `audit_comparison` evidence.
This allows evidence to show which specific FHIR resource produced the comparison value.

### First/Last Attribution

```sql
-- First()/Last() on a Query/Retrieve: target is populated with the winner's ID
audit_comparison(
  value < 140,                -- result
  '<',                        -- operator
  value,                      -- lhs (observed)
  140,                        -- rhs (threshold)
  'value.ofType(Quantity)',   -- attribute
  (SELECT resourceType || '/' || id FROM "Last BP" WHERE ...)  -- target
)
```

The `_audit_target` metadata is stored in `DefinitionMeta.audit_target_expr` so
that scalar CTEs derived from First/Last (e.g., `First(... return O.value)`)
preserve the winning resource ID across CTE serialization boundaries.

### Min/Max Attribution

Min/Max use DuckDB's `arg_min`/`arg_max` aggregate functions to identify the
winning resource alongside the aggregate value:

```sql
-- Min() on a RESOURCE_ROWS query: target via arg_min
audit_comparison(
  value < 140,
  '<',
  (SELECT MIN(_val) FROM (...) _agg),
  140,
  'observation.value',
  (SELECT arg_min(_rid, _val) FROM (...) _agg)  -- winner resource ID
)
```

**Supported aggregates:**
- `First()` — target = first matching resource ID (window LIMIT 1)
- `Last()` — target = last matching resource ID (window LIMIT 1)
- `Min()` — target = resource with minimum value (`arg_min`)
- `Max()` — target = resource with maximum value (`arg_max`)

**Unsupported (target = NULL):**
- `list_min()`/`list_max()` — pre-built lists lose resource provenance
- `Count()`, `Sum()`, `Avg()` — multi-resource aggregates have no single winner

## Macro Reference

| Macro | Arguments | Returns |
|-------|-----------|---------|
| `audit_and(a, b)` | Two audit structs | Merged audit struct |
| `audit_or(a, b)` | Two audit structs | True-branch audit struct |
| `audit_or_all(a, b)` | Two audit structs | All-branch audit struct |
| `audit_not(a)` | One audit struct | Inverted audit struct |
| `audit_leaf(val)` | Boolean value | Audit struct with empty evidence |
| `audit_comparison(result_val, op, lhs, rhs, ev_attr, target_id)` | Comparison parts + target | Audit struct with one evidence item |
| `compact_audit(aud)` | Audit struct | Grouped audit struct |
| `audit_breadcrumb(aud, def_name)` | Audit struct + name | Breadcrumbed audit struct |

## Migration Guide

Field names have been renamed through two phases:

### Phase 1: Computer-centric → Clinical-centric (PLAN-AUDIT-REFACTOR)

| Old Name | New Name | Rationale |
|----------|----------|-----------|
| `via` | `trace` | Breadcrumb trail through CQL definitions |
| `left` | `actual` | Observed clinical value |
| `right` | `threshold` | Expected/comparison value |
| `path` | `attribute` | Clinical attribute being evaluated |

### Phase 2: Naming Consolidation (PLAN-AUDIT-ENHANCEMENTS)

| Old Name | New Name | Rationale |
|----------|----------|-----------|
| `resource_id` | `target` | Unifies FHIR resource IDs and definition names |
| `actual` | `value` | Simpler, broader compatibility |
| `count` | *(removed)* | Redundant — derivable from `len(findings)` |

Additionally, `audit_comparison` gained a 6th parameter (`target_id`) for scalar
attribution, allowing the "winner" resource ID from `First()`/`Last()` to flow
through to comparison evidence.
