# Engineer Handoff — CQL-10 SKEPTIC iteration 1 (2026-08-21)

All five QA issues RESOLVED. Fixes verified on BOTH the Python fallback and
the rebuilt C++ extension (md5 `774abbac349f6e6a755f7317ba4a4978`, deployed to
`fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` and site-packages;
`~/.duckdb` cache dirs empty so no stale-binary risk).

## Fixes

1. QA-001 High/LowBoundary Decimal precision — implemented the HL7 reference
   semantics (BigDecimal: append `99999999`/`00000000` then `setScale(precision,
   DOWN)`). `HighBoundary(1.587,2)`=1.58, `LowBoundary(1.587,2)`=1.58,
   `HighBoundary(1.587,8)`=1.58799999 (official fixture unchanged). Files:
   `fhir4ds/cql/duckdb/udf/math.py` (`_decimal_boundary_text` rewritten; numeric
   branches of `highBoundary`/`lowBoundary` unified onto it) and
   `extensions/cql/src/cql/boundary.cpp` (new `decimal_boundary_text` helper used
   by both `high_boundary`/`low_boundary` numeric paths).
2. QA-002 Ceiling/Floor Integer typing/extent — `TRY_CAST(CEIL/FLOOR(x) AS
   INTEGER)` in the translator (`expressions/__init__.py` registry replaces bare
   renames; `functions.py` `_translate_math_func`), `TRY_CAST(... AS INTEGER)`
   macros in `macros/math.py`, and Integer-extent guards in Python
   `mathCeiling`/`mathFloor` and C++ `math_ceiling`/`math_floor`.
   `Ceiling(2147483647.05)`→null, `Floor(2147483648.2)`→null,
   `Ceiling(2147483646.05)`→2147483647.
3. QA-003 Mixed Integer+Long Add — `_operators.py` binary-op lowering now casts
   statically-integral operands to BIGINT when any operand is Long (CQL implicit
   Integer→Long conversion). `1 + 2147483647L` → 2147483648 (both backends);
   Integer+Integer and Long+Long overflow-to-null unchanged.
4. QA-004 Abs typed overflow — new `_translate_abs_pre` pre-translate hook with
   `_static_integral_expr_type` (literals / unary ± / binary +−×) narrows Abs to
   INTEGER/BIGINT via TRY_CAST: `Abs(-2147483648 - 0)` → null;
   `Abs(-9223372036854775807L - 1L)` → null; `Abs(-2147483647)` → 2147483647.
   Existing four literal-shape guards retained (now redundant but harmless).
5. QA-005 Exp/Ln/Log Decimal typing — translator lowers to
   `TRY_CAST(... AS DECIMAL(38,8))` (`_functions.py` `_translate_exp/_translate_ln/
   _translate_log`) and SQL macros return DECIMAL(38,8) (`macros/math.py`).
   `Exp(1)`→2.71828183, `Log(16,2)`→4.00000000. Official fixtures wrap in
   `Round(Exp(1),8)` so conformance unaffected.

Note on spec authority: the v2 spec prose example `HighBoundary(1.587,2)//1.59`
conflicts with the HL7 Java/Kotlin reference implementation (1.58). Per the
project doctrine "fixtures/reference implementation outrank prose", the
reference semantics (1.58) were implemented.

## Validation

- Focused regression: new test
  `test_cql_arithmetic_spec_compliance_boundaries_typing_and_promotion` in
  `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py`;
  file: 8/8 passed.
- Adjacent integration: arithmetic part2 + temporal complex parity 34/34.
- Full conformance: **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47)
  — baseline holds exactly.
- Full `pytest fhir4ds/cql` tree: running (results appended to architect phase
  verification).

No new issues discovered during remediation.
