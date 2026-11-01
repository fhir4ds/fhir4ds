# QA Handoff — SOF-VD-09 EXPLORER (combined battery)

## Verdict: CLEAN — adversarial compositions E1-E6 all parity-identical

unionAll + enclosing where (filters every branch row); iif() branches in
where; count() comparisons; constant booleans; backtick constant refs;
description + deep chained where. All native==fallback.

Evidence: .temp/qa/speccomp2/sofvd09_historian_explorer_probe1.py
