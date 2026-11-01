# QA Handoff — FP-16 SKEPTIC (§6.4 Collections)

## Verdict: CLEAN — zero defects (27 fresh dual-path cases)

Union dedup via = semantics (int/int-decimal/resource/quantity 1cm|10mm=1/deep objects/
with-empty sides); in membership (true/false rows; left-empty propagates; right-empty
false; quantity equality-based; precision-mismatch temporal empty); contains containership
(mirror semantics); converse property verified; multi-item singleton operands →
row-resilient empty both engines.

## 7 MISS rows ALL adjudicated probe-expectation errors
My probe used CQL-style NON-EMPTY list literals {1, 2}, {1 'cm', 1 'm'}, {'a', 1} —
NOT FHIRPath grammar (only {} exists; | builds non-empty collections — pinned FP-02
EXPLORER doctrine). Also union() FUNCTION takes a collection arg: union({'Chalmers'})
syntax empty; union('Chalmers' | {}) works. All correct spellings verified true on
BOTH engines (1 in (1|2), quantity/temporal/mixed unions, contains mirrors).

Evidence: .temp/qa/speccomp2/fp16_skeptic_probe1.py + adjudication inline matrix
