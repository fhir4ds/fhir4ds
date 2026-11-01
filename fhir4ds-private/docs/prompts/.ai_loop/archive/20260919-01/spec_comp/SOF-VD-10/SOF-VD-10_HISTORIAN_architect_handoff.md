# Architect Handoff — SOF-VD-10 HISTORIAN (2026-08-23)

## Structural audit scope
Chunk-scoped audit of the ViewDefinition validation surface
(`fhir4ds/viewdef/{parser,types,errors}.py`) against the golden standard
already pinned by SOF-VD-01..09 doctrine: strict parser boundary wrapping
types.py ValueError validators into typed ParseError; data-driven registries
(no resource-type branching); official validator + SD as canonical truth;
fixtures outrank prose.

## Findings
- Boundaries clean: every strict-path rejection observed this launch is a
  typed `ParseError` (SQLOnFHIRError/ValueError subclass); no raw stack
  traces on deeply multi-fault VDs; error messages consistently name the
  offending field and cite the invariant.
- Validation-order is coherent (resource → select tree → constants → joins
  → where → name → profiles); a single deterministic error surfaces per
  parse. No ordering-dependent acceptance.
- No silent fallbacks or test-driven hacks found in the chunk surface.
- One real (LOW) drift: numeric representation asymmetry across parse entry
  points — dict input keeps author-side float, JSON-string input yields
  Decimal, and `to_dict()` emits Decimal (QA-001). Documented as doctrine;
  recommend a future chunk introduce a Decimal-aware serialization API if a
  production consumer needs `json.dumps(to_dict())`.

## QA quality gate
QA was NOT lazy: HISTORIAN launched fresh probes beyond the SKEPTIC sweep
(official validator re-fetched from source, constants oneOf/tag schema
conformance, maximal-VD round-trip, ballot-scope check, validation-order
interactions). No veto. RETRY_QA remains false.

## Issue summary (all terminal)
- QA-001 LOW DEFERRED — Decimal in Constant.to_dict / json.dumps TypeError.
- QA-002 LOW INTENDED — valueInteger 3.0 stricter rejection.
- QA-003 LOW INTENDED — select.where/repeat doctrine re-confirmed.

## Compression
QA (33+13 assertions + round-trip + dual-engine probes): validation surface
spec-compliant; 0 CRIT/HIGH/MED. Engineer: no code changes; both gates hold
(ViewDef 1227/1227 pytest; conformance 2832/2832 incl. ViewDef 144/144;
binary md5s unchanged and repo==site-packages). Clean exit at iteration 1
(min_iterations=1, zero non-terminal CRIT/HIGH/MED).

## Recommended Fix Order
None for this chunk. Optional future chunk: Decimal-aware ViewDefinition
JSON serialization API (QA-001).
