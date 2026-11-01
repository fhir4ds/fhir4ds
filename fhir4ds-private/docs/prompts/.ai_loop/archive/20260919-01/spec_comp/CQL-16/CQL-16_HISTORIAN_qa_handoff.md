# QA Handoff — CQL-16 HISTORIAN iteration 1 (2026-08-22)

**Chunk**: CQL 1.5 Interval Operators Part 2 (same mandate as SKEPTIC launch).

**Method**: 4 dual-engine probe batteries (~110 cases) at
`.temp/qa/cql16_historian_2026_08/probe{1..4}.py`: SKEPTIC-fix regression
re-verification, `in` precision keyword + `during` synonyms, Long/Decimal
null-bound sentinels, unbounded temporal intersects + `"Measurement Period"`
parameter indirection, Time intervals through all families, meets
before/after precision grammar forms, Not Equal/Not Equivalent null/open
bounds, overlaps precision/mixed precision, Quantity null bounds,
LIST_EXTRACT operands with precision. Expectations verified against live
reference engine sources fetched this session (Interval.kt start/end getters,
OverlapsEvaluator.kt, MinValueEvaluator, Constants.kt from
cqframework/clinical_quality_language@main).

**Findings — 2 NEW issues, both dual-engine (0 py-vs-cpp disagreements)**:

- QA-001 MEDIUM — Long intervals with closed null bounds sentinel at int32
  limits instead of int64: `end of Interval[5000000000L, null]` → 2147483647
  (ref Long.MAX); meets/on-or-before produce wrong determined `true` where
  reference gives null/false. Root: `_cql_minimum/maximum_for_peer_bound`
  (udf/interval.py) int branch + native interval.cpp sentinel mirrors.
- QA-002 MEDIUM — Quantity intervals with closed null bounds: reference
  sentinels to Quantity(MIN_DECIMAL/MAX_DECIMAL, unit); ours returns None →
  null instead of determined results (`Interval[1 'g', null] on or before
  Interval[2 'g', 3 'g']` → null vs ref false; `Interval[null, 4 'g'] meets
  Interval[5 'g', 6 'g']` → null vs ref false; `start of Interval[null,5 'g']`
  → null vs ref Quantity sentinel).

**SKEPTIC-fix re-verification (all clean)**: interval-interval `in`
(true/false/open/sticks-out/null-low), null-bound sentinels in
meets/meets-before/on-or-after/on-or-before incl. temporal overflow →
false/null per Appendix C. Extension binaries md5-matched
b9164ff5254bc5944d86109dd5e2cf94 (repo bundle + site-packages) pre-fix.

**Verified-clean surfaces**: `in`/`during` precision forms (incl. point-in-
interval and null-high precision included-in); unbounded temporal intersect
effective bounds (`Interval[@2024-01-01, null] intersect Interval[...]` →
correct closed effective interval; contains probes pass); Measurement-Period
parameter indirection through intersect/overlaps/overlaps-before/
included-in/meets/on-or-after; Time intervals across all chunk families incl.
precision; plain meets before/after; Not Equal/Not Equivalent (equal → false,
differing → true, closed-null bound → null for !=, → true for !~,
open-vs-closed → true); overlaps precision (day/month, mixed precision,
overlaps-before/after precision); Decimal null-bound on-or family; one-sided
null overlaps (true/false determined correctly).

**Probe-expectation errors (NOT bugs)**: integer literals > int32 need `L`
suffix (ValueError otherwise is correct Integer typing); Decimal successor
step is 1e-8 so `Interval[null,1.5] meets Interval[1.6,5.0]` false is correct
(pinned CQL-16 SKEPTIC doctrine); `Interval[null,null] overlaps ...` → null is
reference-consistent (point type uninferrable → Interval<Any> → minValue(Any)
null); my D_Param harness MP-reference bug (parameter must be referenced by
name — retried, all pass).

State: evolution.json phase=FIX, 2 OPEN MEDIUM issues.
