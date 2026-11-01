# QA Handoff — FP-04 EXPLORER (FHIRPath §5.2 Filtering and Projection)

## Verdict: CLEAN — 0 defects. 30/30 parity, 0 diffs.

## Coverage (fuzz/pathological, fresh evidence, seed 20261002)
- Nested where-in-select-in-repeat compositions (deep chains).
- $this scope shadowing/restoration across nested selects; $index nesting.
- Pathological criteria: empty-string criteria, not()/double-not compositions,
  iif-criteria, constant projections, arithmetic on $this.
- Resource-shape edges: contained resource mixing (ofType then repeat then where),
  missing-path depth, empty-collection sources, scalar ofType.
- 8 seeded random atom x op compositions.
All runtime-error rows failed symmetrically (row-resilient empty on both engines).

## Evidence
Script: .temp/qa/speccomp2/fp04_explorer_probe1.py — 30/30 ok.
