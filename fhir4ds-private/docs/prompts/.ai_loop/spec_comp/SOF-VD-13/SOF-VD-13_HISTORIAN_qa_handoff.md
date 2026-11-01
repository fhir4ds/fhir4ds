# QA Handoff — SOF-VD-13 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 11/11 checks (flagged=0)

H1 extra_fields repr=False/compare=False (excluded from repr and ==);
H2 cnl-0 single warning per name; H3 canonical arrays validated per-entry
(empty second entry rejected); H4 sql-name on constant.name at serializer
boundary (9x rejected). E1 contact array verbatim retention; E2 multiple
unknown keys retained together; E3 empty tag array OK + empty tag.name
rejected typed.

Evidence: .temp/qa/speccomp2/sofvd13_historian_explorer_probe1.py
