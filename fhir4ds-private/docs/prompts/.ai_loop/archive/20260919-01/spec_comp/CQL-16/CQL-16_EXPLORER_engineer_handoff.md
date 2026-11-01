# Engineer Handoff — CQL-16 EXPLORER iteration 1 (2026-08-22)

## Triage
| Issue | Category | Triage | Terminal |
|---|---|---|---|
| QA-001 intersect effective bounds (native) | SPEC_VIOLATION | CONFIRMED → fixed | RESOLVED |
| QA-002 cross-numeric bound compare (native) | SPEC_VIOLATION | CONFIRMED → fixed | RESOLVED |

## QA-001 — native intersect ignored effective Start/End bounds
- Root cause: `Interval::intersect` (extensions/cql/src/cql/interval.cpp)
  computed min/max over raw low/high and propagated open flags.
- Spec: CQL 1.5 §9.9 via §9.14/§9.15; reference IntersectEvaluator.kt
  `new Interval(max, true, min, true)` over getStart()/getEnd().
- Fix: normalize open finite bounds through `successor_bound` /
  `predecessor_bound` (closed result) before the existing min/max; null-bound
  (closed-null sentinel / open-null unknown) branches untouched — mirrors the
  Python authority, which normalizes at `_parse_interval` time.

## QA-002 — native cross-numeric bounds incomparable
- Root cause: `BoundValue::compare` type gate returned -2 for Integer vs
  Decimal; no-Python native mode then produced NULL (meets, on or before/
  after, intersect) or WRONG FALSE (overlaps, included in, overlaps
  before/after, equivalence).
- Spec: CQL 1.5 §2 implicit conversions (Integer→Decimal).
- Fix: numeric cross-type comparison (long double; int64 exact against
  doubles within 2^53) before the type-mismatch gate, with Optional
  value-presence guards.

## Deployment & verification
- Extension rebuilt (cmake build/release), deployed to repo bundle +
  ~/.local site-packages; md5 **87e4f6e866bfbc7151eb42ff779c9fd1** verified
  identical across build output, bundle, site-packages; ~/.duckdb extension
  cache cleared. Fix re-verified through a fresh no-Python connection.
- Regression test:
  `fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py::
  test_cql_interval_part2_native_effective_bounds_and_cross_numeric_parity`
  (10 cases × py-fallback / native-loaded / no-Python).
- Focused: interval part1+2+3 parity + interval UDFs **97/97**; v2
  expressions + arithmetic-part2 + logical parity **221/221**; both EXPLORER
  probe batteries now show zero py/native/no-Python divergences.
- Master gate (final tree state, fresh run): ViewDefinition 144/144,
  FHIRPath 935/935, CQL 1706/1706, DQM 47/47 — **OVERALL 2832/2832**
  (baseline holds; no DQM ERROR retries needed).

## Files changed
- extensions/cql/src/cql/interval.cpp (2 fixes)
- fhir4ds/cql/duckdb/extensions/cql.duckdb_extension (rebuilt binary)
- fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py (new test)
- AGENTS.md, fhir4ds/cql/AGENTS.md (institutional memory)

No new issues discovered during remediation. Handing to ARCHITECT.
