# Engineer Handoff — QA-103 DQM Gate Restoration (bug_fix, iteration 1)

## Outcome: RESOLVED (exit_reason CLEAN)

## Root causes (2 independent defects)

### Failure mode 1 — "Subquery returns 2 columns - expected 1" (13 of 14 measures)
The CQL-05 QA-101 fix in `fhir4ds/cql/translator/expressions/_query.py` (~line 4519, diff
hunk "Nested query source whose projection is a computed value") restructured the
placeholder-with-WHERE query-source branch and accidentally dropped the
`add_alias(alias, table_alias=alias, cte_name=...)` registration from the
fluent-function branch (`inner_query.where` path). Query-source aliases like
`(([Encounter: "Encounter Inpatient"]).isEncounterPerformed()) InpatientEncounter`
therefore kept only the earlier `ast_expr=source_expr` registration, and
`_translate_identifier` fell to the ast_expr branch, inlining the full 2-column
`(SELECT patient_id, resource FROM ...)` subquery wherever `<alias>.property` was
referenced — instead of a correlated `<alias>.resource` reference. This caused both
binder errors AND (for sites that happened to bind) silently wrong, uncorrelated
results (accuracy dropped to 8-99% on 10 measures once binder errors were cleared).

Note: the CQL-05 HISTORIAN bisect attribution to `_operators.py/_lists.py/
correlation.py/inference.py` was incorrect — a hunk-level bisect in a HEAD worktree
isolated `_query.py` hunk 12 alone as the trigger. The handoff note in the CQL-05
engineer handoff ("first version emitted a second patient_id column... removed")
describes this same site.

### Failure mode 2 — unresolved `urn:cql:code` retrieve placeholders (CMS122 et al.)
`resolve_placeholders()` in `fhir4ds/cql/translator/placeholder.py` did not traverse
`SQLSelect.order_by`, so a `Last(...)`-lowered ORDER BY still holding a
RetrievePlaceholder (e.g. `urn:cql:code:http://loinc.org|71802-3`) raised
"Unresolved retrieve placeholder" at SQL generation.

## Fixes (surgical, campaign fixes preserved)
1. `_query.py`: restore `add_alias(alias, table_alias=alias, cte_name=provisional_cte_name)`
   in the `inner_query.where` (row-shaped) branch. QA-101's value-projection branch and
   all other campaign hunks untouched.
2. `placeholder.py`: `resolve_placeholders` now resolves ORDER BY expressions
   (preserving `(expr, direction)` tuples).
3. Defensive hardening (kept — they only affect previously-invalid 2-column shapes):
   - `_property.py::_narrow_to_resource_column` also narrows explicit
     `[patient_id, resource]` projections (previously only `SELECT *`).
   - `_core.py::_translate_identifier` narrows resource-row ast_expr subqueries in
     SCALAR usage before returning.
   - `_temporal_intervals.py::_ensure_resource_to_interval` treats `[patient_id, resource]`
     as row shape (not a computed value projection) and narrows before fhirpath calls.

## Validation
- DQM: 47/47 measures, 100% accuracy (conformance/reports/dqm_report.json)
- ViewDef 144/144; FHIRPath R4 935/935; CQL 1706/1706 (master gate 2832/2832)
- Campaign regression: test_structural_type_parity 19/19; test_logical_parity,
  test_temporal_complex_parity, test_clinical_type_parity, test_cql01_primitive_types
  (172 passed combined); test_v2_expressions 147/147
- No commits made (per constraints).
