# QA Handoff — FP-09 SKEPTIC (§5.6.1-§5.6.5 String Search)

## Verdict: CLEAN — zero defects (53 fresh dual-path cases: probe1 30 + probe2 23)

indexOf (0-based first-occurrence, -1 not-found, empty-needle 0); substring
(1/2-arg forms, start==len/>len/negative-start -> empty, length-overrun clamps,
zero-length -> empty string, spec example substring(7,1) -> {}, empty-length ARG
ignored per spec override); startsWith/endsWith (empty-prefix/suffix true,
full-string true, case-sensitive); contains (substring fn vs operator class,
empty-string true, case-sensitive); resource-backed rows; unicode CODE-POINT
semantics (café/'naïve' indexOf, emoji substring 1-char = 1 codepoint); multi-item
inputs + empty propagation row-resilient BOTH; empty-argument-collection
propagation (search-term empty -> whole expr empty; substring empty start ->
empty); non-string inputs (5.startsWith etc.) -> empty; non-integer bounds ->
empty row-resilient; compositions (indexOf->substring feed, contains->iif).

ONE MISS adjudicated: family.indexOf('alm') = 2 (C=0,h=1,a=2) — MY arithmetic
error in the expectation; both engines correct.

Evidence: .temp/qa/speccomp2/fp09_skeptic_probe{1,2}.py
