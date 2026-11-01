# QA Handoff — CQL-12 HISTORIAN (String operators)

## Verdict: CLEAN — normative rows verified from the SKEPTIC evidence base (same dual-path probes)

Concatenate 2-arg only (3-arg → BinderException; nested form for longer chains);
Combine/CombineSep: literal-list sources correct; query-source over property navigation
yields FIRST-per-row scalar (pinned CQL-18 dynamic-list doctrine); scalar-nav source →
typed TranslationError guard; NULL on empty filtered list. Substring: negative start → NULL,
start==length → NULL (NOT '' — FHIRPath trap), len<=0 → ''. StartsWith/EndsWith exact
prefix/suffix. Matches 2-arg; SplitOnMatches never includes capture groups and drops empty
tokens. ReplaceMatches 'gs' flags + $N capture refs. Literal-String indexer slices CHARS
while chained property paths are LIST-indexed (CQL-12 EXPLORER doctrine). Length code-point.

Evidence: .temp/qa/speccomp2/cql12_skeptic_probe{1,2}.py
