# QA Handoff — FP-12 HISTORIAN, iteration 1 (2026-08-17)

Chunk: FHIRPath §5.8 Tree Navigation + §5.9 Utility Functions.
Personality: HISTORIAN. Probe: `/mnt/d/fhir4ds/.temp/qa/fp12_historian_2026_08_17/probe.py`
(58 dual-path evaluation cases) + drill probes.

## Prior SKEPTIC fixes re-verified (regression-free)

- QA-001 (parse_value None sentinel): unitless Quantity equality restored on
  fresh data — `repeat(children()).count()` = `descendants().count()` = 16 on
  a fresh duplicate-bearing tree; duplicate-object equality true; distinct
  counts match.
- QA-002 (navigation.py helpers): children preserves nulls + key order,
  descendants dedups correctly, trace passes through, all verified by direct
  import and engine probes.

## Verified clean (parity + spec, no action)

trace name-surface, projection scope in where/select/repeat, error pass-through,
empty corners, root trace identity; now/today/timeOfDay determinism inside
iteration (`select(now() = now()).all(true)`), types, precision shapes,
cross-type comparisons empty, ordering vs static dates, chained iif; children
key-order/first/last, null preservation counts, contained resources,
resource-type-prefixed children/descendants, is_valid parity (single-arg form;
2-arg is a Binder error — pinned doctrine).

## Issues filed

- QA-001 (MEDIUM, PARITY): native fn_children drops field_name/fhir_type
  metadata → ofType(FHIR.string)/FHIR.code/FHIR.id/Quantity on children()
  diverge from direct navigation and from fallback (which is model-correct).
- QA-002 (MEDIUM, PARITY): Quantity-typed child = Integer → native false,
  fallback empty; native inconsistent with its own `= 120 '1'` (empty).
  Likely consequence of QA-001.
- QA-003 (MEDIUM, fallback): `.toString()` on a preserved null child returns
  `'None'` (Python repr leak) in core+fallback; native empty.
- QA-004 (LOW, fallback): nested-array JSON crashes fallback
  children/descendants with AttributeError (int dict keys from list->dict
  conversion); native returns counts without error.
