# QA Handoff — FP-12 SKEPTIC, iteration 1 (2026-08-17)

Chunk: FHIRPath §5.8 Tree Navigation + §5.9 Utility Functions
(children, descendants, trace, now, today, timeOfDay).
Personality: SKEPTIC. Probe: `/mnt/d/fhir4ds/.temp/qa/fp12_skeptic_2026_08_17/probe.py`
(57 dual-path evaluation cases + 13 is_valid cases), dual-path doctrine
(native extension vs forced Python fallback, both via `SELECT fhirpath(?, ?)`).

## Verified clean (parity + spec, no action)

- `children()`: key-order traversal, arrays flattened in array order,
  `resourceType`/`_`-props skipped, **null children preserved**
  (`contact[0].name.children()` → `['Doe', null, 'Jane']`, count 3) in BOTH
  engines (GLOBAL_RULES invariant holds). Primitives/empty → empty. Root
  children include null-valued properties (`address`, `deceasedBoolean`).
- `descendants()`: recursive BFS expansion; equals native; iterative
  work-queue parity; `descendants().select(value)` works on mixed trees.
- `trace(name[, projection])`: pass-through unchanged (`.first().family`
  intact), both forms log via print and return input; `$this.given`
  projection scope restored; missing/non-string name → empty on both
  (error at wrapper); `trace('x', 1/0)` logs `[]` and passes through;
  empty input → empty; root-focused `trace('x')` traces the resource.
- `now()/today()/timeOfDay()`: within-expression determinism (`= ` self
  true), types (is DateTime/Date/Time), precision shapes
  (`now` → `YYYY-MM-DDTHH:MM:SS±HH:MM` second precision, `today` →
  `YYYY-MM-DD`, `timeOfDay` → `HH:MM:SS.fff`), `now() > @2020-01-01` true,
  Date-vs-DateTime cross comparisons empty, arity errors → empty identically,
  resource-chained `Patient.now()` works, toString regex anchors pass.
- `fhirpath_is_valid` parity (single-arg form): all 6 functions valid;
  `trace()`, `trace(1)`, `children(1)`, `descendants('a')`, `now(1)`,
  `timeOfDay(1,2)` invalid on both surfaces.
- Direct helpers exist for now/today/timeOfDay (`DateTimeFunctions`).

## Issues filed

- **QA-001 (HIGH, PARITY/SPEC): fallback `parse_value` collapses unitless
  Quantity-typed wrappers to None → equality True.**
  `component.children()[0] = component.children()[1]` over
  `[{valueQuantity:{value:120}},{valueQuantity:{value:80}}]` → fallback
  `['true']` vs native `['false']`; consequence: `repeat(children()).count()`
  11 vs 15 (= `descendants().count()`), breaking the §5.8.2
  descendants ≡ repeat(children()) invariant and over-deduplicating in
  repeat/distinct/contains paths. Root cause:
  `fhir4ds/fhirpath/engine/util.py::parse_value` returns
  `parse_complex_value(...)`'s None directly for Quantity-typed nodes
  without unit/code.
- **QA-002 (MEDIUM, API_GAP): exported helper module has no
  children/descendants/trace** — 8th instance of the "exported helper API
  forgotten" family (§5.9.2 helpers do exist in `DateTimeFunctions`).
