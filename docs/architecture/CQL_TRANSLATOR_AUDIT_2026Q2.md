# CQL-to-SQL Translator — Architecture Audit Report

**Date:** 2026-Q2 Refresh  
**Scope:** `fhir4ds/cql/translator/` + supporting modules  
**Auditor:** Principal Architect  
**Verdict:** 3 of 8 invariants PASS, 5 FAIL

---

## 1. Invariant Compliance Matrix

| # | Invariant | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | **Pure AST pipeline — no SQLRaw mid-pipeline** | **FAIL** | 46 total `SQLRaw(` calls; ≥12 are mid-pipeline (see §3) |
| 2 | **Context is single source of truth** | **FAIL** | `context.py:490-492` silently falls back to `get_default_profile_registry()`; `cte_builder.py:75` also falls back; dual `definitions`/`definition_asts` storage |
| 3 | **CQL is source of truth — no JSON config duplicating CQL logic** | **PASS** | No `status_filters.json` found. JSON configs are for FHIR schema metadata, not CQL logic duplication |
| 4 | **Fail fast — raise on missing context** | **FAIL** | Silent fallbacks in `context.py:490`, `cte_builder.py:64-75`, `fhir_schema.py:235-240` (hardcoded default resources), `_property.py:158` (fallback loop), `column_generation.py:176` (silent skip) |
| 5 | **Three-layer schema separation** | **PASS** | `FHIRSchemaRegistry` (FHIR base), `ProfileRegistry` (profiles), `SQLTranslationContext` (runtime) correctly layered in `translator.py:246-250` |
| 6 | **No bare `FHIRSchemaRegistry()`** | **PASS** | Both production instantiations pass `model_config=`. 10 bare calls exist but ALL in test files only |
| 7 | **No `get_default_profile_registry()` bypassing context** | **FAIL** | `context.py:492` and `cte_builder.py:75` both call it as fallback instead of raising |
| 8 | **No Strategy 2 string templates** | **FAIL** | `fluent_functions.py` has an active `body_sql` template substitution system (lines 1734-1741, 1747-1792) with `{resource}` placeholders and `.replace()` calls |

---

## 2. Counts Summary

| Metric | Count | Notes |
|--------|-------|-------|
| **`SQLRaw(` total usages** | **46** | Across 16 files in `translator/` |
| **`SQLRaw(` mid-pipeline violations** | **≥12** | In `fluent_functions.py` (4), `_operators.py` (2), `_query.py` (3), `_core.py` (1), `_property.py` (1), `cte_builder.py` (1) |
| **`.to_sql()` total calls** | **97** | Across 13 files |
| **`.to_sql()` in `types.py` (legitimate)** | **48** | Internal serialization — compliant |
| **`.to_sql()` in `translator.py` (final)** | **9** | Final serialization — compliant |
| **`.to_sql()` mid-pipeline violations** | **≥22** | In `fluent_functions.py` (10), `_functions.py` (7), `_operators.py` (6), `_query.py` (5), `ast_helpers.py` (1), `cte_manager.py` (2), `_temporal_utils.py` (2), `patterns/temporal.py` (1) |
| **`get_default_profile_registry()` calls** | **2 in production** | `context.py:492`, `cte_builder.py:75` — both unguarded fallbacks |
| **Bare `FHIRSchemaRegistry()`** | **0 in production** | 10 in test files only |
| **`status_filters.json`** | **0** | Not found anywhere |
| **Hardcoded CMS measure IDs** | **3** | All in comments/docstrings (`CMS165`, `CMS117`, `CMS124`) — no logic coupling |
| **Hardcoded FHIR resource type strings** | **4 sites** | `queries.py:545` (24 types), `_property.py:158` (6 types), `_temporal_intervals.py:43` (15 types), `fhir_schema.py:235` (12 types) |
| **Hardcoded QICore profile prefixes** | **2 sites** | `profile_registry.py:150-153`, `cte_builder.py:179` |
| **Strategy 2 string templates** | **1 system** | `fluent_functions.py` `body_sql` template substitution with `{resource}` placeholder |

---

## 3. Issue Log

