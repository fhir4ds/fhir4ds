# Architect Handoff — CQL-09 Comparison Operators (HISTORIAN, iteration 1)

## Summary
QA (HISTORIAN) probed §9 surfaces the SKEPTIC pass did not reach — uncertainty
propagation through `!=`/`!~` over uncertain composites, nested lists,
tuples-in-lists, Time-type and mixed-precision ordered comparisons, string
lexical ordering, quantity/code/concept corners — ~75 dual-path cases with
zero native-vs-Python parity divergence, and re-verified both SKEPTIC fixes
intact. Two genuine MEDIUM spec violations of the same 3VL-erosion class were
found and fixed: (QA-001) nested-list equality collapsed one-sided-null
uncertainty to false (`{{1,null},{2}} = {{1,2},{2}}` → false, spec null),
fixed with new `CQLNestedListEq{Elem,Temporal}` + subquery-free
`CQLJsonEq{Elem,Temporal}` leaf comparators wired into the
`CQLListEqual{Eq,TemporalEq}` element CASE; (QA-002) tuple list elements
compared via raw JSON equality (`{Tuple{a:1,b:null}} = {Tuple{a:1,b:2}}` →
false, spec null), fixed with the new `CQLTupleValueEqual` field-wise-3VL
macro routed from `CQLListElementEqual` after the clinical/interval/quantity
branches. Both fixes are SQL-macro-only and therefore shared by both engine
registrations (no extension rebuild; both paths re-verified). QA-003 (LOW,
INTENDED) pins the null-code `Code =` doctrine; QA-004 (LOW, DEFERRED)
documents the uncertainty-preserving boundary for clinical objects at list
depth ≥ 2 and >2-level nesting (exact semantics would require a recursive
native/Python list-equal function; DuckDB macros cannot recurse — errors are
always toward null, never definitely wrong).

## Issue counts
SPEC_VIOLATION: 2 (both VERIFIED). SPEC_AMBIGUITY: 2 (INTENDED, DEFERRED).
Architecture drift: 0 — fix honors dual-engine lockstep, pinned doctrines
(contains/except/distinct, interval open-null unbounded, clinical display
semantics untouched), no silent fallbacks (conservative boundary documented in
AGENTS.md), no fixture-specific hacks. Golden-standard notes at
`.temp/architect/golden_standard_cql09_historian.md`.

## QA quality gate
Sufficient — no veto (RETRY_QA false). QA covered the chunk mandate items on
both engine paths, hunted beyond the prior launch's probes, and correctly
discarded its own false-positive expectations against fetched §9 text.

## Validation evidence
New parity regression test (13 cases × 2 backends); comparison parity suite
14/14; list suites 76/76; SKEPTIC probes re-run clean; full conformance gate
2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — baseline held.

## Recommended fix order
None — no open CRITICAL/HIGH/MEDIUM issues remain. Clean exit at
min_iterations=1.
