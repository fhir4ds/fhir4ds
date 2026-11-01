# QA Handoff — CQL-17 SKEPTIC iteration 1 (2026-08-22)

Fresh SKEPTIC pass over CQL Interval Operators Part 3 (Point From, Properly
Includes/Included In precision, Same As/Same Or After/Before precision
(Interval), Size, Start of, Starts precision, Union, Width of), probed via
translation + DuckDB execution across all three engine modes (Python
supplements, native+supplements, no-Python native). Probe artifact:
`.temp/qa/cql17_skeptic_2026_08_22/probe.py` (33 translated cases).

Prior CQL-17 SKEPTIC/HISTORIAN/EXPLORER coverage (2026-07-02) re-validated
clean: union adjacency at successor steps (int/decimal 1e-8/date/day/hour/
month), disjoint union → null, open-bound union containment exclusion,
Starts precision both conjuncts (end-beyond false, end-equal true,
start-diff false), Same Or After/Before equality edges (true), properly
includes strictness with open bounds and equal intervals, point from
Quantity/Date unit intervals, Long MIN..MAX size (2^64-1 exact), temporal
Width/Size raising per spec.

## New findings (all in evolution.json)

- QA-001 HIGH — `(null as Interval<Integer>) union Interval[1, 5]` lowers to
  LIST union (jsonConcat) and raises BinderException on valid CQL; typed-null
  on both sides returns `[]` not null. Violates CQL §19.31 (null → null).
  Root cause in `_translate_union_op` (translator/expressions/_operators.py:4047):
  interval routing requires BOTH operands recognized; the null-CASE lowering
  of `null as Interval<T>` is neither interval-recognized nor an SQLNull.
  NOTE: intersect/except/properly-includes already handle this operand shape.
- QA-002 MEDIUM — `start of Interval[1 'g', 3 'g']`: Python path returns
  Python dict repr (invalid JSON); no-Python native returns valid JSON.
  Root cause `_raw_closed_bound` (udf/interval.py:610) str()s dict bounds.
- QA-003 MEDIUM — `width of Interval[1 'g', 2000 'mg']`: Python
  `intervalWidth` quantity output omits `"system"` field that `interval_size`
  and native include (HISTORIAN fixed Size only; Width missed).

Phase advanced to FIX. Reproducers are the probe lines above.
