# QA Handoff — CQL-17 HISTORIAN (2nd launch) iteration 1 (2026-08-22)

Fresh HISTORIAN pass over CQL Interval Operators Part 3 (Point From,
Properly Includes/Included In [precision], Same As/Same Or After/Or Before
[precision] (Interval), Size, Start of, Starts [precision], Union, Width of),
probed via translation + DuckDB execution across all three engine modes
(Python supplements, native+supplements, no-Python native). Probe:
`.temp/qa/cql17_historian2_2026_08_22/probe.py` (28 translated defines +
16 direct UDF cases) plus three follow-up scripts run inline.

Institutional memory applied: CQL-16 lesson "probe MIXED POINT TYPES on
interval bounds" was the decisive lever — it exposed QA-001/QA-002/QA-003.

## SKEPTIC fix re-verification — all 3 hold

- Typed-null `(null as Interval<T>) union X` → null on all engines (QA-001).
- `start of Interval[1 'g', 3 'g']` → valid JSON (QA-002).
- Width Quantity output includes UCUM system (QA-003).

## New findings (in evolution.json)

- QA-001 HIGH — `same as` (Interval, no precision) with Decimal bounds:
  Python engine RAISES ValueError (int('1.0') inside cqlDateTimeEqual →
  `_parse_components`, udf/datetime.py:1668); native/no-Python return NULL.
  Expected True (§19.27). Integer intervals work only by accident of the
  datetime parser reading '1' as year 1. Root cause: `_temporal_comparisons.py`
  lowers interval start/end equality to `cqlDateTimeEqual` regardless of
  point type.
- QA-002 HIGH — `same or after`/`same or before` (Interval, no precision)
  with Decimal bounds → NULL on all engines (§19.28/§19.29 expect True).
  Same root cause family: temporal UDF lowering on numeric intervals.
- QA-003 MEDIUM — native `intervalWidth`/`interval_size` return NULL for
  mixed Integer/Decimal bounds (`width of Interval[1, 5.5]` → NULL on
  no-Python engine; Python correct 4.5). Root cause: interval.cpp
  width_string/size_string switch on bound_type (from LOW bound) requires
  both bounds of that numeric type; cross-type fallback missing (CQL-16
  QA-002 precedent fixed compare only). Pure decimal/integer paths OK.
- QA-004 MEDIUM — `start of`/`end of` Quantity intervals emit
  {"value","unit"} without "code"/"system" while Width/Size emit the full
  UCUM canonical Quantity JSON — the exact inconsistency class SKEPTIC
  QA-003 fixed for Width. Root cause: native `quantity_json_for_bound`
  minimal shape; Python passthrough mirrors it. Dual-engine lockstep fix.

## Verified CLEAN (not re-logged)

- width/size of unbounded intervals → null (spec example §19.25 holds).
- start of closed-null Integer low → -2147483648: CORRECT (CQL Integer is
  signed 32-bit; earlier probe expectation of 64-bit min was wrong).
- properly includes point overload strictness (unit interval → false).
- Starts open-low false / end-beyond false / null-right null.
- Same As mixed Date/DateTime intervals implicit conversion → true.
- Time-interval `same hour as` true/false edges.
- Union decimal successor-step adjacency + gap; reversed adjacency.
- Quantity union cross-unit overlap composes correctly (bounds keep their
  authored units — heterogeneous-unit result registered NOT A BUG, see
  AGENTS.md).
- Same-or-after with timezone offsets evaluates by normalized instant.

Phase advanced to FIX. Point From non-unit silent-null remains the
registered DEFERRED case (not re-logged).
