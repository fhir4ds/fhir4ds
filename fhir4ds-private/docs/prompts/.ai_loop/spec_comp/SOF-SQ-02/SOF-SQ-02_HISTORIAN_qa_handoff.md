# QA Handoff — SOF-SQ-02 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 9/9 cases (flagged=0)

H1 self-cycle (SQLQuery->itself) rejected; H2 resolver returns ViewDefinition
DICT (structural select+resource detection); H3 resolver returns Library
dict; H4 date param coerced to DATE (2024-01-15 + 1 -> 2024-01-16); H5
decimal param arithmetic. E1 diamond dependency graph (B->D, C->D, JOIN
across both views); E2 boolean param; E3 unreferenced declared param ->
raw DuckDB InvalidInputException (documented engine error, not typed —
by-design boundary); E4 unicode parameter round-trip.

Evidence: .temp/qa/speccomp2/sofsq02_historian_explorer_probe1.py
