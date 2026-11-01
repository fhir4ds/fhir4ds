# QA Handoff — CQL-17 EXPLORER (3rd launch, 2026-08-22)

## What was probed
Fresh three-engine sweep (Python supplements, native+supplements, no-Python)
via `.temp/qa/cql17_explorer3_2026_08_22/probe.py` — 60 translated defines
plus direct-UDF exploration, targeting the EXPLORER mandate corners:

- Properly includes / properly included in strictness at exact-bound equality
  across every open/closed combination (int, decimal, Date, Quantity, point
  overload, unit intervals): ALL CORRECT (effective Start/End bounds + "not
  the same interval" honored; [1,5] PI [1,5) true, [1,5) PI [1,5) false, etc.)
- Same as / same or after / same or before [precision] at differing operand
  precisions: correct (AND(null,false)=false semantics; month-precision end
  vs day-precision operand correctly resolves false at month, uncertain day
  start propagates null only when no determined conjunct).
- Union chains with mixed adjacency (left-assoc null propagation): correct.
- Union at successor-adjacent open bounds for decimal 1e-8 and temporal ms:
  correct (adjacent merges; one-step 1e-8 gap null; ms gap null).
- Size/Width of temporal intervals: typed "not defined ... use duration in"
  error per spec note (§19.18/§19.25), consistent on Python + native.
- Width vs Size at every type incl. open bounds and mixed int/decimal:
  correct (Size = width + point-size; Quantity point-size = 1e-8).
- Point From unit intervals of each type incl. open (2,3)->null, [4,5)->4:
  correct (null-on-non-unit is the documented DuckDB-surface boundary).
- Start of closed-null min-sentinel intervals feeding arithmetic: FOUND QA-001.
- Starts/ends feeding boolean chains with overlaps and day precision: correct.
- Re-verified all 7 prior SKEPTIC/HISTORIAN fixes: all hold.

## Issues
- QA-001 HIGH (CONFIRMED): arithmetic over interval-derived scalars
  (`start of`/`end of`/`width of` numeric intervals) misroutes: integer +
  integer literal lowers to dateAddQuantity(..., 1 'year') -> NULL; decimal
  or width cases hit raw SQL '+'(VARCHAR, x) -> BinderException on valid CQL.
  CQL §19.19 Start returns the point type; numeric add must be numeric.
  Same on all three engines (translator dispatch, not engine divergence).
- QA-002 MEDIUM (CONFIRMED): width/size overflow beyond the Integer point-type
  range returns out-of-range BIGINT values instead of null
  (width of Interval[-2147483648, 2147483647] -> 4294967295; Size -> 4294967296).
- QA-003 LOW (UNCONFIRMED): point from non-unit interval returns null, spec
  says run-time error; documented DuckDB-surface boundary, flagged for human.

## Not-a-bug registry additions
- `same day as` interval with uncertain start (null) and known-different end
  (false) resolves to false via three-valued AND, not null.
- `same or before` interval compares END of left vs START of right (§19.29).
- Size(Interval[1 'g', 3 'g']) = 2.00000001 (Quantity point-size is the
  Decimal 1e-8 step, matching the reference successor doctrine).
- Time interval bounds serialize with the 'T' prefix in interval JSON.

## Notes for FIX
QA-001 root cause is in translator arithmetic dispatch (+/-) over
interval-helper SQLExpressions whose static point kind is numeric; the
HISTORIAN `_numeric_interval_point_kind` fix covered same-as family only.
QA-002 needs range checks in intervalWidth/interval_size (Python + native
mirror) keyed on the interval point type inferred from bounds.
