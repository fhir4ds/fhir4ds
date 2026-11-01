# QA Handoff — SOF-VD-03 SKEPTIC (select/column/path)

## Verdict: CLEAN — 14/14 fresh dual-path cases (flagged=0 after 1 adjudication)

Verified: multi-select deterministic column ORDER (pid,g,bd); missing select ->
ParseError; empty select array -> ParseError (minItems 1); empty column array ->
ParseError; TWO select blocks -> single flat projection in declaration order;
forEach select relative paths (family/use from the iterated name focus); root-context
%resource.id inside forEach; duplicate column names -> ParseError; invalid sql-name
_bad -> ParseError; missing column.path -> ParseError; missing column.name ->
ParseError; unknown column field -> ParseError (SOF-VD-05 allowlist); empty path
string -> ParseError (whitespace-only FHIRPath rejection).

1 adjudication: relative-path-in-forEach expectation — forEach DROPS absent/empty
foci (p2/p3 without name produce NO rows; only p1's Chalmers row); forEachOrNull
adds the null row (verified 'Chalmers' + (None,None)). My want erroneously
included null rows for forEach — SOF-VD-11 EXPLORER doctrine (forEach drops
absent/empty) corrected.

Evidence: .temp/qa/speccomp2/sofvd03_skeptic_probe1.py + /tmp/opencode/sofvd03_adj.py
