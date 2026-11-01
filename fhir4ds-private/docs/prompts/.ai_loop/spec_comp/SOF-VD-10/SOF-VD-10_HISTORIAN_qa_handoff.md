# QA Handoff — SOF-VD-10 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 22/22 cases (flagged=0 after 2 adjudications)

H: boundary names (1/255 chars); nested duplicate column depth-2 rejected;
where array-of-non-objects rejected; constant dual value[x] rejected;
constant valueInteger float rejected; H8 single-branch unionAll ADDS a column
(arm model — legal; row carries enclosing+branch cols); H8b branch-vs-BRANCH
schema mismatch -> typed ValidationError (official union.json fixture shape,
expectError:true). E: emoji names rejected; resource digits/non-string
rejected; select non-array rejected; column non-object rejected; empty VD {}
rejected; repeat-string rejected; constant unknown field ACCEPTED (official
validator has NO additionalProperties:false on constant items — SOF-VD-10
HISTORIAN doctrine).

Adjudications: H8 want (arm-model legality, execution-verified);
E10 want (permissive constant items per official validator).

Evidence: .temp/qa/speccomp2/sofvd10_historian_explorer_probe1.py
