# QA Handoff — spec_comp FP-01 (FHIRPath §4.1 Literals) — SKEPTIC

## Verdict: CLEAN — 0 issues logged
~123 fresh dual-path cases (native C++ extension vs forced Python fallback)
across 5 probe batteries. All flagged rows adjudicated as probe artifacts.

## Probe batteries (.temp/qa/speccomp2/fp01_skeptic_probe{,2,3,4,5}.py)
- probe1 (48 eval parity): ALL PARITY-OK. int32 bounds; 0.1+0.2=0.3; 28-digit
  Decimal; partial-date precision mismatch empty; tz-equivalent DateTime equality;
  quantity literal equalities (1 month=30 days; 1 'cm'=10 'mm'; 1 'kg'=1000 'g';
  1 day=24 'h'). '1 month + 1 day' → '31.436875 day' on BOTH engines — evaluation
  rule over example prose (pinned doctrine).
- probe2/3 (26 is_valid + adjudication evals): 'TRUE' is_valid=True both engines
  is CORRECT (case-sensitive identifiers: TRUE parses as identifier → evals []).
- probe4 (13 verbatim quantity-spec examples): ALL PASS.
- probe5 (18 escape/toString cases): toString round-trips all pass; heredoc
  double-escaping created 4 false MISS rows — direct-construction probes
  (chr(92)) verified '\f', '\u00E9', '\r' all correct.

## Probe-artifact lessons (recorded to GLOBAL_KNOWLEDGE)
- heredoc r-string double-escaping: build backslash cases via chr(92).
- display-compare of newline/tab rows: check actual bytes, not repr.
- 'flagged' counts are expectation misses — adjudicate before logging.
