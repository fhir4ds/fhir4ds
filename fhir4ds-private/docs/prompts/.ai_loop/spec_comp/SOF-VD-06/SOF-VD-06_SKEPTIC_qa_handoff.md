# QA Handoff — SOF-VD-06 SKEPTIC (forEach / forEachOrNull)

## Verdict: CLEAN — 12/12 fresh dual-path cases (flagged=0 after 1 adjudication)

Verified: forEach multiplies rows per item; empty collection suppresses rows
(p3 dropped); forEachOrNull preserves ONE null row for empty collections and
behaves like forEach when non-empty; deep-path iteration (contact.name.given)
with $this; singleton collections; filtered collection exprs
(name.where(use='official')); %context = iterated item (verified %context =
$this true); %rootResource reaches the root; %rowIndex 0-based per parent;
forEach + collection column; complex items w/ nested navigation.

1 adjudication: `name.where(use='official')` DROPS names with ABSENT use
(empty != true) — p2's use-less name filtered out; want corrected.

Evidence: .temp/qa/speccomp2/sofvd06_skeptic_probe1.py
