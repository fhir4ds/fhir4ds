# QA Handoff — CQL-19 SKEPTIC (list operators Part 2)

## Verdict: CLEAN — 0 defects (~25 fresh cases + adjudication micro-probes)

Last/Length (Last {1,2,3}=3; Last {}=None); properly includes matrix (subset True /
identical False / converse True / null-right False / disjoint False); union family
(dedup count 3, symbolic | = union, union null operand -> other list); != and !~
order-sensitive rows; singleton-ok (S1 'only', S3 None); skip/take (Skip 1->[2,3],
Take 2->[1,2], Tail->[2,3], Skip 0->whole, Take -1->[], Skip 10->[]); and the
KEY ADJUDICATION: static-literal `singleton from {1,2}` raises the TYPED
SingletonFrom error (InvalidInputException) on BOTH engines — the SPEC §20.30
run-time-error path; the rows-branch NULL adjudication applies only to the
SUBQUERY/rows spelling (gate fixtures outrank prose THERE). LIB-ERROR sentinel
pattern added to the harness for typed-error libs (per-engine try/except
requiring BOTH to raise).

Evidence: .temp/qa/speccomp2/cql19_skeptic_probe1.py (flagged=0 of 5 libs + 1 error lib)
