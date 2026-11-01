# QA Handoff — SOF-VD-05 HISTORIAN (combined battery)

## Verdict: CLEAN — 12-case combined battery PARITY OK (H1-H6 half)

H1 collection-in-nested-foreach: per-name given lists (['John','Kim']/['Kim']/['Kim']).
H2 typed string in nested select. H3 forEachOrNull null row: child columns NULL.
H4 description retained nested. H5 deep-3-level: %resource.id reachable from depth 3.
H6 nested where-clause: 'where' must be an ARRAY of {path} objects (official
fixtures shape — string form ParseErrors typed); filter works per-focus.

Evidence: .temp/qa/speccomp2/sofvd05_historian_explorer_probe1.py
