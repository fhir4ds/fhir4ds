# QA Handoff — CQL-09 EXPLORER (comparison operators)

## Verdict: CLEAN — 6/6 adversarial-composition groups, 0 diffs (from
cql09_historian_explorer_probe1.py E-rows)

Chained comparisons (1<2 and 2<3 and 3<4; (1<2)=(3<4); between = true);
equivalence-of-comparisons; if-then-else over string ordering; null-side mixes
((1/0) < 5 → null→False surface; Coalesce over between); Quantity comparison
chains incl. unit-mixed (1 'kg' > 500 'g' and 500 'g' > 0.4 'kg'; 3 'cm' * 2 =
6 'cm'); string lexicographic case rows ('Apple' < 'apple'); date-vs-datetime
precision composition. Native==fallback every row.

Evidence: .temp/qa/speccomp2/cql09_historian_explorer_probe1.py (E-prefixed libs)
