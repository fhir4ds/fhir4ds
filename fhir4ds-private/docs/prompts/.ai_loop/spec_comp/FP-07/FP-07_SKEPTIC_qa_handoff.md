# QA Handoff — FP-07 SKEPTIC (FHIRPath §5.5.4-§5.5.6 Date/DateTime/Decimal Conversion)

## Verdict: CLEAN — zero defects (76 fresh dual-path cases, 0 flags)

## Probes
- probe1 (42 cases): toDate/toDateTime lexical grammar (partial precisions,
  T-marker promotion, tz-suffixed forms, invalid calendar dates empty);
  convertsTo* mirrors; toDecimal exact-Decimal ('0.1'+0.2=0.3 true), Boolean
  true/false → 1.0/0.0, rejection of 'abc'/'1.5.2'/'1e3'/whitespace/' 1.5';
  Long-suffix interop ('42L'/'-5L' ok, '5.5L'/'5l' rejected); typed inputs
  (Integer→Decimal ok; @2015 / @T14:30 / Quantity → empty).
- probe2 (34 cases): 28-digit decimal precision exact; whitespace rejection on
  dates+decimals; tz offset boundaries (+/-14:00 valid; +14:01/+99:00/+0900
  empty); multi-item/empty propagation (row-resilient both engines);
  post-conversion equality ('2015-02-04'.toDate() = @2015-02-04 true; toDateTime
  T-marker forms); leap-year convertsToDate (2016/2000 true, 2015/1900 false);
  time component ranges (24:00/12:60/30:60 → false).

## Evidence
Scripts: .temp/qa/speccomp2/fp07_skeptic_probe{1,2}.py