### Issue CQL-001
**File:** `fhir4ds/cql/translator/fluent_functions.py:1353,1414,1551,1610`  
**Severity:** Critical  
**Category:** SQLRaw-Violation  
**Description:** Four `SQLRaw()` calls embed full SELECT statements as raw SQL strings mid-pipeline, bypassing the AST.  
**Current Code:**
```python
expr=SQLRaw(
    "(SELECT patient_ref AS patient_id, resource"
    " FROM resources WHERE resourceType = 'Condition')"
),
```
**Proposed Fix:** Replace with `SQLSelect(columns=[...], from_clause=SQLIdentifier("resources"), where=SQLBinaryOp(...))` AST nodes.  
**AC:** Zero `SQLRaw` calls in `_get_condition_resources`, `_get_claim_resources`, `_get_procedure_resources`, `_get_prerequisite_resources`.

---

### Issue CQL-002
**File:** `fhir4ds/cql/translator/expressions/_query.py:3096-3110`  
**Severity:** Critical  
**Category:** SQLRaw-Violation  
**Description:** Recursive CTE for `Aggregate` clause built as a single massive `SQLRaw()` string (~15 lines of raw SQL). This is the worst single SQLRaw violation in the codebase.  
**Current Code:**
```python
self.context.add_alias(accum_name, ast_expr=SQLRaw("__fold.__acc"))
...
result = SQLRaw(
    f"(WITH RECURSIVE __xj AS (...) __fold(...) AS (...) SELECT __acc FROM __fold ...)"
)
```
**Proposed Fix:** Introduce `SQLRecursiveCTE` and `SQLWithClause` AST node types. Build the fold expression as a structured AST tree.  
**AC:** `_translate_aggregate()` produces zero `SQLRaw` nodes; recursive CTE is fully structured.

---

### Issue CQL-003
**File:** `fhir4ds/cql/translator/context.py:488-492`  
**Severity:** Critical  
**Category:** Silent-Fallback / SSOT-Violation  
**Description:** The comment on line 489 says *"Downstream code must never fall back to `get_default_profile_registry()`"* — but line 492 does exactly that. This is a self-contradictory silent fallback that undermines the SSOT invariant.  
**Current Code:**
```python
# Downstream code must never fall back to get_default_profile_registry().
if self.profile_registry is None:
    from ..translator.profile_registry import get_default_profile_registry
    self.profile_registry = get_default_profile_registry()
```
**Proposed Fix:**
```python
if self.profile_registry is None:
    raise ValueError(
        "SQLTranslationContext requires an explicit profile_registry. "
        "Pass profile_registry= to the constructor."
    )
```
**AC:** `get_default_profile_registry()` is never called from `context.py`. All callers provide an explicit registry.

---

### Issue CQL-004
**File:** `fhir4ds/cql/translator/cte_builder.py:64-75`  
**Severity:** High  
**Category:** Silent-Fallback / SSOT-Violation  
**Description:** `_resolve_profile_registry()` falls back to `get_default_profile_registry()` when context is None, rather than raising.  
**Current Code:**
```python
def _resolve_profile_registry(context) -> "ProfileRegistry":
    if context is not None and context.profile_registry is not None:
        return context.profile_registry
    from .profile_registry import get_default_profile_registry
    return get_default_profile_registry()
```
**Proposed Fix:**
```python
def _resolve_profile_registry(context) -> "ProfileRegistry":
    if context is None or context.profile_registry is None:
        raise RuntimeError("CTE builder requires context with profile_registry")
    return context.profile_registry
```
**AC:** `get_default_profile_registry()` is only called from `profile_registry.py` itself and test code.

---

### Issue CQL-005
**File:** `fhir4ds/cql/translator/expressions/_temporal_intervals.py:43-59`  
**Severity:** High  
**Category:** Hardcoded-Logic  
**Description:** `_RESOURCE_PRIMARY_DATE_PATHS` hardcodes 15 resource-type-to-date-path mappings. Adding new resource types requires modifying Python source.  
**Current Code:**
```python
_RESOURCE_PRIMARY_DATE_PATHS: dict = {
    "Encounter": "period",
    "Procedure": "performed",
    "Observation": "effective",
    ...  # 12 more entries
}
```
**Proposed Fix:** Load from `FHIRSchemaRegistry` or a versioned JSON config file in `resources/schema/`.  
**AC:** No hardcoded resource-type-to-date mappings in `_temporal_intervals.py`.

---

