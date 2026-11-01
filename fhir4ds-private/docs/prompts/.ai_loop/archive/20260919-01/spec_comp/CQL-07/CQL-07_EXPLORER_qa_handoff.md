# QA Handoff — CQL-07 EXPLORER launch (iteration 1)

## Probed (all dual-engine: python-only vs cpp-registered; zero parity divergences)
Workspace: `.temp/qa/cql07_explorer_2026_08_20/` (probe1–probe4).

- Conversion chains/round-trips: ToInteger(ToDecimal(x)) incl. ±truncation,
  ToString→ToQuantity→ToString stability ('5 mg' -> "5 'mg'"), ToQuantity(ToDecimal)
  -> "2.75 '1'", str→DateTime→Date→ToString, ToQuantity(Quantity) identity intact
  (prior HISTORIAN fix verified).
- Extremes: maximum/minimum Integer/Long/Decimal/Date/DateTime/Time through every
  applicable To* and ToString (all correct, incl. 99999999999999999999.99999999,
  ±0 (ToString(-0.0)='0.0'), ToInteger/ToLong overflow→null, ToBoolean('0')=false,
  ToBoolean('1')=true).
- ToBoolean full Appendix B Table 9-F: true/t/yes/y/1/false/f/no/n/0, case variants
  ('Y','Yes','TRUE') — implementation matches the case-insensitive table exactly.
- ToDateTime(Date) at year/month/day precision (partial precision preserved);
  ToDate(DateTime) incl. offset; ToString temporals with +05:30/-08:00 offsets and
  1–3 fractional digits (offset preserved, round-trippable).
- Sub-millisecond literals (4/6 fractional digits) → null on both engines. Verified
  against spec: DateTime/Time support millisecond max precision; logged QA-001 LOW
  INTENDED (strict rejection, consistent with pinned strict-digit-count doctrine).
- ToConcept: single Code display carryover to top-level Concept.display; List<Code>
  input keeps per-code displays and no top display (spec-exact); null→null;
  null-in-list→null.
- ToRatio with units (mg/mL) and RatioToString; ToQuantity(Ratio) division (5 mg /
  2.5 mg -> 2.0 '1').
- Query pipelines e2e via `translate_library_to_population_sql` over `resources`:
  `[Observation] O where ToDecimal((O.value as FHIR.string).value) > 10.0
  return ToInteger(...)` returns [42] correctly; Quantity-valued `.value` accessor
  path works (12.50000000); `exists([Observation])` true.
- Define aliases referenced multiple times (AliasedYear used by two downstream
  defines) — correct (1980/1981/1979 for birthDate 1980-06-15).
- To* over null literals and empty strings → null on both engines.

## Findings
- QA-001 LOW (INTENDED): sub-millisecond fractional-second literals rejected (null)
  — spec-consistent strictness, pinned. No other issues: zero non-terminal
  CRITICAL/HIGH/MEDIUM findings.

## Spec verification
CQL 1.5 Appendix B fetched and paraphrased during the session (ToBoolean Table 9-F,
ToDateTime/ToTime millisecond precision, ToString Table 9-G, ToConcept display
semantics, Table 9-E conversion matrix).

## Notes
- Probe harness lesson: e2e execution must use
  `CQLToSQLTranslator.translate_library_to_population_sql` (defines referencing
  patient context need the `resources` table shape), not raw `to_sql()` SELECTs.
  Raw translate_cql returns Dict[str, SQLExpression].
