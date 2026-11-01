# QA Handoff — CQL-07 HISTORIAN launch

## Probed
- Re-ran the SKEPTIC 60-case dual-backend matrix (.temp/qa/cql07_master/probe.py):
  both prior fixes intact (Decimal truncation toward zero for ToInteger/ToLong;
  patient-context singleton .value). Zero parity divergences; the 3 "FAILURES"
  printed are stale expectations inside the old probe file itself (Decimal
  object repr, unit system URIs), not implementation defects.
- Fresh Appendix-B-walkthrough probes (.temp/qa/cql07_historian2_2026_08_20/):
  ToBoolean single-letter table rows ('t','y','f','n', case variants, 'yes',
  'NO', rejects 'tru'/' true'), ToDecimal/ToLong(Boolean), ToInteger/ToLong
  range edges ('2147483648' null, Long min truncation), ToQuantity(Ratio)
  division semantics (same unit, cross unit g/mg, negative), ToRatio
  '<quantity>:<quantity>' incl. ';' and one-sided rejection, ToDate(
  DateTime-typed) == date from (incl. +05:00), ToDateTime(Date), ToTime
  precision/range/tz normalization, ToString(Decimal '#0.0#' min one
  fractional digit), ToString(Date/DateTime/Time/Ratio), ToConcept(Code,
  List<Code>, display carryover, null), leap-year and +14:00/+14:01 timezone
  boundaries, 28/29-integer-digit Decimal limits. Plus e2e
  translate_cql -> SQL -> DuckDB for 16 define shapes on both backends.
- Spec verified against CQL Appendix B via cql.hl7.org 09-b-cqlreference
  (conversion operator tables fetched and paraphrased during the session).

## Findings
- QA-001 HIGH: ToQuantity(Quantity) identity conversion returns NULL.
  Appendix B Table 9-E lists Quantity -> "the quantity itself".
  Repro (both backends, macro and e2e surfaces):
  SELECT ToQuantity(ToQuantity('5 ''mg''')) -> NULL;
  define X: ToQuantity(5 'mg') -> NULL (e2e).
  Twin invariant violated: ConvertsToQuantity(same JSON) -> true.
  Root cause: udf/quantity.py toQuantity() sends every '{'-prefixed string to
  _quantity_from_ratio_json; a Quantity JSON has no numerator/denominator so
  it returns None. Native cql::to_quantity (extensions/cql/src/cql/quantity.cpp)
  lacks the branch too (WASM fallback path).

## Verified clean (no issue)
Everything else above, including zero native-vs-python parity divergences
across ~70 fresh cases. Not-a-bug pins reconfirmed: RatioToString trailing
'.0' Decimal formatting (pinned), ToTime tz normalization drops offset
(fixture-pinned), ToQuantity(Ratio) cross-unit produces ratio-unit 'g/mg'
(consistent with quantity division), direct-SQL ToString on raw ratio JSON
passthrough (translator dispatches RatioToString correctly).

## Notes for Remediation
- ToQuantity is python-shadowed on both backends via
  _PYTHON_PREFERRED_CPP_CONFLICTS (macro -> __fhir4ds_py_toquantity), so the
  primary fix is Python-side; patch native to_quantity for lockstep if a
  rebuild is practical, else document the WASM-only gap.
- Identity must normalize/validate the JSON via is_valid_quantity_object and
  re-emit canonical form (keep value/unit/code/system), preserving calendar
  keywords.