### Issue CQL-006
**File:** `fhir4ds/cql/translator/queries.py:545-551`  
**Severity:** High  
**Category:** Hardcoded-Logic  
**Description:** `fhir_types` set hardcodes 24 FHIR resource type names. This prevents dynamic extension.  
**Current Code:**
```python
fhir_types = {
    "Patient", "Condition", "Observation", "Encounter", "MedicationRequest",
    "Medication", "Procedure", ...
}
```
**Proposed Fix:** Query `context.fhir_schema.loaded_resources` or load from registry.  
**AC:** No hardcoded set of resource type names in `queries.py`.

---

### Issue CQL-007
**File:** `fhir4ds/cql/translator/expressions/_property.py:158`  
**Severity:** High  
**Category:** Hardcoded-Logic / Silent-Fallback  
**Description:** When context lacks a resource type, falls back to brute-force looping over 6 hardcoded resource types to find a UDF match.  
**Current Code:**
```python
for rt in ["Observation", "Condition", "Encounter", "Procedure", "MedicationRequest", "Patient"]:
    udf = schema.get_udf_for_element(rt, path)
    if udf:
        return udf
```
**Proposed Fix:** Require resource type from context. If genuinely unknown, query `schema.loaded_resources` for the full set.  
**AC:** No hardcoded resource type list in `_property.py`.

---

### Issue CQL-008
**File:** `fhir4ds/cql/translator/fhir_schema.py:235-240`  
**Severity:** Medium  
**Category:** Hardcoded-Logic  
**Description:** `load_default_resources()` hardcodes 12 resource types. Adding a new default resource requires code change.  
**Current Code:**
```python
default_resources = [
    "Patient", "Observation", "Condition", "Encounter",
    "Procedure", "MedicationRequest", "DiagnosticReport",
    "ServiceRequest", "Immunization", "AllergyIntolerance",
    "Task", "Coverage"
]
```
**Proposed Fix:** Load the default resource list from a versioned config file or auto-discover from the schema directory.  
**AC:** Default resource list is externalized.

---

### Issue CQL-009
**File:** `fhir4ds/cql/translator/profile_registry.py:150-153`  
**Severity:** Medium  
**Category:** Hardcoded-Logic  
**Description:** Profile name resolution uses hardcoded "QICore-" and "QICore" prefix stripping as fallback.  
**Current Code:**
```python
if profile_name.startswith("QICore-"):
    return (profile_name[7:], None)
if profile_name.startswith("QICore"):
    return (profile_name[6:], None)
```
**Proposed Fix:** Move prefix patterns to the profile JSON config. Log a warning when falling back to prefix stripping.  
**AC:** No hardcoded "QICore" prefix strings in `profile_registry.py`.

---

### Issue CQL-010
**File:** `fhir4ds/cql/translator/cte_builder.py:179`  
**Severity:** Medium  
**Category:** Hardcoded-Logic  
**Description:** Hardcoded `'qicore-'` string replacement for profile URL parsing.  
**Current Code:**
```python
profile_suffix = _url.rsplit('/', 1)[-1].replace('qicore-', '')
```
**Proposed Fix:** Use `ProfileRegistry.resolve_url()` or parameterize prefix.  
**AC:** No hardcoded `'qicore-'` string in `cte_builder.py`.

---

### Issue CQL-011
**File:** `fhir4ds/cql/translator/column_generation.py:210`  
**Severity:** Medium  
**Category:** Hardcoded-Logic  
**Description:** Component profile detection hardcoded to `resource_type == "Observation"` only.  
**Current Code:**
```python
if profile_url and resource_type == "Observation" and profile_registry:
    keywords = profile_registry.component_profile_keywords
    if any(kw in profile_url for kw in keywords):
        paths |= BP_COMPONENT_PROPERTY_PATHS
```
**Proposed Fix:** Query `ProfileRegistry` for which resource types support component profiles.  
**AC:** No hardcoded `"Observation"` check for component profiles.

---

### Issue CQL-012
**File:** `fhir4ds/cql/translator/expressions/_operators.py:1390-1395`  
**Severity:** High  
**Category:** SQLRaw-Violation / to_sql-Mid-Pipeline  
**Description:** Null-check predicates in Tuple equality built by calling `.to_sql()` mid-pipeline and embedding in `SQLRaw`.  
**Current Code:**
```python
left=SQLRaw(f"({lv.to_sql()}) IS NULL"),
right=SQLRaw(f"({rv.to_sql()}) IS NULL")
```
**Proposed Fix:** Use `SQLIsNull(expr=lv)` AST node instead of serializing to string.  
**AC:** No `.to_sql()` calls in `_translate_eq_op()` null-check construction.

