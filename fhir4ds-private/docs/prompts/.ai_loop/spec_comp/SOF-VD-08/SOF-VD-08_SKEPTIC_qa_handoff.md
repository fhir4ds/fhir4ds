# QA Handoff — SOF-VD-08 SKEPTIC (unionAll)

## Verdict: CLEAN — 11/11 fresh dual-path cases (flagged=0 after 4 adjudications)

Verified: unionAll combines branch rows (ARM MODEL: enclosing columns carried on
EVERY branch row — 2 branches x 3 patients = 6 rows; no standalone base row);
UNION ALL preserves duplicates (no value-dedup, unlike FHIRPath |); missing-
column mismatch -> ParseError; type mismatch -> ParseError; NESTED unionAll in
the OFFICIAL shape (bare-unionAll branch without own columns, sub-branches
reuse enclosing names) parses+generates; column-branch re-declaring its own
nested name -> duplicate-name ParseError (whole-tree name uniqueness);
forEach-in-branch; forEachOrNull-in-branch (null rows); repeat-in-branch
(distinct branch name required; repeat rows carry enclosing cols); where at
branch scope filters branch only; where at enclosing scope filters all rows
incl. branch rows.

4 adjudications (all want-shape errors, parity OK): arm-model row counts;
norm() int-normalizes numeric-looking linkIds; official nested-unionAll shape
discovered in union.json fixture 'nested' test (tel reused 3x through bare
unionAll branch — accepted); repeat-in-branch needed distinct column name.

Evidence: .temp/qa/speccomp2/sofvd08_skeptic_probe1.py
