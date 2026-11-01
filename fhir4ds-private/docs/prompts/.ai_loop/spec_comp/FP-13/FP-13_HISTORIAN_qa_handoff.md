# QA Handoff — FP-13 HISTORIAN (§6.1 Equality family)

## Verdict: CLEAN — zero defects (23 fresh spec-verbatim cases; 1 MISS adjudicated)

§6.1.1 rows: 1=1/1!=1/'a'='b'/union-collapse (1|1)=1/multi ordered/3.5=3.50;
quantity 10mg=10mg, 100cm=1m; temporal tz-instant equality, precision-mismatch
(@2012-01 = @2012 → empty). §6.1.2 rows: 1~1, {}~{}, 1~{} false, 'a'~'a'/'a'~'A',
1.10~1.1, 1.2/1.8~0.67, 0.0~0, @2012-01~@2012 FALSE (not empty), @2012-01~@2012-01,
3.5cm~3.50cm, 2'mo'~1'mo' false.

## Adjudication (1 MISS)
`@T23:59:54.999 = @T23:59:55` → ['false'] CORRECT: both ms-precision; the VALUES
differ numerically (54.999 ≠ 55.000; seconds+ms are one combined decimal precision).
My [] expectation confused value-difference with the precision-MISMATCH rule —
control rows verified: @T23:59:54.999 = @T23:59:54.999 → true; @T23:59 = @T23:59:00
(sec-vs-ms precision) → [] as expected. Probe artifact.

Evidence: .temp/qa/speccomp2/fp13_historian_probe1.py + adjudication controls