---

### Issue CQL-013
**File:** `fhir4ds/cql/translator/expressions/_operators.py:2908`  
**Severity:** High  
**Category:** SQLRaw-Violation / to_sql-Mid-Pipeline  
**Description:** NOT operator wraps temporal equality result by double-serializing via `.to_sql()`.  
**Current Code:**
```python
result = SQLRaw(f"CASE WHEN {result.to_sql()} IS NULL THEN NULL WHEN {result.to_sql()} THEN false ELSE true END")
```
**Proposed Fix:** Use `SQLCase` AST node with `SQLIsNull(result)` and `SQLNot(result)` branches.  
**AC:** No `.to_sql()` call on line 2908.

---

### Issue CQL-014
**File:** `fhir4ds/cql/translator/expressions/_functions.py:697-700`  
**Severity:** High  
**Category:** SQLRaw-Violation / to_sql-Mid-Pipeline  
**Description:** Quantity aggregate wrapping serializes 3 sub-expressions to SQL strings and embeds in SQLRaw CASE.  
**Current Code:**
```python
unit_sql = unit_json.to_sql()
return SQLRaw(
    f"CASE WHEN ({agg_result.to_sql()}) IS NULL THEN NULL "
    f"ELSE CAST(json_object('value', ({agg_result.to_sql()})::DOUBLE, ..."
)
```
**Proposed Fix:** Build `SQLCase` with `SQLFunctionCall("json_object", ...)` children.  
**AC:** No `.to_sql()` calls in quantity aggregate construction.

---

### Issue CQL-015
**File:** `fhir4ds/cql/translator/expressions/_functions.py:934-935`  
**Severity:** Medium  
**Category:** SQLRaw-Violation / to_sql-Mid-Pipeline  
**Description:** `Log()` function implementation serializes arguments into SQLRaw.  
**Current Code:**
```python
return SQLRaw(raw_sql=f"TRY(system.log({args[1].to_sql()}, {args[0].to_sql()}))")
return SQLRaw(raw_sql=f"TRY(LN({args[0].to_sql()}))")
```
**Proposed Fix:** Use `SQLFunctionCall("TRY", [SQLFunctionCall("system.log", [args[1], args[0]])])`.  
**AC:** No `.to_sql()` in log function translation.

---

### Issue CQL-016
**File:** `fhir4ds/cql/translator/expressions/_temporal_utils.py:572`  
**Severity:** Medium  
**Category:** SQLRaw-Violation / to_sql-Mid-Pipeline  
**Description:** `intervalStart`/`intervalEnd` cast built via `.to_sql()` embedded in SQLRaw.  
**Current Code:**
```python
return SQLRaw(f"TRY_CAST(({expr.to_sql()}) AS TIMESTAMP)")
```
**Proposed Fix:** Use `SQLCast(expr=expr, target_type="TIMESTAMP")` AST node.  
**AC:** No `.to_sql()` in temporal interval start/end.

---

### Issue CQL-017
**File:** `fhir4ds/cql/translator/fluent_functions.py:1734-1741, 2314-2413`  
**Severity:** High  
**Category:** Strategy-2-Template  
**Description:** Active `body_sql` string template substitution system using `{resource}` placeholders and `.replace()`. The code acknowledges this is technical debt (line 1761: "deferred to Task C4") but it's an active Strategy 2 violation.  
**Current Code:**
```python
# line 1734-1736
if func_def.body_sql:
    return self._substitute_template(func_def.body_sql, resource_expr, args, func_def)

# line 2413
result = result.replace("FROM {resource}", f"FROM {resource_for_from.to_sql()}")
return result.replace("{resource}", resource_sql)
```
**Proposed Fix:** Complete Task C4: parse `body_sql` templates to AST, eliminate string templates entirely.  
**AC:** `body_sql` attribute removed from `FunctionDefinition`; all fluent functions use AST inlining.

---

### Issue CQL-018
**File:** `fhir4ds/cql/translator/fluent_functions.py:1255,1458`  
**Severity:** Medium  
**Category:** to_sql-Mid-Pipeline  
**Description:** Valueset argument extracted by calling `.to_sql()` and parsing the resulting SQL string to find a URL.  
**Current Code:**
```python
raw = valueset_arg.to_sql()
if raw.startswith("'") and raw.endswith("'"):
    vs_url = raw[1:-1].replace("''", "'")
```
**Proposed Fix:** Check `isinstance(valueset_arg, SQLLiteral)` and extract `.value` directly from the AST node.  
**AC:** No `.to_sql()` for valueset URL extraction.

