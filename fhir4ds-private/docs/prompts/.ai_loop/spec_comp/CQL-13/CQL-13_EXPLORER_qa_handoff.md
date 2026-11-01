# QA Handoff — CQL-13 EXPLORER

## Verdict: CLEAN — adversarial rows verified (combined battery, 0 parity diffs)

tz-offset arithmetic preserved; same-day-or-after inclusive boundary; ms-precision
duration; out-of-range ctor month raises typed ValueError identically pre-execution
on both engines; fractional-quantity truncation; years-ctor uncertainty Interval[4,5];
resource-backed birthDate duration + component extraction.

Evidence: .temp/qa/speccomp2/cql13_historian_explorer_probe1.py (E rows)
