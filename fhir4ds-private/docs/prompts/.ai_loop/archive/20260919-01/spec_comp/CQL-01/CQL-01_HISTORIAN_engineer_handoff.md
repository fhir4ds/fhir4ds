# Engineer Handoff — CQL-01, iteration 1 (HISTORIAN)

All 3 QA issues RESOLVED at root cause; regression tests added
(fhir4ds/cql/tests/unit/test_cql01_primitive_types.py, now 40 tests).

## Fixes
- QA-001 (`/` DOUBLE division): new exact `cqlDivide` Python UDF registered
  in fhir4ds/cql/duckdb/macros/math.py (VARCHAR operands, DECIMAL(38,8)
  return, 60-digit Decimal context, ROUND_HALF_UP quantize to scale 8, null
  on zero divisor / non-numeric / out-of-range). The generic `/` fall-through
  in translator/expressions/_operators.py (~line 7060) now emits
  cqlDivide(CAST a AS VARCHAR, CAST b AS VARCHAR). Spec: 9.9 / 3.0 →
  3.30000000; 1/3 = 0.33333333 → true.
- QA-002 (Sum DOUBLE list transform): the list-aggregate branch in
  translator/expressions/_functions.py no longer DOUBLE-casts statically
  numeric Sum sources; DuckDB native list sum is exact (HUGEINT integral /
  DECIMAL(38,8) decimal). Integral element lists TRY_CAST to INTEGER/BIGINT
  → overflow null (Sum({maximum Long, 1}) → null). Element-type inference
  extended: `_function_return_type` now resolves `maximum/minimum T`
  FunctionRefs (NamedTypeSpecifier or bare Identifier arg).
- QA-003 (Avg/Median Decimal typing): Avg = cqlDivide(exact_sum, non-null
  count) — exact at scale 8. Median/StdDev/Variance/Population*/Product
  results wrapped TRY_CAST AS DECIMAL(38,8) per CQL §20 result types.
  Residual: extreme-value low-order digits for median/stddev family remain
  DOUBLE-precision (DuckDB has no exact decimal list median); documented.
- Recovery-gate event (root-caused, not blind): first attempt regressed 7
  DQM measures — Binder "Cannot mix VARCHAR and DECIMAL(38,8) in COALESCE"
  (Coalesce of dynamic FHIR VARCHAR values with the now-DECIMAL division
  result, e.g. CumulativeMedicationDuration). Diagnosed from the generated
  tests/output/sql/CMS122.sql. Fixed by extending `_translate_coalesce`'s
  `_is_numeric_expr` to recognize cqlDivide and DECIMAL casts so mixed
  dynamic Coalesce arguments normalize to DOUBLE (matching their previous
  dynamic typing).

## Test updates
- fhir4ds/cql/tests/unit/test_v2_expressions.py: 6 structural tests updated
  to the new spec-driven lowerings (division → cqlDivide; statistical
  aggregates → TRY_CAST AS DECIMAL(38,8) wrapper).

## Validation
- Chunk tests: 40/40.
- CQL unit+integration: 4906 passed, 4 skipped.
- Full conformance gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47). Baseline held after the recovery-gate fix.
