# QA Handoff — CQL-09 SKEPTIC (comparison operators)

## Verdict: CLEAN — 15/15 fresh dual-path cases, 0 parity diffs

Between true/false; Equal/NotEqual; Equivalent case-fold (ABC~abc true) + !~;
Quantity unit-aware (1 'g' = 1000 'mg' true; 5 'mg' < 10 'mg' true); temporal
equality (@2024-06-15); resource-backed birthDate<'1980-01-01' p1-False/p2-True;
ge/le conjunction; qty-equivalent least-precision tolerance (1.0'g'~1.06'g' true).
3 MISS rows adjudicated as the PINNED population-surface null-collapse doctrine
(expression-level 3VL preserves NULL; boolean population membership surface renders
null as False): qty-dimension-mismatch, temporal precision-mismatch, null=null —
all IDENTICAL native vs fallback.

Evidence: .temp/qa/speccomp2/cql09_skeptic_probe1.py
