# QA Handoff — CQL-01, iteration 1, HISTORIAN

## Method
Exhaustive section walkthrough of CQL 1.5 09-b-cqlreference.md (Types:
Any/Boolean/Decimal/Long/Integer/String; Type Operators incl. Table 9-E
conversions, To* family, Table 9-G ToString representations; Aggregate/Sum)
verified against execution (translate_cql → to_sql → DuckDB with register_cql).
~140 probes across two batches plus targeted DuckDB-native probes. Local spec
source: /mnt/d/gemini/training_data/cql-master/input/pages/.

## Re-verification of prior SKEPTIC fixes
All 6 prior fixes hold: test_cql01_primitive_types.py 20/20 pass; overflow
guards (max Long * 2 → null, -(-923372036854775808L) → null), decimal extent
literals, ToDecimal scale-rounding (both literal and string, incl. negative
half-up), Truncate → Integer, CanConvert lowering all confirmed live.

## Verified-correct (no action)
- Full String escape table (\' \" \r \n \t \f \\ \uXXXX) incl. BMP unicode.
- Any: `5 is Integer` T / `'5' is Integer` F / `5 is Any` T / `null is Integer` F;
  `as` returns null on runtime-type mismatch; `cast as` throws on mismatch;
  `cast 5 as Integer` OK.
- Table 9-G ToString for Boolean/Integer/Long/Decimal incl. round-trip
  (ToInteger(ToString(13))=13 etc., ToString(maximum Decimal) exact).
- To* family: spec examples ToDecimal('-0.1')/'(+-0.1)'→null, ToLong('-1')/
  ('one')→null, ToInteger('-1')/('one')→null, ToInteger(2147483648L)→null,
  ToDecimal(true)=1.0, '+1.5' accepted, '.5'/'1.'/''/' 1.5' rejected, '007'→7.
- Table 9-E explicit conversions among primitives incl. convert true to
  Integer=1, convert 5L to Integer, convert 0.1 to String.
- Literals out of range (2147483648, 9223372036854775808L, >20-int-digit
  Decimal) raise translation ValueError — intended strict-literal policy.
- Boolean 3-valued logic (and/or/xor/not with null), cross-type equality → null,
  equivalent semantics (null ~ null true, 1.0 ~ 1 true).
- div/mod by zero → null (Integer, Long, Decimal); mod sign = dividend.
- Sum null handling (all-null → null, null list → null); quantity Sum fine.

## Issues (see evolution.json)
- QA-001 HIGH: `/` is DOUBLE division, not Decimal — spec's own example
  `9.9 / 3.0` → 3.3000000000000003 (spec: 3.3); `1 / 3 = 0.33333333` → False.
- QA-002 HIGH: list Sum computed in DOUBLE — Sum({0.1,0.2}) = 0.30000000000000004;
  Sum({maximum Long, 1}) → 9.223372036854776e+18 (silent precision loss, no
  overflow null); Sum(List<Integer>/List<Long>) must return Integer/Long.
- QA-003 MEDIUM: Avg/Median/etc. return DOUBLE artifacts (Avg({0.1,0.2}) →
  0.15000000000000002; spec result type Decimal).

## Notes for FIX
- QA-002/QA-003 root: `_translate_function` list-aggregate branch in
  fhir4ds/cql/translator/expressions/_functions.py (~line 1925) wraps every
  numeric list aggregate in list_transform(TRY_CAST _v AS DOUBLE). DuckDB
  native list_aggregate('sum') is exact (HUGEINT for integral, DECIMAL(38,8)
  for decimal lists) — drop the DOUBLE cast for sum and TRY_CAST the result to
  the spec result type (INTEGER/BIGINT for Integer/Long element lists,
  DECIMAL(38,8) for Decimal). Element type inference: ListExpression element
  types, definition_meta cql_type List<T>.
- QA-001 root: division lowering in translator/expressions/_operators.py
  promotes to DOUBLE. Spec: Decimal division at implementation scale 8.
  Fix must keep the conformance gate green (1706 CQL) — official divide
  fixtures expect values like 3.3 which an 8-scale Decimal matches exactly.
