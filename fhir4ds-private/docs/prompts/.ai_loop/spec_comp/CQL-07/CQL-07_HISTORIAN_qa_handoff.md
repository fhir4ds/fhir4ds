# QA Handoff — CQL-07 HISTORIAN

## Verdict: CLEAN — 13/13 fresh normative rows, 0 flags

Table 9-F boolean strings (T/y/1 True, 0/FALSE False); integer grammar (-42/+42 ok,
' 42' whitespace None); decimal grammar ('1e3'/'.5' None); partial-date ToDate('2024');
ToTime seconds-range '14:30:60' None; ToString(1.5) '1.5'. All identical
native vs fallback.

Evidence: .temp/qa/speccomp2/cql07_historian_probe1.py