---

### Issue CQL-019
**File:** `fhir4ds/cql/translator/cte_manager.py:64`  
**Severity:** High  
**Category:** to_sql-Mid-Pipeline  
**Description:** Audit tree flattening prematurely serializes terms to SQL strings, then joins with OR/AND string operators.  
**Current Code:**
```python
term_sqls = [t.to_sql() for t in terms]
result_expr = " OR ".join(f"({s}).result" for s in term_sqls)
```
**Proposed Fix:** Build `SQLBinaryOp("OR", ...)` chain from AST terms, accessing `.result` via `SQLQualifiedIdentifier`.  
**AC:** `_flatten_audit_tree()` produces AST nodes, not strings.

---

### Issue CQL-020
**File:** `fhir4ds/cql/translator/ast_helpers.py:1771-1804`  
**Severity:** High  
**Category:** SQLRaw-Violation / to_sql-Mid-Pipeline  
**Description:** `_inject_audit_evidence()` serializes audit expressions to SQL then rebuilds as SQLRaw struct_pack strings.  
**Current Code:**
```python
expr_sql = expr.to_sql()
return SQLRaw(
    f"struct_pack(result := ({expr_sql}).result, "
    f"evidence := list_concat(COALESCE(({expr_sql}).evidence, []), {evidence_sql}))"
)
```
**Proposed Fix:** Introduce `SQLStructPack` AST node with named field access.  
**AC:** No `.to_sql()` calls in `_inject_audit_evidence()`.

---

### Issue CQL-021
**File:** `fhir4ds/cql/translator/cte_builder.py:176-182`  
**Severity:** Low  
**Category:** Hardcoded-Logic  
**Description:** Negation pattern suffixes hardcoded as a tuple.  
**Current Code:**
```python
NEGATION_PATTERNS = ('notrequested', 'notdone', 'cancelled')
```
**Proposed Fix:** Load from `ProfileRegistry.negation_patterns`.  
**AC:** Negation patterns externalized.

---

### Issue CQL-022
**File:** `fhir4ds/cql/translator/profile_registry.py:295-301`  
**Severity:** Medium  
**Category:** Global-Singleton  
**Description:** `get_default_profile_registry()` uses a module-level singleton with no invalidation. Breaks test isolation and multi-version support.  
**Current Code:**
```python
_default_registry: Optional[ProfileRegistry] = None

def get_default_profile_registry() -> ProfileRegistry:
    global _default_registry
    if _default_registry is None:
        from ..translator.model_config import DEFAULT_MODEL_CONFIG
        _default_registry = ProfileRegistry.from_model_config(DEFAULT_MODEL_CONFIG)
    return _default_registry
```
**Proposed Fix:** Remove global singleton. Require explicit construction with `model_config` at all call sites.  
**AC:** `_default_registry` global removed; all callers construct explicitly.

---

### Issue CQL-023
**File:** `fhir4ds/cql/loader/fhir_loader.py:16-17`  
**Severity:** Medium  
**Category:** Global-Mutable-State  
**Description:** Module-level `WeakKeyDictionary` and `WeakSet` caches for valueset UDFs persist across instances, creating implicit shared state.  
**Current Code:**
```python
_VALUESET_UDF_CACHE_BY_CONNECTION = WeakKeyDictionary()
_VALUESET_UDF_REGISTERED_CONNECTIONS = WeakSet()
```
**Proposed Fix:** Move cache into `FHIRDataLoader` instance or `SQLTranslationContext`.  
**AC:** No module-level mutable globals in `fhir_loader.py`.

---

### Issue CQL-024
**File:** `fhir4ds/cql/translator/context.py:352`  
**Severity:** Low  
**Category:** Hardcoded-Logic  
**Description:** Default context hardcoded to `"Patient"`. While this matches CQL spec defaults, it should be explicit.  
**Current Code:**
```python
current_context: str = "Patient"
```
**Proposed Fix:** No code change needed — this matches the CQL specification default. Document the rationale.  
**AC:** Add docstring comment explaining CQL spec alignment.

---

