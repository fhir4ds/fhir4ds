# QA Handoff — CQL-20 HISTORIAN (combined battery H-rows)

## Verdict: CLEAN — 6/6 H-rows parity-OK w/ correct values

Length(Patient.name.given)=2 dynamic; Sum((from {1,2,3} X return X))=6 query-source
fold; Count dynamic=2; Max/Min decimals; Sum(union {4})=10 scale-8. Evidence:
.temp/qa/speccomp2/cql20_historian_explorer_probe1.py
