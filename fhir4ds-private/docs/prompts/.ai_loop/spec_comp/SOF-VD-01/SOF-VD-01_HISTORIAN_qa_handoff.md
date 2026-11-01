# QA Handoff — SOF-VD-01 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 12 fresh dual-path cases (H1-H6 normative + E1-E6 fuzz), 0 parity diffs

H: id projection order; typed boolean/string columns; collection=true on
name.given (['John','Kim'] / [] / []); where name.exists() filters to p1;
unionAll branch emits parent column + branch column only for matching focus.
E: nested forEach (parent pid + family per name); iif expression column
(M/F/F); %resource.id inside forEach; %flag boolean constant ('true' string
render); constant-false where filter -> 0 rows; projection of plain ids.

All rows identical native == fallback. Evidence:
.temp/qa/speccomp2/sofvd01_historian_explorer_probe1.py
