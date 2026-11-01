# FP-04 HISTORIAN QA Handoff (iteration 1, 2026-08-17)

Chunk: FHIRPath N1 §5.2 Filtering and Projection — where(criteria),
select(projection), repeat(projection), ofType(type). Spec grounding
carried from the SKEPTIC launch (N1 §5.2.1-§5.2.4, §6.3.1, §6.3.3 +
build.fhir.org FHIRPath override notes).

Method: fresh dual-path probes (native extension vs Python fallback, 6
result channels each) run with `PYTHONPATH=/mnt/d/fhir4ds`, batteries in
`/mnt/d/fhir4ds/.temp/qa/fp04_historian_2026_08_17/` (probe.py 49 cases,
probe2.py 30 cases). 79 total cases, ZERO parity fails, ZERO new spec
violations.

## SKEPTIC fix re-verification (regression-free, spec-correct)
- structuralFHIRComplexType fix re-verified on its edges: is/as/ofType/
  type() over structural Coding/CodeableConcept/Quantity/Reference/
  Range/Period objects, unknown objects, and backbone preservation —
  all 12 R1 cases parity-clean.
- Regression test
  `test_structural_complex_type_tests_match_cpp_fp04_skeptic`:
  13/13 passed.

## New seams probed (all clean)
- Scope: defineVariable inside where() criteria correctly does NOT leak
  into subsequent select() in either engine (both error identically on
  the later %v access); $index restored after where(); nested
  select-in-select; $index inside repeat projections.
- Criteria truthiness: constant true/false criteria, empty criteria,
  string and multi-item criteria (error → empty), iif-inside-select with
  empty branches, empty-comparison criteria on partial dates — all
  spec-consistent in both engines.
- ofType supertypes/profiles: DomainResource/Resource supertype match,
  Element does NOT match resources (0 — consistent with the model
  hierarchy), subtype/supertype chaining both directions, Age/Duration
  correctly REJECT temperature and energy quantities (FP-15 doctrine),
  SimpleQuantity → 0 (Quantity is the ofType selector per FHIR page),
  System.* never matches FHIR-typed data (pinned doctrine), FHIR.string
  on `id` → empty (primitives independent).
- repeat() fixpoint: value-growth fixpoint (`$this < 3` → [2,3]),
  `=`-dedup with FP-02 derived units (1 'kJ'/1000 'J' and
  1 'm2/m'/1 'm' collapse to 1), key-order-different duplicate objects
  dedup via repeat and via select().distinct(), repeat($this.item)
  self-referential projection, repeat does NOT re-navigate projected
  scalars (`repeat(item.v)` → {1,3} then stops, correct).
- where() returns ORIGINAL items (`.code`/`.unit`/`.type().name` pins);
  select() flattens without dedup (`repeat(item).select(v)` keeps 4).

## Issues
None filed. issues[] remains empty; zero non-terminal
CRITICAL/HIGH/MEDIUM issues → clean exit eligible at min_iterations=1.

Validation: full conformance 2832/2832 (ViewDef 144, FHIRPath 935,
CQL 1706, DQM 47) — baseline held.
