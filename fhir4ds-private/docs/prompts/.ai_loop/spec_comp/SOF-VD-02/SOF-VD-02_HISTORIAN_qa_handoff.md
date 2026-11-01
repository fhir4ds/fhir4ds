# QA Handoff — SOF-VD-02 HISTORIAN (constants)

## Verdict: CLEAN — 6/6 H-rows + 6/6 E-rows fresh combined battery (0 parity diffs)

H: constant substitution at depth-2 (nested forEach where %resource.gender = %g);
collection-typed %g string column; decimal 1.5 render; multi-constant iif composition;
%rowIndex builtin takes precedence over same-named constant (0,1 not 99); unknown const
at depth → ValidationError both engines. E: false-filter nested where → 0 rows; %n + 1
arithmetic → '3' string render; escaped-quote string constant equality 'true'; boolean
False constant typed column → (False,False); date-const @ equality in iif → 'y'; two
forEach columns w/ const. Two checker expectation fixes (string renders '3'/'true') and
two probe-shape fixes (constant key had been misplaced inside select — SOF-VD-05
allowlist ParseError caught it on BOTH engines, moved to top level).

Evidence: .temp/qa/speccomp2/sofvd02_historian_explorer_probe1.py (flagged=0)
