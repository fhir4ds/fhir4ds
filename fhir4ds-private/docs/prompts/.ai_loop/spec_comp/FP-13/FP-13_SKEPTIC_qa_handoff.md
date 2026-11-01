# QA Handoff — FP-13 SKEPTIC (§6.1 Equality family: = / ~ / != / !~)

## Verdict: CLEAN — zero defects (35 fresh dual-path cases; 1 MISS adjudicated)

Covered: = basics (int/decimal-exact/string/bool; cross-type empty); Quantity =
(cross-unit 1cm=10mm/1kg=1000g; calendar 1 month=30 days, 1 year=12 months; calendar-vs-UCUM
EMPTY per pinned doctrine; 1 second = 1 's'; 23 = 23 '1'); Date/Time = (tz-equivalent
instants, precision-mismatch EMPTY, time-vs-string EMPTY per §5.5 Explicit-only,
date-vs-string JSON-convenience true); ~ String (case-fold true); ~ Quantity tolerance
(least-precision half-width: 1.0 g ~ 1.06 g true; 1.6 false); ~ Date differing
precision FALSE (not empty); multi-item ORDERED ( (1|2)=(1|2) true, !=(2|1) true );
empty propagation ({} = {} empty, {} != 'x' empty); resource-backed rows.

## Adjudication (1 MISS)
`'hello world' ~ 'helloworld'` → ['false'] BOTH engines — CORRECT: string
equivalence normalizes whitespace by REPLACING each whitespace char one-for-one
(replace-not-collapse doctrine; fixtures testEquivalent5-7 pin the case-fold and
inequality rows). My 'true' expectation assumed collapsing. Probe artifact.

Evidence: .temp/qa/speccomp2/fp13_skeptic_probe1.py
