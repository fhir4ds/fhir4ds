# QA Handoff — CQL-12 SKEPTIC (String operators)

## Verdict: CLEAN — probe1 flagged=0 (6 libs ~27 defines) + probe2 effective-clean (2 adjudications)

probe1: Concatenate 2-arg (+ nested 3-string); Upper/Lower/Length code-point (Length('café')=4);
Replace literal + Trim; PositionOf first-occurrence + IndexOf; Combine query-source
((from [Patient] P return P.name.given), '+') → 'John' FIRST-per-row scalar on BOTH engines
+ literal {'John','Kim'} → 'John+Kim'; Substring bounds matrix (negative start NULL, start==len NULL,
len<=0 → ''); string indexer char-slicing ('Montavon'[2]→'n'); Split.
probe2: Matches 2-arg; SplitOnMatches (empty tokens DROPPED — 'one two  three' on \s+ →
[one,two,three] BOTH engines); ReplaceMatches $2 $1 backreference → 'Smith John'; Trim/StartsWith rows.

## Adjudications (2, both probe errors — engines identical everywhere)
1. Matches 3-arg-with-flags spelling → BinderException BOTH: CQL Matches macro is 2-ARG;
   official fixtures' 3-arg form is Matches(s, pattern, SUBSTITUTION) — flags are a SQL-macro
   param, not a CQL argument.
2. SplitOnMatches double-space: engine drops empty tokens (vs my Java-split '' expectation) —
   both engines identical.

Evidence: .temp/qa/speccomp2/cql12_skeptic_probe{1,2}.py + /tmp/opencode/cql12_adj*.py
