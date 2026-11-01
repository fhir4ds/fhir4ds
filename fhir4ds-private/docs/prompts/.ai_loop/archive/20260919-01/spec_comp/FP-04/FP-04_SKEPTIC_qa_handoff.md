# FP-04 SKEPTIC QA Handoff (iteration 1, 2026-08-17)

Chunk: FHIRPath N1 §5.2 Filtering and Projection — where(criteria),
select(projection), repeat(projection), ofType(type). Spec text fetched
from https://hl7.org/fhirpath/N1/index.html (§5.2.1-§5.2.4, §6.3.1,
§6.3.3) plus build.fhir.org FHIRPath override notes (ofType concrete
core types only; primitives independent; Quantity covers
SimpleQuantity; `is(System.String).not()` example; "FHIR.string is a
different type to System.String").

Method: dual-path probes (native extension vs Python fallback, 6 result
channels each) run with `PYTHONPATH=/mnt/d/fhir4ds`, batteries in
`/mnt/d/fhir4ds/.temp/qa/fp04_skeptic_2026_08_17/` (probe.py 61 cases,
probe2.py 23 cases, probe3 21 repeat/dedup/primitive-ofType corners,
probe4 structural blast radius).

## Pre-registered SKEPTIC hypotheses and outcomes
- H1 where() criteria strictness/empty/false handling, $index, original
  items — REJECTED (all 16 cases parity-correct and spec-correct;
  non-single-boolean criteria error in both, empty/false dropped,
  fixture analog `telecom.where(use='official').value` -> 555).
- H2 select() flattening, empty projection dropped, $index, spec's
  `where(use='usual').select(given.first() + ' ' + family)` example —
  REJECTED (all 10 parity-correct, Ann Smith).
- H3 repeat() fixpoint/dedup — REJECTED (ValueSet-style contains tree
  7 nodes both; questionnaire dedup of duplicate `q1` via `=`; identity
  repeat once; quantity-aware dedup `1 'cm'`/`10 'mm'` -> count 1 both;
  compose where/select).
- H4 ofType() — CONFIRMED as QA-001 (see below): FHIR resource types,
  FHIR primitives incl. exact subtype behavior (`id.ofType(FHIR.string)`
  empty in both — correct, primitives are independent types), Any, and
  choice-typed `value.ofType(Quantity)` all correct in both; divergence
  only for structurally-typed objects under unmodelled fields.
- H5 arity/is_valid controls — REJECTED (where()/select()/ofType()/
  repeat() arity errors invalid in both; `ofType('Patient')` string
  argument invalid in both).

## Issues logged (evolution.json)
1. QA-001 (MEDIUM, OPEN) — Native/fallback type-test divergence on
   unmodelled fields: `is Quantity`/`ofType(Quantity)`/`as Quantity`
   (plus CodeableConcept, Coding, Range, Period) native false/empty vs
   fallback true/value; native also blanket-infers BackboneElement for
   any object under a known field name (5 vs 0). Typed/choice fields
   unaffected. Root cause: Python nodes.py structural complex-type
   detection absent from native fn_isType.
2. QA-002 (LOW, INTENDED) — ofType(System.String)/is(System.String)
   non-matching on FHIR strings is spec-correct per the FHIR page's own
   `is(System.String).not()` example; both engines agree. Terminal.

Also verified (observations, no issue): `contained.select($this as
Patient)` behaves correctly (an earlier probe2 confusion was fixture
error — the first contained resource was an Observation); repeat()
order is implementation-defined per §5.2.3 and both engines agree on
all probes.
