# QA Handoff — FP-12 EXPLORER iteration 1 (2026-08-17)

Personality: EXPLORER (fuzzer/abuser). Chunk: FHIRPath §5.8 Tree Navigation,
§5.9 Utility Functions. Probe: `.temp/qa/fp12_explorer3_2026_08_17/probe{,2,3}.py`
(123 dual-path evaluation cases + 8 is_valid checks).

## What was probed

- children()/descendants() chained with ofType/is/type() on deeply nested
  BackboneElements (Questionnaire.item recursion incl. EQUAL duplicate
  subtrees) and choice-type fields (value[x] matrix: string/integer/boolean/
  dateTime/CodeableConcept/Period/Quantity, all 6 ofType(FHIR.*) cases parity-ok).
- descendants() on a 60-element wide tree with identical display values
  (dedup collisions: 122 descendants both engines; select(display).where = 60).
- descendants() ≡ repeat(children()) identity re-verified (count 20 = 20 on DEEP).
- trace(): pass-through identity, projections defining variables
  (trace('t', defineVariable('v',1).select(%v))), nested traces
  (trace-in-projection, trace chains), name validation ('' / 123 / missing /
  3-arg arity — all error → empty identically; '' still logs).
- now()/today()/timeOfDay(): determinism (= self true), arithmetic chains
  ((now()+1 year) > today() true; (today()+1 day) > today(); (today()-100y)
  < today(); (now()+10 min) > now()), iif integration, toString shapes.
- children() on primitives with extensions (value-carrying birthDate +
  value-less _deceasedBoolean companion): counts parity-ok (11 descendants).
- descendants() ∘ where/select/repeat from earlier chunks.
- is_valid (single-arg form): trace arity/name forms — parity ok.

## Findings (2 filed, see evolution.json)

- QA-001 (HIGH): fallback loses FHIR typing on recursive nested paths
  (`item.item.type()` → 'object', should be BackboneElement; native correct)
  and choice-suffixed nested paths (`component.valueCodeableConcept.coding
  .ofType(FHIR.Coding)` → 0; native 1). Breaks the §5.8-ofType composition
  the spec itself recommends. Also a same-family ofType(FHIR.string) count
  divergence (4 vs 7 on DEEP) while where(is(FHIR.string)) agrees at 14.
- QA-002 (MEDIUM): native fails to type `extension` array elements
  (`extension.type().name` → 'object', `extension.ofType(FHIR.Extension)` → 0;
  fallback correct). is(FHIR.Extension) works in both — the declared-type
  metadata path is the gap.

## Verified clean (do not "fix")

- Null-child preservation, wide-tree dedup, trace scope restoration,
  now/today/timeOfDay precision/offset shapes (all prior-launch doctrines hold).
- `.sum()` chain divergence (native continues with empty, fallback errors
  whole expression) = pre-existing documented FP-02 EXPLORER QA-004 LOW
  DEFERRED doctrine; not re-filed.
- `now() >= today()` → empty (DateTime vs Date comparison, correct).

## Probe traps honored

PYTHONPATH=/mnt/d/fhir4ds; native conns assert register() is True with
allow_unsigned_extensions; fhirpath() serializes Integers as strings.
