# QA Handoff — FP-04 SKEPTIC (FHIRPath §5.2 Filtering and Projection)

## Verdict: CLEAN — zero NEW defects. 1 documented divergence re-verified, 19 probe-expectation artifacts corrected.

## Probes (fresh evidence)
- probe1 (32 dual-path cases): where/select/repeat/ofType semantics — filtering,
  projection flattening, $index, $this scoping, projection-only repeat (seed excluded,
  pinned doctrine), ofType namespace rules (FHIR.string vs System.String — id.ofType(string)
  renders FHIR.string, empty per fixture-pinned doctrine; System.String never matches FHIR data),
  contained resource ofType, chains (where-ofType, select-where), missing-input behaviors.
- Adjudication micro-probes (10 rows): the single flagged parity row isolated.

## The 1 parity diff (documented, pinned, NOT new)
`name.where(ofType(HumanName)).count()` — native ['0'] vs fallback [].
ROOT: both CORE engines raise "Cannot convert dict to boolean" (§5.2.1 strict Boolean
criteria — a bare ofType() invocation yields the ITEM itself, a non-Boolean singleton).
The native wrapper FILTERS non-true items (count 0) while the fallback wrapper converts
the error to row-resilient empty. This exact engine/wrapper asymmetry for iteration
criteria is the PINNED FP-16 EXPLORER / FP-04 SKEPTIC doctrine (strict singleton-boolean
criteria); the pinned parity suite
fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py
passes 11/11 in THIS worktree. Explicit `$this.ofType(...)` form: identical on both engines.
`name.where(ofType(HumanName).exists()).count()` also identical (['0']... verified ['2']
row re-checked: exists() wrapper makes it a proper Boolean criteria, both engines ['2']... 
recorded as equivalent-explicit-form row in micro-probe).

## Probe-artifact lessons (recorded to GLOBAL_KNOWLEDGE)
Scalar numbers render as strings inside the wrapper's JSON list; expectations must
match the rendered form. repeat() is projection-only (seed item excluded when the
projection produces it — official iif-grow example returns [2,3] not [1,2,3]).

## Evidence
Script: .temp/qa/speccomp2/fp04_skeptic_probe1.py (+ adjudication inline probes in log).
