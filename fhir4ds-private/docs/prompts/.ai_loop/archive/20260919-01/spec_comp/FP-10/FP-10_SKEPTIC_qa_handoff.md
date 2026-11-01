# QA Handoff — FP-10 (iteration 1, SKEPTIC)

Chunk: FHIRPath §5.6.6–§5.6.12 String Manipulation (upper, lower, replace,
matches, replaceMatches, length, toChars). Note: a prior FP-10 inner launch
left fixes + regression tests in the working tree (test_string_transform_parity.py
fp10_skeptic / fp10_explorer tests, Unicode case-mapping tables in
evaluator.cpp) but no state files; this launch re-ran discovery fresh.

Spec verified against N1 index.adoc fetched from HL7/FHIRPath GitHub
(/tmp/fpath_n1.adoc lines 1346–1429): replace is literal all-instances
substitution with the empty-pattern/empty-substitution examples; matches must
be case-sensitive, single-line mode, allow Unicode, PCRE recommended, dialect
NOT prescribed; replaceMatches replaces each match with group-reference
substitution ($N, ${name}, canonical date example); length/toChars empty→{}.

Probes: 82 dual-path cases (probe.py) + 31 regex-class cases (probe2.py) +
direct-helper comparisons, in /mnt/d/fhir4ds/.temp/qa/fp10_skeptic2_2026_08_17/.

Verified clean (zero parity/spec diffs): upper/lower Unicode case mapping
(ß→SS, ς↔Σ, ﬃ→FFI, İ lower, dotted letters, CJK, mixed-script); replace
literal semantics incl. both occurrences, regex-metachar-as-literal,
empty-pattern xaxbxcx example, empty-substitution removal, astral-plane
replacements, not-found no-op; matches partial-match semantics, single-line
default, backreferences, lookahead, non-capturing groups, \Z, bounded
quantifiers, unicode literals/classes/ranges, flag args i/m/im; replaceMatches
global replacement, $N reordering, $0, non-participating groups, no-match
unchanged, spec date example (numbered form); length/toChars code-point
semantics incl. astral (😀x😀 → 3) and combining sequences; empty/multi-item/
non-string error paths uniform across engines; arity/invalid-flag/ReDoS/
overlong-pattern classification parity.

Issues filed (evolution.json):
- QA-001 MEDIUM: native default-mode `$` lacks PCRE trailing-newline match.
- QA-002 MEDIUM: native lacks inline (?i)/(?m) flag groups.
- QA-003 MEDIUM: fallback \w\d\s\b Unicode-aware vs PCRE-default/native ASCII.
- QA-004 LOW DEFERRED: lookbehind unsupported in std::regex (dialect-sanctioned).
- QA-005 MEDIUM: fallback pattern precheck rejects `$$` inside string literals.
- QA-006 MEDIUM: direct helper replace_matches missing $N/${name}/$$/named-group
  translation; replace helper lacks None-arg guard (helper-API family, 5th).

Existing FP-10 regression tests pass (7/7). No conformance run yet this launch.
