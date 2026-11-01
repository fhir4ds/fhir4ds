# QA Handoff — CQL-20 EXPLORER (combined battery E-rows)

## Verdict: CLEAN — 8/8 E-rows parity-OK w/ correct values

Sum((from {10,20} Y return Y*2))=60 query-arithmetic fold; Avg scale-8; Median
odd; Sum(distinct {1,1,2})=3; Product 8; Sum(Skip)=5 subsetting composition;
Max(Take)=9; Sum(union {}) = 6 (null/empty operand union doctrine). Evidence:
.temp/qa/speccomp2/cql20_historian_explorer_probe1.py (flagged=0)
