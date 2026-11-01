# QA Handoff — FP-19 SKEPTIC (§7 aggregate + §8 lexical)

## Verdict: CLEAN — zero defects (28 fresh cases; 4 MISS all adjudicated probe-expectation errors)

§7.1 aggregate (sum/no-init-null-total/$index/empty+init/empty-no-init/arity errors);
§8.1 whitespace charset; §8.2 comments (line/block/markers-in-strings); §8.5 keywords
(reserved via backtick = unknown fn); §8.6 identifiers; §8.7 case-sensitivity.
Adjudications: (1) `id in (p1|x)` → ['false'] CORRECT — bare p1/x are PATH identifiers
evaluating empty; string form `id in ('p1'|'x')` → ['true'] verified. (2) top-level
backtick-given → [] CORRECT (given lives under name; name.`given`.count() → ['2']).
(3)+(4) same two rows double-counted by the flag counter.

Evidence: .temp/qa/speccomp2/fp19_skeptic_probe1.py
