# QA Handoff — CQL-06 SKEPTIC (iteration 1)

## Chunk
CQL 1.5 Type Operators — Conversion Checks (CanConvertQuantity, ConvertQuantity, ConvertsToBoolean/Date/DateTime/Decimal/Long/Integer/Quantity/Ratio/String/Time).

## Method
Verified normative semantics against CQL Appendix B (Type Operators + To* sections, Table 9-E conversion matrix, Table 9-F boolean strings, Table 9-G string representations) fetched from cql.hl7.org / build.fhir.org. Probed the DuckDB UDF surface on BOTH backends (Python-supplements-only and native-extension) plus end-to-end `translate_cql` → `to_sql()` → DuckDB execution. ~130 probe cases in `/mnt/d/fhir4ds/.temp/qa/cql06_skeptic/probe1.py`.

## Verified-correct surfaces (no divergence)
- Null propagation: all 12 operators return null for null input (spec: "If the argument is null, the result is null"); CanConvert/ConvertQuantity null on either argument.
- ConvertsToBoolean: Table 9-F case-insensitive strings, numeric 1/0-only acceptance ('2'→false, 1.0→true).
- ConvertsToInteger/Long: Integer/Long range boundaries (2147483647 true / 2147483648 false at both ends), Long in-range rule, Decimal input rejected per Table 9-E ('-' entry).
- ConvertsToDecimal: 8-digit scale cap + representability; 'NaN'/'1e2'/'.5'/'1.' rejected.
- ConvertsToDate/DateTime/Time: padded formats enforced ('2024-1-1' false), leap years (2024-02-29 true, 2023-02-29 false), component ranges (25:00, 10:61, 24:00, :60 false), timezone bounds (+14:00 ok, +14:30 false), datetime-string acceptance by ToDate (time ignored per spec), any-precision datetimes.
- ConvertsToQuantity/ToQuantity: quoted UCUM units, JSON quantity/ratio objects, numeric overloads, scale/representability limits.
- ConvertsToRatio: '1:2' plain, quoted-unit ratios, malformed rejection, null-propagation; Ratio overload of ToQuantity (divide) works end-to-end.
- ConvertsToString: structural (List/Tuple/JSON) → false; temporals/quantities/numerics → true; end-to-end static gating consistent.
- ConvertQuantity/CanConvertQuantity: UCUM family compatibility (mg→g values correct: 1000mg→1g, 2.5kg→2500g, 180cm→1.8m), incompatible families null/false, case-sensitive units ('MG' is megagauss → false), calendar year→month (60 mo), null on either argument.
- Native vs Python parity: 100% across all probes (ConvertQuantity routed through native quantityConvert when extension loaded; identical JSON results).
- End-to-end translation: Long literal overflow, date/time literals, quantity literals, CanConvert(x, T) lowering — all correct.

## Issue found
- QA-001 (HIGH, OPEN): ToQuantity/ConvertsToQuantity/ConvertsToRatio reject bare calendar duration keywords (singular/plural) in the string grammar. Spec §ToQuantity: unit designator may be a "UCUM unit of measure or calendar duration keyword, singular or plural", and Table 9-G's round-trip rule (`ToString(4 days)` → `4 days`) requires ToQuantity('4 days') to parse. Actual: False/null on both backends. Root cause: `toQuantity` regex in `fhir4ds/cql/duckdb/udf/quantity.py` only accepts quoted unit designators.

## Notes for FIX
- Fix belongs in `toQuantity` (udf/quantity.py): accept a bare unit token after optional whitespace when (and only when) it is in `_CQL_CALENDAR_DURATION_UNITS` (already defined; `_is_valid_quantity_unit` already accepts these keywords, so `_format_cql_quantity` will pass through). Bare non-calendar words ('mg') must remain rejected per case-sensitive UCUM string-literal rule.
- No C++ changes needed: both backends share the Python toQuantity for this surface (verified parity after fix must hold trivially).
- Regression guard: existing test `test_cql_conversion_check_spec_boundaries_match_cpp_registration` asserts `ConvertsToQuantity('5 mg')` False — must stay false.
