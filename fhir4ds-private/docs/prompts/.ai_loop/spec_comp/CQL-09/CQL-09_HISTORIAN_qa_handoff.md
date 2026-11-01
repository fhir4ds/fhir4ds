# QA Handoff — CQL-09 HISTORIAN (comparison operators)

## Verdict: CLEAN — 7/7 spec-row groups, 0 flags (from cql09_historian_explorer_probe1.py H-rows)

Between (true/false bounds + between-equivalence row (5 between 2 and 10) =
((5>=2) and (5<=10))); Equal/NotEqual; Equivalent string case-fold + whitespace
normalization; Quantity unit-aware (2 'kg' = 2000 'g' true; 1 'm' < 100 'cm'
false — equal magnitudes; dim-mismatch 1 's' > 1 'g' → null → False surface);
temporal ordering + equality; resource-backed birthDate anchor (p1 <1980 True /
p2 False). Native==fallback every row.

Evidence: .temp/qa/speccomp2/cql09_historian_explorer_probe1.py (H-prefixed libs)
