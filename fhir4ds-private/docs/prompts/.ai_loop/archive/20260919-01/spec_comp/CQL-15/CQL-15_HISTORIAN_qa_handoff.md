# QA Handoff — CQL-15 (Interval Operators Part 1), iteration 1, HISTORIAN

## Scope tested
Chunk CQL-15 re-verified after the SKEPTIC launch's 4 fixes. ~100 dual-engine cases
(Python fallback + native C++ extension) beyond the SKEPTIC battery: After/Before
[precision] null/uncertain boundaries, Ends [precision] point-promotion and coarse
precision, Collapse per (temporal units, per 0/1/2, unsorted, decimal, Quantity,
incompatible, chain merges, null elements), Contains/In precision (month/year,
boundaries, mixed precision), End of (Decimal/Quantity/Time/open DateTime),
Equal/Equivalent (Quantity conversion, Decimal/Integer, open-null bounds), Except
(open/unbounded/partial-containment shapes), Includes [precision], Expand (open
intervals, per month/3/Quantity/hours/Decimal, list overload, unbounded).
Spec verified against cql.hl7.org 09-cqlreference and the HL7 reference engine
source (clinical_quality_language master: CollapseEvaluator.kt, InEvaluator.kt,
IncludedInEvaluator.kt, IncludesEvaluator.kt, ExpandEvaluator.kt — fetched live).

Probes: /mnt/d/fhir4ds/.temp/qa/cql15_historian_2026_08_21/probe1.py + inline drills.
SKEPTIC pins: test_interval_part1_parity 18/18 pass — all 4 prior fixes regression-free.

## Issues opened
- QA-001 HIGH: `collapse(X, per)` temporal per of value 0 or 1 does not perform the
  meets/overlaps decision at the per-unit precision. Reference CollapseEvaluator keeps
  the interval unextended for per 0/1 but passes `precision = per.unit` to
  Meets/Overlaps. Ours falls back to raw-bound successor, so
  `collapse { Interval[@2024-01-15, @2024-01-31], Interval[@2024-02-02, @2024-02-10] } per month`
  stays split (reference: merged to {[2024-01-15, 2024-02-10]}). Affects Python
  `collapse_intervals` (_extend_bound_by_per returning None for per 0/1 temporal) and
  native CollapseIntervalsPerFunc. `per 0 months` misses the same merge. per>=2
  (numeric extension path) is correct.
- QA-002 MEDIUM: `includes [precision]` (interval-interval) mistranslates: the
  `precision of` wrapper on the right interval is translated generically (bounds
  truncated via LEFT(...,N)) and the comparison runs through non-precision
  `intervalIncludes` at mixed precision → NULL instead of TRUE for determined cases.
  `Interval[@2024-01-05, @2024-03-31] includes month of Interval[@2024-01-01, @2024-02-15]`
  → null; reference (IncludedIn via In/SameOrAfter at month) → true. The
  intervalIncludesPrecise/intervalIncludedInPrecise UDFs exist and return the right
  answer when called directly; the translator's `includes` branch (line ~2663
  _operators.py) simply lacks the interval-interval precise routing that
  `included in` already has (line ~2735).
- QA-003 MEDIUM: engine divergence on `expand Interval[1, null]` and
  `expand Interval[null, 5]`: Python returns [], native returns NULL. Reference
  ExpandEvaluator returns null when the lessOrEqual boundary comparison is null
  (unbounded interval cannot be expanded). Python path wrong.
- QA-004 LOW: parser rejects a negative Quantity literal after `per`
  (`collapse {...} per -1` → ParseError "Unexpected token MINUS"). CQL grammar allows
  negative quantity literals; reference gets the value and errors/nulls at evaluation.

## Verified conformant (NOT A BUG registry additions)
- After uses only end(B) (so `Interval[1,5] after Interval(null,0]` = true is correct);
  Before symmetric via start(B); open-null-bound → null confirmed.
- Ends [precision] point operands (both sides), coarse precision start-conjunct, all
  match degenerate-interval promotion semantics.
- Except: any exclusion that yields two pieces (superset/interior/open-inner removal,
  unbounded-high middle removal) → null (single-interval rule); `Interval[1,null]
  except Interval[3,null]` → [1,2] (Integer [1,3) normalization) correct.
- Expand open interval (1,5) → {2,3,4}; [1,10] per 3 → {1,4,7}; per month DateTime;
  Quantity/Decimal/hour-precision per; list overload — all match spec examples.
- Collapse numeric/Quantity/Decimal per merges, per>=2 temporal extension merges,
  unsorted input, null elements excluded, incompatible per → null.
- Contains/In [precision] month/year boundaries, `in month of` mirror of contains.
- End of Decimal open → 3.49999999 (spec predecessor); Quantity; open DateTime →
  predecessor date. Equal with Quantity unit conversion (100 'cm' = 1 'm') → true.

## Baseline
No source changes made by QA. Conformance gate untouched this phase.
