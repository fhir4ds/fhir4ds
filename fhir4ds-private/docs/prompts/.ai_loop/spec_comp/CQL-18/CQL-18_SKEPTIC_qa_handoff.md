# QA Handoff — CQL-18 SKEPTIC (CQL List operators Part 1)

## Verdict: CLEAN — 23/23 fresh dual-path cases after 3 probe-expectation adjudications (0 parity diffs, 0 defects)

Literal-list static surface: Contains (incl. null-element → False per the pinned
CQL-15 null-contains doctrine); In membership; Distinct ({1,1.0} collapses via
numeric equality to a 1-element list — Count-checker sentinel); list Equal/
Equivalent order-wise; Except/Intersect equality-based set ops; Exists(list)
non-empty; Flatten; First = LIST_EXTRACT; Includes/Included In; IndexOf
(first-occurrence, -1 not-found); Count/Length over lists.

Adjudications: (1) null in {1,2} → False (spec-mandated false, NOT null);
(2) {1, 1.0} distinct → DISTINCT LIST [1.0] not a Boolean (probe shape error —
a DISTINCT-LIST sentinel checker now verifies 1-element numeric-collapse);
(3) First({1,2,3}) = 1 (my want=10 was a copy-paste typo).

## Evidence
Script: .temp/qa/speccomp2/cql18_skeptic_probe1.py (flagged=0 of 23)
