# QA Handoff — FP-02 HISTORIAN (FHIRPath §4.2-§4.5)

## Verdict: CLEAN — zero defects (0 issues logged)

49 fresh dual-path cases across 2 systematic battery walks:
- probe1 (31): §4.4 empty-propagation table, §4.5 singleton truthiness,
  §4.2 operator table rows, §4.3 invocation forms.
- probe2 (18): narrative-rule edges (empty-criterion iif, absorbed logic rows,
  precedence/associativity, indexer vs toChars, substring empty-length).

## Adjudications (6 flagged rows — all probe-expectation artifacts, NOT bugs)
1. `{} = {}` → [] — my ['true'] expectation was WRONG: official fixtures
   testEquality2/testNEquality2 carry NO <output> = expected-EMPTY assertions;
   empty collection short-circuits the comparison table. Both engines [].
2. `'a' & 'b'` → ['ab'] — fhirpath() renders strings BARE (no quotes); my
   '"ab"' display-form expectation was wrong. Verified via `'a'&'b' = 'ab'` → true.
3. `id.length()` → ['5'] — fixture id is 'pat-1' (5 chars); my '3' assumed a
   different fixture. Correct value for this resource.
4. `gender` → ['male'] — bare-string rendering (same convention as #2).
5. `{} and true is true` — INVALID GRAMMAR ('is' takes a type specifier, not a
   Boolean literal); is_valid=False correctly returned; eval → empty both engines.
6. `id[0]` → ['pat-1'] — indexer selects collection ITEMS; strings are not
   char-collections. String decomposition is toChars() (id.toChars()[0] → 'p').
   Fixture testIndexer pins name[0].given (collection item selection).

## Evidence
Scripts: .temp/qa/speccomp2/fp02_historian_probe{1,2}.py
Logs: inline (adjudication re-probes included)
