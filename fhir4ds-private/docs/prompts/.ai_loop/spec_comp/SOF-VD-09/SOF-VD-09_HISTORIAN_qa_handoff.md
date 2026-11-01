# QA Handoff — SOF-VD-09 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 12/12 cases, PARITY OK after 3 adjudications

H1 compound boolean chain; H2 ofType(boolean) deceased absent -> excluded
(official logic.json fixtures pin PRESENT deceasedBoolean:false for
m0/f0 — absent field yields empty=false-cast -> excluded; both engines
agree); H3 negated predicate; H4 where at iterated focus filters per-item
(p1-Gray + p2-Gray); H5 %resource-scoped where in forEach (root filter
pre-iteration); H6 three-way AND. E1 enclosing where + unionAll arms
(filters ALL branches); E2 iif() in where; E3 count() compare; E4
constant-false where excludes all; E5 description + complex where
(name.where(use='official').given.first() = 'John'); E6 backtick constant
reference in where.

Adjudications: H2 want corrected per official fixture semantics; H4 was a
harness sk() wrapping bug (fixed); E6 backticks were over-escaped in the
probe (fixed with chr(96)).

Evidence: .temp/qa/speccomp2/sofvd09_historian_explorer_probe1.py
