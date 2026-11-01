# Engineer Handoff — CQL-17 EXPLORER (3rd launch, 2026-08-22)

## QA-001 (HIGH, SPEC_VIOLATION) — RESOLVED
Root cause: translator arithmetic dispatch in
`fhir4ds/cql/translator/expressions/_operators.py`:
1. `_is_cql_date_expression` (in `_temporal_utils.py`) returns True for ANY
   `start of` / `end of` unary, so `(start of Interval[1, 5]) + 1` matched the
   "CQL Date/DateTime +/- Integer => year-unit quantity" path and lowered to
   `dateAddQuantity(CAST(intervalStart(...) AS VARCHAR), {1 'year'})` → NULL.
2. Decimal / width-of / Size operands fell through to raw SQL
   `'+'(VARCHAR, DECIMAL)` / `'*'(VARCHAR, INTEGER)` → DuckDB binder errors.

Fix (spec: CQL 1.5 §19.19 Start / §19.15 End / §19.22 Point From / §19.25
Width / §19.18 Size return the interval's point type; §9 Add/Subtract are
numeric for numeric points):
- New helper `TemporalComparisonMixin._interval_scalar_point_kind(node)` in
  `_temporal_comparisons.py`: classifies `start of` / `end of` / `point from` /
  `width of` (UnaryExpression) and `Size` (FunctionRef) operands via the
  existing `_numeric_interval_point_kind` interval classification →
  "numeric" / "quantity" / None (temporal untouched).
- Gates in `_operators.py` for `+`/`-` and `*`/`/`: numeric kind →
  DECIMAL(38,10) binary arithmetic (mirrors `_numeric_point_compare`);
  quantity kind → quantity_add/subtract/multiply/divide with
  `_quantity_operand_for_arithmetic` on the interval-scalar side.

Verified: `(start of Interval[1,5]) + 1` → 2; `(end of ...) - 1` → 4;
`(start of Interval[1.5,5]) + 1` → 2.5; `(width of Interval[1,5]) + 1` → 5;
`Size(Interval[1,5]) * 2` → 10; `(point from Interval[4,4]) + 1` → 5;
`(start of Interval[null as Integer,5]) + 1` → -2147483647 (int32 sentinel
doctrine); reversed operand order; `(start of Interval[1 'g',3 'g']) + 1 'g'`
→ 2 'g'; `(width ...) - 1 'g'` → 1 'g'; `(end ...) / 2` → 1.5 'g'; temporal
`(start of Interval[@2024-01-01, ...]) + 1 day` unchanged → 2024-01-02.
Same results on python, native, and no-python engines.

Regression test:
`test_interval_part3_parity.py::test_cql_interval_part3_explorer3_interval_scalar_arithmetic_numeric_quantity`
(12 cases × 3 engines). Full probe (.temp/qa/cql17_explorer3_2026_08_22/
probe.py, 69 assertions × 3 engines) PASS.

## QA-002 (MEDIUM, SPEC_VIOLATION) — reclassified INTENDED
QA expected width/size overflow beyond the Integer point-type range to null
per the §9 overflow clause. This conflicts with the pinned doctrine
`test_cql_interval_part3_explorer_long_minmax_width_size_exact_per_spec`
(2026-07-02 EXPLORER): Long MIN..MAX width/size MUST return exact 2^64-1 /
2^64, "per spec", reference-engine-aligned. Fixtures/precedent outrank my
prose reading; exact computation is the established engine contract.
Added to NOT A BUG registry with the tension noted.

## QA-003 (LOW) — UNCONFIRMED (terminal)
point-from null-on-non-unit documented DuckDB-surface boundary (docstring +
prior launches' pinned expectations); flagged for human confirmation only.

## Files changed
- fhir4ds/cql/translator/expressions/_temporal_comparisons.py (helper)
- fhir4ds/cql/translator/expressions/_operators.py (+,-,*,/ gates)
- fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py (test)

## Validation
- Focused: part3 parity 11/11; part2 + v2 expressions + overlap decomposition
  + interval UDFs 227/227.
- Master gate (fresh, final tree): see architect handoff / final report.
- Binaries unchanged (translator-only fix): cql.duckdb_extension md5
  3e7d4167143e01907fdd8561db43b7d7 (repo bundle == site-packages);
  fhirpath site-packages 57d0634b6ee6eddee9fc06a1355bef5a.
