# QA Handoff — SOF-VD-04 SKEPTIC (column.collection / column.type)

## Verdict: CLEAN — 20/20 fresh dual-path cases (flagged=0 after adjudications)

Verified: collection default false when unset (single-value path projects scalar,
None for absent); multi-value path WITHOUT collection -> RUNTIME ERROR both engines
(InvalidInputException; p1 has 2 names); first()-demoted single legal; collection=true
-> typed DuckDB LIST wrapping scalars too (['male']), absent -> [] empty list; given
nested flatten (['John','Kim','Kim']); telecom.value multi; type=string/boolean/date
pass-through ('true' string renders); type-mismatch string-on-birthDate and
boolean-on-gender -> runtime error both; unknown relative type URI -> ValidationError
(supported-list) both; System name 'String' -> ValidationError both; complex path w/o
type -> runtime error; complex + HumanName type -> JSON strings in list; element-ID
same-resource accepted (runtime guard only); element-ID CROSS-resource rejected at
generation (ValidationError); full type URI form works; collection+type combined.

Adjudications: (1) collection=true on a single-valued path ALSO list-wraps
(['male'] not 'male') — corrected my want; (2) absent -> [] (not None) per
SOF-VD-04 doctrine 'collection=true emits typed arrays; empty list for absent'.

Evidence: .temp/qa/speccomp2/sofvd04_skeptic_probe1.py
