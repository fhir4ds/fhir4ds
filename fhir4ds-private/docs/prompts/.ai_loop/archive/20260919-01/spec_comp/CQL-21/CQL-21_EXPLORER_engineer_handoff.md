# Engineer Handoff — CQL-21 EXPLORER FIX (iteration 1), QA-001..003

All three open issues reproduced, fixed at root cause, and verified on BOTH
engines (Python fallback + native C++, plus focused and master-gate validation).

## QA-001 (HIGH, RESOLVED/VERIFIED) — Equal on retrieved code vs literal always False
- **Root cause**: the `=` dispatch only had `_translate_static_clinical_equality`
  (both operands static). A dynamic property/query operand fell through to a raw
  SQL comparison of the CodeableConcept JSON against the literal Code JSON —
  structurally never equal. `~` had a full dynamic extraction path, so the two
  operators were asymmetric (probe: matched components gave `~`→True, `=`→False).
- **Fix**: `_translate_dynamic_code_equality` + `_resolve_code_ref_for_dynamic_equality`
  in `fhir4ds/cql/translator/expressions/_operators.py`, hooked after the static
  clinical-equality attempt. New Python UDF `coding_matches_exact(json, path,
  system, code, display, version)` in `udf/valueset.py` (registered alongside
  `coding_matches`) extracts the Coding and applies the Authors-Guide exact-match
  semantics: code+system matched with the same alias normalization as
  `coding_matches`, and display/version must match exactly — an element absent
  from the literal must be absent from the coding (a value on one side only is
  not an exact match). `!=` wraps in NOT; null retrieved value → SQL null.
- Python-only UDF (same deployment surface as the existing `coding_matches`,
  which the native engine also sources from Python supplements).

## QA-002 (MEDIUM, RESOLVED/VERIFIED) — Sum/Median silently dropped uncertainty
- **Root cause**: literal-list Sum/Avg/Median lowering was not uncertainty-aware
  (CQL-21 HISTORIAN had covered Min/Max only); DuckDB list aggregates over the
  §22.21 VARCHAR intervals silently dropped them and returned a wrong crisp value.
- **Fix**: new `cqlUncertainListSum` UDF — Python `udf/datetime.py` (sums
  [Σ lows, Σ highs], nulls ignored, empty/all-null → null) AND native
  `CqlUncertainListSumFunc` in `extensions/cql/src/cql_extension.cpp`
  (registered `cqlUncertainListSum`). Translator routing in
  `_functions.py` list-aggregate branch: literal lists with any
  uncertainty-capable element → Sum routes to `cqlUncertainListSum`;
  Avg/Median return null (not representable in the integer-bounded §22.21
  form; honest null instead of a wrong crisp number).
- Native extension rebuilt (cmake --build build/release), deployed to repo
  bundle + ~/.local site-packages, ~/.duckdb cache cleared. md5
  `c5b22d58310c1eb7bafa17ce7877f989` identical across build/bundle/site-packages.

## QA-003 (MEDIUM, RESOLVED/VERIFIED) — Average() catalog error
- **Root cause**: CQL keyword `Average` missing from the pre-translate registry
  (`expressions/__init__.py`) and from `_CQL_AGG_TO_SQL` keys (`avg`), so a raw
  `Average(...)` SQL call leaked and failed with a DuckDB Catalog error.
- **Fix**: registered `"average"` in the pre-translate tuple; `_translate_aggregate_pre`
  normalizes name to `"Avg"` so every downstream map/dispatcher hits the existing
  exact-Decimal avg lowering. `Average({1,2,3})` → 2.00000000, `Average({0.1,0.2})`
  → 0.15000000 (exact).

## QA-004 (LOW, INTENDED) — population null→False collapse for unloaded valuesets;
documented filter-based define-boundary behavior; direct UDF is spec-correct NULL.

## Regression test
`fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py::
test_cql_clinical_explorer_dynamic_code_equal_and_aggregates_regression`
— 7 assertions across py + cpp engines (18/18 in file).

## Validation
- Focused: test_clinical_operator_parity 18/18; test_clinical_type_parity +
  test_v2_expressions 171/171.
- Master gate `conformance/scripts/run_all.py` on FINAL tree:
  ViewDef 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832.

## Files changed
- fhir4ds/cql/translator/expressions/_operators.py (dynamic code equality)
- fhir4ds/cql/translator/expressions/_functions.py (Average normalization,
  uncertain Sum routing)
- fhir4ds/cql/translator/expressions/__init__.py (register 'average')
- fhir4ds/cql/duckdb/udf/valueset.py (codingMatchesExact)
- fhir4ds/cql/duckdb/udf/datetime.py (cqlUncertainListSum)
- extensions/cql/src/cql_extension.cpp (native cqlUncertainListSum) + rebuilt
  binary deployed (fhir4ds/cql/duckdb/extensions/cql.duckdb_extension)
- test_clinical_operator_parity.py (regression test)
