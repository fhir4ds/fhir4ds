# QA Handoff — FP-10 SKEPTIC (§5.6.6-§5.6.12 String Transform)

## Verdict: CLEAN with ONE findings-only LOW note (58 fresh dual-path cases:
probe1 31/31 parity 0 flags; probe2 26/27 parity + 1 isolated DIFF)

## FP-10-F01 (LOW, dialect note — findings-only, no patch)
`'a\nb'.matches('a.b', 's')` — native ['true'] vs fallback [].
- Spec: 2018Sep §5.6.9 defines ONLY 'm' and 'i' flags; 's' is illegal input.
- Fallback (spec-strict): strings.py _regex_flags rejects 's' →
  FHIRPathError → row-resilient []. Verified via direct core evaluate.
- Native (lenient): fhirpathRegexCompileOptions (evaluator.cpp:289-307) ACCEPTS
  's' as a no-op (ECMAScript std::regex has no dotall) — carries an in-code
  'FP-10 QA-003 dialect note' comment; a third flag char 'x' IS rejected by
  native too (verified). Matches the documented FP-10 SKEPTIC 2026-08-17
  lineage (native folds leading (?s) groups).
- Existing coverage: test_string.py test_matches_flags pins i/m only; no
  integration parity 's'-row exists.
Recommendation (for human): either drop 's' from the native accept-set
(rebuild required — out of maintenance scope) or pin the asymmetry explicitly
in the parity suite. Do NOT change behavior silently.

## Clean evidence
upper/lower (sharp-s→SS, Turkish, é); replace literal + empty-pattern
wraps-each-char (fixture testReplace2 :771) + empty-sub removal; matches
search semantics/anchors/classes/i-flag; replaceMatches $1/global/no-match;
length + toChars code-point semantics (café 4, emoji 1); multi-item/empty
propagation; typed-input rejections; compositions (upper→matches,
toChars→count, replace→length, iif-over-matches).

Evidence: .temp/qa/speccomp2/fp10_skeptic_probe{1,2}.py
