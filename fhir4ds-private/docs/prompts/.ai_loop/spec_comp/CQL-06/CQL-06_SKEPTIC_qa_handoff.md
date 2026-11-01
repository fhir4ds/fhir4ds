# QA Handoff — CQL-06 SKEPTIC (ConvertsTo* family + CanConvert/ConvertQuantity)

## Verdict: CLEAN — 28/28 fresh dual-path cases, 0 diffs

ConvertsToBoolean ('true'/'YES'/'t' True, 'vrai' False); ConvertsToInteger ('42' True,
'4.0' False decimal-string rejection); ConvertsToLong ('42' True, '4.5' False);
ConvertsToDecimal ('3.14' True, 'abc' False); ToString int '5'; ConvertsToDate
('2024-06-15' True, '2024-13-01' False); ConvertsToDateTime (plain + +05:00 True);
ConvertsToTime ('T14:30' AND bare '14:30' True [fixtures :351-352], 'T25:00' False);
ConvertsToQuantity bare-calendar '5 years' True / bare-UCUM '5 mg' False (pinned);
CanConvertQuantity kg->g True / g->s False; null propagation rows -> None.
3 harness EXC rows were identical-both (probe spellings, not defects).

Evidence: .temp/qa/speccomp2/cql06_skeptic_probe1.py
