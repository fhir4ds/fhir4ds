# QA Handoff — SOF-VD-09 SKEPTIC (where clauses)

## Verdict: CLEAN — 20/20 fresh dual-path cases (flagged=0 after 2 adjudications)

Verified: single true/false include+exclude; empty-literal {} excludes ALL;
nonexistent path (empty->false) excludes; null JSON value excludes; MULTIPLE
wheres AND semantics (2-way + 3-way); truthy singleton boolean (active);
negation (active.not()); exists(); where.description retained; constant refs
in where; complex FHIRPath (where-in-where, substring compare); where +
forEach combos; boolean column beside where; empty where ARRAY = no
constraints (all rows); string-form where + missing path field -> typed
ParseError BOTH engines.

Adjudications:
1. w10 non-boolean where result (gender string): fhirpath_bool returns NULL
   for non-true/false strings (FP-06/FP-17 singleton-boolean contract) ->
   WHERE NULL -> row excluded. Parity holds on both engines. NOT a bug.
2. w16 where+forEach: where evaluates at the ITERATED focus (name.gender =
   empty -> 0 rows); root filtering requires %resource (verified live:
   %resource.gender = 'male' keeps p1 rows). Spec focus semantics, NOT a bug.

Evidence: .temp/qa/speccomp2/sofvd09_skeptic_probe1.py + /tmp/opencode/sofvd09_adj*.py
