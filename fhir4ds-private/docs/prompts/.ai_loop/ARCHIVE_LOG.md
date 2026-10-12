
## maint/spec-comp-20261012 — spec-compliance iteration (2026-10-12, opencode-fix4)

- 2026-10-12T03:20:00-05:00 WORKTREE_READY (cf66ab1d)
- 2026-10-12T04:05:00-05:00 PROBE GREEN (probe1: 12 checks 0 findings after three probe-shape corrections — _plain_code is a class staticmethod; SearchResult exposes attrs not subscripts; and the no-key ctor is LAZY by documented design so the typed error must be asserted at CALL time not construction — 9th instance of the probe-error-over-bugs ratio rule). Fresh coverage: UMLS adapter unit invariants via fake-urlopen injection — SAB map covers all six documented systems; MTH family excluded from results (no leak through the pipeline); _plain_code extracts URI tails for all source shapes; search->CUI->atoms pipeline returns multi-SAB deduped rows (C1-A duplicate collapses, SNOMED+LOINC both present); apiKey rides the QUERY PARAM (UTS contract, never Basic); the no-key CALL raises the typed UMLSTerminologyEndpointError with env-var guidance and never echoes a key value; fs-list traversal guard semantics (resolve().relative_to) reject escape paths.
- 2026-10-12T04:55:00-05:00 GATES: terminology pytest 49 passed/4 skipped; devserver pytest 204/204; dev-server e2e 48/48 FIRST PASS (PYTHONPATHs retargeted).
- VERDICT: CLEAN, 0 findings. Findings-only per directive; branch left for human merge.
