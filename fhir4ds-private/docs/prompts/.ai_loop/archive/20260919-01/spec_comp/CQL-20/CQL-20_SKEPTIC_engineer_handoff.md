# Engineer Handoff — CQL-20 Aggregate Functions (SKEPTIC, iteration 1)

All six QA issues fixed at root cause; zero workaround shims; translator-only
(binaries unchanged: cql 3e7d4167143e01907fdd8561db43b7d7, fhirpath
57d0634b6ee6eddee9fc06a1355bef5a, repo bundle == site-packages).

## Files changed
- `fhir4ds/cql/translator/expressions/_functions.py`
  - NEW `_translate_list_aggregate_dispatch`: single list-semantics lowering for
    Count/Mode/Min/Max/Sum/Avg/Product/statistical family over any SQL
    expression that evaluates to the element list (Quantity unit-aware, exact
    typed Sum/Product widths, cqlDivide exact Avg, DOUBLE+DECIMAL(38,8)
    statistical, empty → null).
  - NEW `_element_rows_define_list`: per-patient element LIST materialization
    for element-rows define CTEs.
  - Identifier branch: rows-define (PATIENT_MULTI_VALUE, or PATIENT_SCALAR
    List<...>-typed non-stored-list) aggregates now materialize/inline+coerce;
    inline path is gated OFF for CTE-backed sources (they carry no patient
    correlation — cross-patient leak caught during testing).
  - stored-list defines: statistical family now dispatches (previously fell
    through).
  - Query branch: statically-Quantity-returning queries route through the
    unit-aware quantity helpers.
  - Mode over dynamic multi-valued Properties: fhirpath_text → from_json list
    promotion + CQLListMode.
  - `_FHIR_TO_CQL_TYPE_NAMES` canonicalization in `_type_spec_name` +
    `_from_cql_type` (dateTime/instant/... → DateTime/...).
  - Product integral typing (literal path) per CQL-01 Sum doctrine.
  - `_translate_quantity_list_aggregate(force=)`; dynamic quantity statistical
    aggregates use a hoisted derived-table shape (DuckDB forbids subqueries in
    lambda bodies).
- `fhir4ds/cql/translator/cte_manager.py`
  - `_wrap_definition_cte` UNKNOWN branch guard: scalar aggregate subqueries
    and single-column selects over derived tables keep the outer `_pt`
    correlation (fixes AllTrue/AnyTrue-over-retrieve-query self-referential
    `_agg` SQL). NEW `_is_scalar_aggregate_select` + `_from_is_derived`.
- Tests: `fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py`
  (+21 CQL-20 end-to-end population tests, py/cpp/no-python parity, plus
  Product Integer typing and dateTime-cast Min/Max).

## Validation
- Reproducers: `.temp/qa/cql20agg_skeptic_probe1/3.py` — all probes green.
- aggregate parity 30/30; list part1+part2 74/74; test_v2_expressions 147/147.
- Master gate (final tree): 2832/2832 — ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47/47 (100%).

## Terminal classification
QA-001..QA-006 RESOLVED (reproducer + regression test + gate). GeometricMean
over List<Quantity> rejection and GeometricMean(negatives)→null logged in
AGENTS.md NOT A BUG Registry (spec has no Quantity overload; ln() convention).
