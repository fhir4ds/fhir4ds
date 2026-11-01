# QA Handoff — FP-04 HISTORIAN (FHIRPath §5.2 Filtering and Projection)

## Verdict: CLEAN — 0 defects. 21/21 fresh cases, 0 flags.

## Coverage (normative walk)
- §5.2.1 where(): strict Boolean criteria; returns ORIGINAL items (not
  projections); no-match/empty-criteria -> empty; criteria scope ($this).
- §5.2.2 select(): per-item projection with flattening (name.select(given)
  -> 3); $this/$index scopes; empty input -> empty.
- §5.2.3 repeat(): projection-only fixpoint (iif-grow example -> [2,3];
  identity converges ['a']); nested navigation dedup via =.
- §5.2.4 ofType(): FHIR model types (HumanName, contained Observation);
  unqualified primitive `string` never matches FHIR data (fixture-pinned
  doctrine — id.ofType(string) -> []); unknown type -> []; Boolean scalar.
- Strict-criteria row (bare non-Boolean where-criteria): row-resilient on
  both engines here (family renders ['0']/[] classes previously pinned).
- Scope restoration after select ($index) and $this in where criteria.

## Evidence
Script: .temp/qa/speccomp2/fp04_historian_probe1.py — 21/21 ok.
