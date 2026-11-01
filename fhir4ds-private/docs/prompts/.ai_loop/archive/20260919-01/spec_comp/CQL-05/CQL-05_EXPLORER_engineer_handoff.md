# Engineer Handoff — CQL-05 EXPLORER iteration 1 (2026-08-20)

## Fixed (all RESOLVED, reproducer + gate verified)

- **QA-104 HIGH** — Strict casts in arithmetic produced non-executable SQL
  (`TRY(...error()...)`, DuckDB "TRY can not be used in combination with a
  volatile function"). Root cause: `_contains_function_call` skipped SQLCase
  nodes. Fix: recurse into when_clauses/else_clause/operand.
  File: `fhir4ds/cql/translator/expressions/_operators.py`.
- **QA-105 HIGH** — Element access over retrieve-bound define aliases broken:
  `First(ObsList).id` → null, `ObsList[0].status` / `ObsList.first().id` →
  scalar-subquery binder errors. Fixes: First/Last Identifier-arg dispatch +
  `_translate_first_last_over_cte` / `_definition_resource_cte_name`
  (`_functions.py`); `_definition_resource_rows_list` used by the indexer and
  method-form first/last/singletonfrom (`_lists.py`). Known limitation:
  forward-referenced RESOURCE_ROWS defines aren't detected (definition_meta is
  populated in definition order).
- **QA-106 MEDIUM** — Array/backbone property access on singleton resource
  expressions returned 0/null: `Count(First([Observation]).contained)` = 0.
  Root cause: `fhirpath_text` returns only the first element of multi-valued
  paths; `Count(fhirpath_text(...))` mapped to `json_array_length` over scalar
  text (always 0/NULL). Fix: `_coerce_fhirpath_text_to_list` swaps in the
  list-returning `fhirpath` UDF for Count (array_length) / First / Last.
  File: `fhir4ds/cql/translator/expressions/_functions.py`.

## Regression + recovery

- First attempt at QA-105 (aggregating ALL LIST-usage definition lookups in
  `_core.py`) regressed DQM 47 → 28 (scalar-subquery flattening unwraps `list()`
  aggregates next to patient_id columns). Reverted and replaced with localized
  consumer-site fixes; full gate re-verified **2832/2832**
  (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`: 22/22
  pass with three new regression tests (strict cast in arithmetic; element
  access over retrieve-bound aliases; array properties on singletons).

## Deferred

- **QA-107 MEDIUM (DEFERRED)** — list-literal query sources (`({1,2,3}) X return
  all X`) produce row subqueries and PATIENT_SCALAR misclassification:
  `Count(L)` = 1 (expect 3), `Sum` over filtered variant → binder error.
  Requires net-new row-shape classification for list-typed query defines in the
  `_translate_query` region flagged by the Architect Drift Log; out of the
  CQL-05 type-operator chunk. Recommend a dedicated query-source chunk launch.

## Tests / artifacts

- Regression tests: `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`
  (3 new tests appended).
- Reproducers/probes: `/mnt/d/fhir4ds/.temp/qa/cql05_explorer2_2026_08_20/`.
