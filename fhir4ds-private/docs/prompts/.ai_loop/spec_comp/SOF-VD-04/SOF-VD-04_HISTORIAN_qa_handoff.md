# QA Handoff — SOF-VD-04 HISTORIAN (combined battery w/ EXPLORER)

## Verdict: CLEAN — 12-case battery PARITY OK / values verified (flagged=0)

H-cases: collection=true inside forEach (per-name given lists; 3 rows for p1-official
+ p1-maiden + p2; row order unpinned across patients — sorted compare); typed
collection (string) in forEach; unionAll arms w/ collection (dict form -> typed
'must be an array' ParseError; valid array re-declaring enclosing names ->
duplicate-column ParseError — both engines identical; composition itself = SOF-VD-08
scope); multi-value runtime guard INSIDE forEach (given John+Kim non-collection ->
InvalidInputException both); absent typed date -> NULL row kept; %rowIndex beside
collection (per-patient counter).

Evidence: .temp/qa/speccomp2/sofvd04_historian_explorer_probe1.py
