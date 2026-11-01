# QA Handoff — SOF-VD-05 SKEPTIC (nested select recursion)

## Verdict: CLEAN — 12/12 fresh dual-path cases (flagged=0 after 6 want-adjudications)

Core doctrine VERIFIED (12 cases): columns in a select with forEach/forEachOrNull
evaluate against the ITERATED focus — parent-scope columns yield NULL, %resource
required for root values. Nested select without forEach inherits $this context.
Parent+child columns combine (single-valued contexts). 2-level nesting
(contact → name.given). Name collisions (parent-child + within nested select) →
ParseError. Empty nested select {} is legal (column 0..*), contributes no columns,
parent rows kept. Empty forEach focus → 0 rows; forEachOrNull → null row. Mid-select
forEach re-focuses sibling columns. Sibling nested selects compose (cartesian).

6 adjudications — ALL want errors, engines identical (parity OK everywhere):
pid/g/cfam NULL at iterated/deeper focus per the doctrine above; %resource.id is
the correct way to reach root values from a forEach select.

Evidence: .temp/qa/speccomp2/sofvd05_skeptic_probe1.py
