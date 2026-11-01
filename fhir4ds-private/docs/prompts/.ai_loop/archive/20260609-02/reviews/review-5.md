# Code Review Findings

Milestone review for the first 5 per-chunk spec-compliance chunks (`FP-01` through `FP-05`).

## Findings

### REV-001 — HIGH — Python fallback `all(criteria)` leaks `$index`

`fhir4ds/fhirpath/engine/invocations/existence.py:51-55` sets `ctx["$index"]` in `all_macro()` without saving and restoring the previous value. This creates native/fallback drift at the public DuckDB UDF surface when the C++ extension is unavailable.

Reproducer:

```sql
-- resource: {"resourceType":"Patient","a":[1,2]}
SELECT fhirpath(?::JSON, 'a.all($this > 0) | $index');
```

Observed during review:

- Native C++: `['true']`
- Forced Python fallback: `['true', '1']`

Existing FP-03 tests cover `$index` inside criteria, but not cleanup after `all(criteria)`.

### REV-002 — MEDIUM — Native `where(criteria)` leaks `defineVariable` state

`extensions/fhirpath/src/fhirpath/evaluator.cpp:772-792` saves/restores `chain_defined_vars_` and `index_context_` in `evalWhere()`, but not `defined_variables_`. That violates the loop-scope invariant used elsewhere, such as `evalExists()`, and lets criteria-local variables escape into later chained expressions.

Reproducer:

```sql
-- resource: {"resourceType":"Patient","a":[1,2]}
SELECT fhirpath(?::JSON, 'a.where(defineVariable(''leak'', $this).exists()).select(%leak)');
```

Observed during review:

- Native C++: `['2', '2']`

The variable defined inside `where()` criteria should not become ambient state for the subsequent `select()`.

## Validation Performed

- Focused milestone parity tests: `16 passed`
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py`
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py`
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py`
- Native extension artifact freshness check:
  - build artifact and packaged `fhirpath.duckdb_extension` SHA-256 match: `f872569476274722e322eea301d018904159598119409ecbf564096a02be7ec7`
- Targeted repro probes confirmed both findings above.

## Scope Notes

No broad refactors or source fixes were made during this review. The reviewed milestone areas were literal/operator/existence/filtering/subsetting/combining changes, with emphasis on native C++ vs Python fallback parity, strict-core vs DuckDB wrapper boundaries, scope isolation, and bundled extension freshness.
