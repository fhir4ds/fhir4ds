# FP-05 EXPLORER QA Handoff (2026-08-17, iteration 1)

Personality: EXPLORER. Chunk: FHIRPath §5.3 Subsetting / §5.4 Combining
([index], single(), first(), last(), tail(), skip(num), take(num),
intersect, exclude, union, combine).

## What was probed

144 fresh dual-path probe cases (native extension vs forced Python fallback,
both via `SELECT fhirpath(?, ?)`; native assert `register_fhirpath(con) is True`;
run with `PYTHONPATH=/mnt/d/fhir4ds`). Probes saved at
`/mnt/d/fhir4ds/.temp/qa/fp05_explorer_2026_08_17/probe.py` plus two inline
batteries (re-created as part of the probe log in the launch transcript).

Coverage per the EXPLORER brief:
- Chained subsetting: skip().take().tail(), skip().skip(), take().take(),
  skip(n).first(), tail().tail(), take(3).tail(), skip(count-1), skip(150/200).
- first()/last() on empty, singleton, 200-element collections; nested
  first().first(), last().tail().
- Indexer: computed (1+1, 2*2, count-3, count), negative bounds (0-1, -0,
  0-1e9), out-of-range (count, 1e9), iif()-computed indexes, {}[0],
  (1|2|3)[1], wrong-typed a[1.0].
- single(): 0→empty, 1→value, 2+→error→wrapper empty, after where()/skip()/
  take()/ofType reduction, {}.single().first(), (a|a).single().
- Combiners with nested collections and mixed resources: nested.tags union/
  combine, select(tags) flattening counts, mixed ofType(Patient) exclude/
  intersect, patients name.given/family select+combine.
- combine() flattening depth vs select(): repeat(item).select(v) vs
  select(item | item.v); combine(select(...), select(...)) counts.
- Combiners vs repeat() fixpoints: repeat(item).select(v) ∘
  union/combine/intersect/exclude/skip/take — all dedup/terminating correctly.
- Temporal/quantity equality through combiners at odd precisions: Date
  partial precision (@2020-01 vs @2020-01-01), DateTime/Times, cm/mm, kJ/J
  derived units (FP-02), integer vs decimal (1 vs 1.0).
- Boundary numerics: skip/take(0, negative, 1e9), huge collection
  first/last/index.
- Self-referential and root-context `other` operands: a.intersect(a.skip(0)),
  a.exclude(a), first().exclude(first()).

## Findings

ZERO parity diffs, ZERO spec violations. No issues filed.

Doctrine confirmations (do not "fix"):
- `tail()` is zero-arg (§5.3.4, equivalent to skip(1)); `tail(n)` is wrong
  arity → is_valid=False + empty on BOTH surfaces (consistent with the
  wrong-arity-invalid doctrine; distinct from wrong-TYPE args which are
  valid execution-type errors per the FP-05 SKEPTIC fix).
- skip(num<=0) returns the input collection; take(num<=0) returns empty;
  take/skip beyond length clamp; out-of-range/negative indexers return empty.
- union/intersect dedup via `=` equality (incl. 1=1.0, 1 'cm'=10 'mm',
  1 'kJ'=1000 'J', partial-precision Dates stay distinct); exclude/combine
  preserve duplicate occurrences of remaining items.
- single() 2+ → execution error → DuckDB wrapper empty; 0 → empty (N1).
- Result ordering from intersect/union is unspecified; counts pinned where
  deterministic.

## Validation

Full conformance suite: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
DQM 47) — baseline held. No code changes made.

Recommendation: clean exit; chunk FP-05 §5.3/§5.4 is conformant after the
prior SKEPTIC is_valid fix.
