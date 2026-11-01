# QA Handoff — CQL-05 SKEPTIC (nullological + type operators)

## Verdict: CLEAN — 15/15 fresh dual-path cases, 0 diffs

Coalesce (basic/first/variadic-4); is null / is not null (literal + absent resource
field); is true / null is true; ConvertsToInteger('42')=true ('4.5'=false);
ToString(5)='5'; convert 'true' to Boolean=true; is Integer / is String / is Any.

Harness gotcha re-confirmed: resources table must be created+seeded BEFORE
translate+execute (first run CatalogException'd on all rows).

Evidence: .temp/qa/speccomp2/cql05_skeptic_probe1.py
