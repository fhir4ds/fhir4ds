# QA Handoff — CQL-14 HISTORIAN (DateTime ops Part 2)

## Verdict: CLEAN — 25/25 fresh battery rows (H1-H13 normative walk), 0 parity diffs

date from Now() = Today() True; Now/Today/TimeOfDay determinism; same-hour
precision rows (+05:00 10:30 vs 10:45 True; cross-hour False); same-day-or-after
inclusive; on-or-before inclusive; Time ctor precision render T14:30:45;
T12:00-90min -> T10:30; Mar31-1mo -> 2024-02-29 clamp. Battery script (shared
with EXPLORER rows): .temp/qa/speccomp2/cql14_historian_explorer_probe1.py
