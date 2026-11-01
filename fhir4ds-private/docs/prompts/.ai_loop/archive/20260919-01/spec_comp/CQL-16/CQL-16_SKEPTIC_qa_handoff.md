# QA Handoff — CQL-16 SKEPTIC iteration 1 (2026-08-22)

**Chunk**: CQL 1.5 Interval Operators Part 2 (Included In [prec], Intersect (Interval),
Meets/before/after [prec], Not Equal / Not Equivalent (Interval), On Or After/Before
[prec] (Interval), Overlaps / Overlaps Before / Overlaps After [prec]).

**Method**: 129 dual-engine probes (native C++ DuckDB registration vs forced Python
fallback) at `.temp/qa/cql16_skeptic_2026_08_22/probe1.py` (89 literal/precision/
open-bound/LIST_EXTRACT cases) and `probe2.py` (40 null-bound sentinel, temporal
null-bound, precision meets before/after, Quantity, Time-interval, incompatible
Quantity dimensions, `in`-keyword cases). Expected values re-derived from live
cql.hl7.org 09-b normative text AND the cqframework reference engine sources
(Interval.kt start/end getters, IntersectEvaluator.kt, MeetsEvaluator.kt,
OverlapsEvaluator.kt, IncludedInEvaluator.kt, SuccessorEvaluator.kt).

**Findings — 4 issues, all dual-engine (py/cpp parity throughout; 0 disagreements)**:

- QA-001 HIGH — `Interval[2, 3] in Interval[1, 5]` (interval-interval `in`) raises
  DuckDB BinderException (VARCHAR/INTEGER mix in BETWEEN) on both engines. Spec
  grammar accepts `in` between intervals (Included In interval-interval overload);
  reference engine routes it through includedIn.
- QA-002 MEDIUM — Intersect builds its result from RAW low/high fields instead of
  effective Start/End boundaries: `(Interval[1,5] intersect Interval[null,3])
  contains -5` → false; reference (spec §9.14 Start: closed null low → minimum of
  point type) yields result low = min sentinel, so contains -5 → true.
  `intervalStart(Interval[null,3])` alone already returns -2147483648 correctly.
- QA-003 MEDIUM — Null CLOSED bounds do not sentinelize in Meets / On Or After /
  On Or Before / Overlaps([null,null]): all return null where spec Start/End
  semantics (min/max of point type) produce determined false/true. Cases:
  MeetsNullHigh/Low, MeetsTemporalNullHigh, OnOrAfterNullLow/High,
  OnOrAfterTemporalNullHigh, OvBothNull (probe2.py).
- QA-004 MEDIUM — Meets over Quantity intervals returns false; successor for
  integer-valued Quantity bounds is not implemented (spec Appendix C Successor:
  Quantity successor = +1·precision, units unchanged). Decimal-valued quantity
  successor already works. Previously deferred out-of-scope (2026-07-02 doctrine);
  now explicitly in this chunk's mandate.

**Verified-clean surfaces** (no action): included-in basic/precision/open-bound;
intersect overlap/nested/disjoint/adjacent/open-touch shapes (reference returns
CLOSED effective-bound intervals — our JSON output `{"low","high","lowClosed":true,
"highClosed":true}` matches reference `Interval(max, true, min, true)`); meets
Integer/Date/DateTime-ms/precision-qualified + meets before/after directionality;
on-or-after/before boundaries incl. open-bound adjacency + precision + Time
intervals; overlaps family incl. open-bound adjacency ([1,5) overlaps [5,10] →
false), precision forms, overlaps-before/after bound conjuncts; Not Equal /
Not Equivalent null propagation (Neq(null-operand) → true, both-null → false);
incompatible Quantity dimensions → NULL for overlaps/overlaps-before/intersect
(meets → false: quantity equality across dimensions is false, acceptable);
LIST_EXTRACT-derived interval operands through all families (CQL-15 recognizer
covers these operators); temporal null-high overlaps unbounded semantics.

**Probe-expectation errors (NOT bugs)**: OnOrBefore_OpenHighTouch (effective start
of open (1,5) is 2 → false correct), OvB_OpenBound (effective start of (0,5] is 1 →
true correct), ListSel_Indexer (CQL indexing is 0-based), intersect open-flag
"preservation" (reference returns closed effective bounds — our output correct).

State: evolution.json phase=FIX, 4 OPEN issues.
