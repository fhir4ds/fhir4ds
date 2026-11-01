# QA Handoff — CQL-15 (Interval Operators Part 1), iteration 1, SKEPTIC

## Scope tested
CQL 1.5 interval operators: After/Before [precision] (interval+point), Collapse(argument,[per]),
Contains/In [precision], End of, Ends [precision], Equal/Equivalent (interval), Except (interval),
Expand(argument,[per]) (interval AND list overloads), Includes [precision]. Dual-engine
(Python fallback + native C++ extension) on ~100 cases. Spec verified against live cql.hl7.org
09-b-cqlreference.html and the HL7 reference engine (clinical_quality_language main branch:
CollapseEvaluator.kt, EndsEvaluator.kt).

Probes: /mnt/d/fhir4ds/.temp/qa/cql15_skeptic/probe{1,2}.py.

## Issues opened
- QA-001 HIGH: `ends <prec> of <interval-or-point>` drops the start-containment conjunct
  (spec: start(A) >= start(B) AND end(A) == end(B) at precision). Returns true when it must
  be false. Location: `_translate_ends_op` "precision of" branch,
  fhir4ds/cql/translator/expressions/_operators.py (~line 5548). No-precision path
  (intervalEndsSame) is correct.
- QA-002 HIGH: `collapse(X, per)` mistranslated as `collapse_intervals(expand(X, per))`.
  Truncates interval bounds to the per grid ({[1,3],[5,6]} per 2 -> {[1,2],[5,6]}), explodes
  Decimal intervals into singletons, and fails merges the reference performs (per extends each
  interval's end by `per` for the merge decision only; output keeps original bounds ->
  {[1,6]}). Existing pins in test_interval_part1_parity encode the wrong behavior.
- QA-003 MEDIUM: engine divergence at `per 0` — Python returns inverted intervals ([1,0]),
  native returns []; reference merges to {[1,6]}. Same root cause as QA-002.
- QA-004 MEDIUM: `{list of intervals} except <interval>` generates CQLListExceptEq(list,
  scalar-VARCHAR) -> BinderException. Interval must be coerced to a singleton list.

## Verified conformant (NOT A BUG)
- Contains/In null semantics exactly per spec: `null contains 3` -> false, `3 in null` ->
  false, `Interval[1,5] contains null` -> null.
- After/Before: strict inequality on Start/End semantics; adjacency ([3,4] after [1,3] ->
  false; [1,3) before (3,4] -> true); null operand -> null; precision variants.
- End of: open non-null high -> predecessor (Integer 4 for (1,5); 01-14 for DateTime);
  closed null high -> point-type maximum (2147483647 / 9999-12-31); open null high -> null
  (spec describes an uncertainty; null is the accepted simplification — LOW, not opened).
- Equal/Equivalent interval: open-null vs closed-null bounds per CQL-09 doctrine; Equivalent
  never-null. Except: partial containment -> null (proper-interval rule); spec examples pass.
- Collapse without per: overlap/meet/successor adjacency, null exclusion, null list -> null,
  DateTime hour-precision meets, spec example {[1,4],[4,8],[7,9]} -> {[1,9]}.
- Expand: single-interval and list overloads incl. `per day`, `per 2 days`, numeric per,
  Quantity intervals, `per null` (default per), `expand null`, incompatible per -> [].
- Includes: interval/point/null overload examples all match spec.

## Baseline
No source changes made by QA. Conformance gate untouched this phase.
