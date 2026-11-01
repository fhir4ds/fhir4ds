# QA Handoff — FP-10 HISTORIAN (iteration 1)

Chunk: FHIRPath §5.6.6–§5.6.12 String Manipulation (upper, lower, replace,
matches, replaceMatches, length, toChars). Personality: HISTORIAN. Spec text
verified against cached N1 index.adoc §5.6.6–§5.6.12 (/tmp/fpath_n1.adoc
1346–1429); SKEPTIC launch handoffs re-read for fix re-verification targets.

Probe: 107 dual-path cases + follow-ups in
/mnt/d/fhir4ds/.temp/qa/fp10_historian2_2026_08_17/probe.py
(native extension conn vs forced Python fallback, both via
`SELECT fhirpath(?,?)` + `fhirpath_is_valid`, per FP-04 doctrine).

## All 5 SKEPTIC fixes re-verified intact
`$`-anchor trailing newline, leading (?i)/(?m)/(?s) fold (matches +
replaceMatches, incl. (?m)^b$ on 'a\nb'), ASCII \w/\b classes on '日本語',
`$$` inside literals, helper replace_matches $N/${name}/$$ — all parity-correct.

## Verified clean (fresh angles, zero parity/spec diffs)
- upper/lower: titlecase ǅ→Ǆ/ǆ, ẞ→ß, Kelvin K→k, ﬅ→ST, ẛ→Ṡ, ligatures
  ﬀﬁﬂﬃﬄ, empty→{} (`.length()` also {}), non-string/multi-item error paths,
  resource-field driven inputs, case chains.
- replace: non-overlapping left-to-right scan ('aaa'.replace('aa','b')='ba'),
  no rescan ('a'→'aa' = 'aaaaaa'), case sensitivity, longer-than-input
  pattern, escaped-newline literal, ''/'' corner, absent-arg fields → {},
  arity classification.
- matches: empty-string regex, single-line dot vs \n, negated class matches
  \n, anchors, bounded quantifiers, backrefs, flag args i/invalid, arity.
- replaceMatches: global non-overlapping replacement, $N reorder, $0,
  non-participating group → '', out-of-range $N, $10 two-digit, dangling $,
  $name literal, no-match unchanged, multiline flag path, non-string args.
- length/toChars: code-point counts (😀x😀=3, combining=2), ''→{} vs 0,
  toChars()[indexer]/first/last/count/select chaining, non-string/multi-item.

## Issues filed
- QA-001 (HIGH, SPEC_VIOLATION): native engine cannot execute the spec §5.6.10
  canonical replaceMatches example — `(?<name>…)` named groups are rejected by
  std::regex (is_valid=False, empty) and `${name}` substitution is passed raw
  to std::regex_replace. Fallback returns '30-11-1972'. Also affects
  '$n'/'${n}'/'${missing}' variants (all named-group-rooted).
- QA-002 (MEDIUM, API_CONTRACT): direct helper `matches()` raises raw
  TypeError on None regex (len(None) in _validate_regex) instead of the
  sibling-helper contract ({} / typed error). 6th instance of the
  exported-helper-API family.
- QA-003 (LOW, DEFERRED): mid-pattern inline flags `a(?i)B`, scoped
  `(?i:a)b`, and regex-level `\uXXXX` escapes diverge (Python re supports,
  std::regex — and default PCRE for \u — do not). Dialect-sanctioned, same
  family as the lookbehind pin; to be added to the divergence pin test.

Probe artifact note: an apparent `é` regex diff was traced to an escaped
backslash in the probe literal (regex-level \u, not FHIRPath literal \u) —
not a bug.
