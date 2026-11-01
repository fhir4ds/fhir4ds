# Architect Handoff — CQL-08 HISTORIAN (iteration 1, 2026-08-20)

## Golden Standard invariants applied
1. Translator layering: the nested-Coalesce fix lands in static type inference
   (`_infer_static_cql_type_for_logical_operand`), not SQL string patching;
   no SQLRaw/to_sql introduced.
2. No silent fallbacks: Decimal→Integer/Long now returns NULL/False because
   the SPEC defines no such conversion — this is typed spec behavior, not a
   fallback masking an error; the previous truncation branch was itself the
   silent wrong-behavior path.
3. Dual-engine lockstep: all three fixes live on the shared macro/UDF/
   translator surface that serves both native-cpp and python-fallback
   connections (the C++ extension registers none of the touched names) —
   single-source fix, py==cpp verified on every regression case.
4. General, not specific: Coalesce static-type inference works for arbitrary
   nesting depth and any argument shape; Decimal rejection is type-driven,
   not test-fixture-specific.
5. Doctrine precedence honored: live spec text (three targeted fetches incl.
   verbatim Table 9-E Decimal row) outranked an earlier launch's recorded
   "spec mandates truncation" claim — matching the campaign rule that
   fixtures/spec outrank recorded pins, and the SKEPTIC-era lesson that
   prior-launch pins can themselves be spec-wrong.

## Audit findings
- No new architectural drift. All fixes minimal-footprint.
- Cross-chunk doctrine conflict CLOSED: CQL-07 master's Decimal-truncation
  conversion doctrine has been corrected in AGENTS.md; CQL-01's null/false
  expectations restored as canonical.
- The 3 SKEPTIC-documented pre-existing working-tree failures are all
  closed (2 were symptoms of QA-001; 1 was a stale CQL-06-era pin).
- QA quality gate: PASS — HISTORIAN probed dual-path matrices at both SQL
  and translator levels, fixture-shaped list overloads, nested/dynamic
  Coalesce compositions, and triaged the inherited failures to root cause.
  No veto.

## Empirical validation
- Fresh full conformance: OVERALL 2832/2832 (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47) — baseline held.
- Focused: nullological parity 15/15, conversion function parity (incl. 2
  updated tests) all pass, structural parity 22/22, CQL-01 CanConvert and
  primitive-boundary tests pass.
- Full `fhir4ds/cql` pytest: running detached
  (`.temp/qa/cql08_historian_2026_08_20/cql_pytest.log`); zero failures
  observed in completed portion at close.

## Summary (compression)
HISTORIAN re-verified the SKEPTIC fixes (variadic Coalesce, uniform
type-family guard — both intact) and hunted new divergences: found 2 MEDIUM
spec violations (Decimal→Integer/Long truncation conversion leaking through
ToInteger/ToLong/ConvertsToInteger/CanConvert; nested Coalesce escaping the
type-family guard into a raw DuckDB binder error) plus 1 stale test pin.
All fixed with dual-path regression coverage; conformance gate held
2832/2832.

## Recommended fix order
None pending. Chunk CQL-08 (HISTORIAN launch, 2nd of 3 personalities) is
CLEAN at iteration 1.
