# Engineer Handoff — CQL-05 Structural Type Operators (iteration 1)

## Fixed (all RESOLVED, reproducer + regression tests + baseline 2832/2832)

### QA-001 (HIGH) — First/Last/`singleton from` over bare retrieves
Root cause: First/Last dispatch and `_apply_singleton_from` translated a bare Retrieve in LIST
usage to a CTE identifier used directly inside LIST_EXTRACT (no FROM/join) → Binder Error.
Fix:
- `fhir4ds/cql/translator/expressions/_functions.py`: new
  `_translate_first_last_over_retrieve()` — per-patient correlated subquery
  `(SELECT list_extract(list(_agg_src.resource), ±1) FROM <cte> _agg_src WHERE patient_id = _pt.patient_id)`,
  wired into the First/Last dispatch before the Query branch.
- `fhir4ds/cql/translator/expressions/_operators.py`: `singleton from [X]` wraps the retrieve
  placeholder in a `SELECT *` row subquery so `_apply_singleton_from`'s cardinality branch
  applies with patient correlation.

### QA-002 (HIGH) — per-element alias binding over Children()/Descendants()
Root cause: query sources over cqlChildren/cqlDescendants lists never UNNESTed, so the
where-clause alias bound to the whole VARCHAR[] list (ltrim(VARCHAR[]) binder errors, wrong False).
Fix (expressions/_query.py + translator/correlation.py):
- Structural-source query handler: UNNEST per item with `_lt_<alias>` binding (mirrors the
  backbone-array pattern), used for WHERE/RETURN.
- `_alias_is_element_value()`: element-value aliases (list literals, Children/Descendants) are
  no longer qualified with `.resource` in is-checks.
- `_cql_typed_value_type_check()` recognizes `_lt_` structural-item aliases and reads the
  `__fhir4ds_cql_type` tag.
- correlation.py: no patient_id correlation injected into FROM-clause-less unnest subqueries.

### QA-003 (MEDIUM) — FHIR string-family primitives rejected by `is String`
Root cause: runtime type().name reports FHIR primitives (code/id/uri/...) but is-checks accepted
only the single canonical name; also the static System-type shortcut and the clinical Code routing
both mis-handled FHIR-qualified targets.
Fix: externalized data-driven map `FHIR_TYPE_TO_CQL_TYPE` + `fhir_type_names_for_cql_type()` in
`fhir4ds/cql/translator/inference.py` (was an inline dict); `_fhirpath_primitive_type_check` and
`_fhirpath_type_name_check` accept the family for unqualified/System targets only; static shortcut
and `_clinical_json_type_check` skipped when target is FHIR-qualified (FHIR.code ≠ CQL Code).

### QA-004 (MEDIUM) — `exists ({1,2} N where ...)` invalid SQL
Root cause: `_translate_exists_expression`'s list-typed branch emitted `list_count(<row subquery>)`
(no such scalar function; multi-row scalar subquery) and the is-check qualified alias N with .resource.
Fix: `fhir4ds/cql/translator/expressions/_lists.py` — row-subquery sources now lower to EXISTS;
alias resolution fix shared with QA-002.

## Deferred
- QA-005 (MEDIUM, DEFERRED): value comparisons (`C > 3`) over tagged Children/Descendants items
  compare the JSON tag wrapper as VARCHAR. Needs per-element unwrap in comparison lowering
  (net-new machinery, wide regression surface). is/as/Convert are covered.

## Files changed
- fhir4ds/cql/translator/expressions/_functions.py
- fhir4ds/cql/translator/expressions/_operators.py
- fhir4ds/cql/translator/expressions/_query.py
- fhir4ds/cql/translator/expressions/_lists.py
- fhir4ds/cql/translator/inference.py
- fhir4ds/cql/translator/correlation.py
- fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py (+3 tests, 17 total)

## Validation
- test_structural_type_parity.py: 17/17 (native C++ and forced-Python paths, parity asserted)
- CQL unit tests: 1612 passed
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  OVERALL 2832/2832 — no regression.
