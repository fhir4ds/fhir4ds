# QA Handoff — FP-20 SKEPTIC (§9 env vars / §10 reflection / §11 type safety / §12 grammar)

## Verdict: CLEAN — zero defects (26 fresh dual-path cases; 2 MISS both adjudicated probe errors)

%context/%resource/%rootResource identity + navigation; %ucum canonical URI; backtick
%`vs-administrative-gender`; type() reflection for every literal type + namespace
System/FHIR + multi-item per-element TypeInfo; name.first() HumanName.
MISS adjudications: (1) birthDate.type().name — MY fixture lacked the birthDate field
(with field → ['date'] verified m3098); (2) is_valid("1 = 'a'") = True is the documented
runtime-error-class doctrine (execution errors are valid expressions) — my False
expectation wrong. §11 runtime type errors → empty both engines (1='a', true=1,
1+'a', true<false). Grammar edges: (), id., 1 + + 2 = 3 (double unary) consistent.

Evidence: .temp/qa/speccomp2/fp20_skeptic_probe1.py