### Issue CQL-025
**File:** `fhir4ds/cql/translator/patterns/temporal.py:824-831`  
**Severity:** Medium  
**Category:** SQLRaw-Violation / to_sql-Mid-Pipeline  
**Description:** Date precision truncation uses `.to_sql()` to serialize temporal expression, then wraps in SQLRaw CASE/LEFT.  
**Current Code:**
```python
varchar_expr = f"REPLACE(CAST(({expr.to_sql()}) AS VARCHAR), ' ', 'T')"
return SQLRaw(f"CASE WHEN SUBSTR(...) THEN LEFT(...) END")
```
**Proposed Fix:** Use `SQLCast` + `SQLFunctionCall("REPLACE", ...)` + `SQLCase` AST nodes.  
**AC:** No `.to_sql()` in temporal precision truncation.

---

## 4. Risk Heat Map

| File | SQLRaw Violations | to_sql Violations | Silent Fallbacks | Hardcoded Logic | Total Issues |
|------|:-:|:-:|:-:|:-:|:-:|
| `fluent_functions.py` | 4 | 10 | 1 | 0 | **15** |
| `expressions/_operators.py` | 2 | 6 | 0 | 0 | **8** |
| `expressions/_query.py` | 3 | 5 | 0 | 0 | **8** |
| `expressions/_functions.py` | 0 | 7 | 0 | 0 | **7** |
| `cte_manager.py` | 0 | 2 | 0 | 0 | **2** |
| `ast_helpers.py` | 3 | 1 | 0 | 0 | **4** |
| `context.py` | 0 | 0 | 2 | 1 | **3** |
| `cte_builder.py` | 0 | 0 | 1 | 2 | **3** |
| `_temporal_intervals.py` | 0 | 0 | 0 | 1 | **1** |
| `queries.py` | 0 | 0 | 0 | 1 | **1** |
| `_property.py` | 0 | 0 | 1 | 1 | **2** |
| `patterns/temporal.py` | 2 | 1 | 0 | 0 | **3** |
| `_temporal_utils.py` | 1 | 2 | 0 | 0 | **3** |
| `column_generation.py` | 0 | 0 | 0 | 1 | **1** |
| `profile_registry.py` | 0 | 0 | 0 | 1 | **1** |
| `fhir_schema.py` | 0 | 0 | 0 | 1 | **1** |

---

## 5. Prioritized Remediation Plan

### P0 — Critical (blocks correctness/security)
1. **CQL-003**: Remove silent `get_default_profile_registry()` fallback in `context.py`
2. **CQL-004**: Remove fallback in `cte_builder.py`

### P1 — High (architectural drift)
3. **CQL-002**: Refactor `_translate_aggregate()` recursive CTE from SQLRaw → AST
4. **CQL-001**: Refactor fluent function resource subqueries from SQLRaw → AST
5. **CQL-017**: Complete Task C4 — eliminate `body_sql` template system
6. **CQL-012, CQL-013**: Fix mid-pipeline `.to_sql()` in operators
7. **CQL-014**: Fix quantity aggregate `.to_sql()` chain
8. **CQL-019, CQL-020**: Fix audit tree serialization

### P2 — Medium (maintainability)
9. **CQL-005, CQL-006, CQL-007, CQL-008**: Externalize hardcoded resource lists
10. **CQL-009, CQL-010, CQL-011**: Externalize profile name heuristics
11. **CQL-015, CQL-016, CQL-025**: Fix remaining SQLRaw wrapping patterns
12. **CQL-018**: Fix valueset URL extraction via AST introspection
13. **CQL-022, CQL-023**: Remove global singletons

### P3 — Low (cleanup)
14. **CQL-021, CQL-024**: Externalize negation patterns, document defaults

---

## 6. Positive Observations

1. **FHIRSchemaRegistry always gets `model_config`** — zero bare instantiations in production code.
2. **Parser and lexer are clean** — pure, stateless, no resource loading.
3. **Error hierarchy is well-structured** — `fhir4ds/cql/errors.py` is a good pattern.
4. **Dependency resolver is cleanly isolated** — no translator coupling.
5. **Three-layer schema architecture is correctly wired** at the top level in `translator.py`.
6. **CQL is source of truth** — no JSON configs duplicate CQL logic (status_filters.json eliminated).
7. **Functions marked with `body` (CQL AST)** use mandatory AST inlining path — only `body_sql` functions use templates.
