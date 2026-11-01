# Engineer Handoff — CQL-15 iteration 1

All four QA issues fixed at root cause; no shims.

## QA-001 (HIGH) Ends [precision] start-conjunct
`fhir4ds/cql/translator/expressions/_operators.py` `_translate_ends_op` "precision of"
branch now emits `start(left) >= start(right) AND end(left) == end(right)` at the given
precision (point operands compare the point for both conjuncts, matching degenerate
interval [p,p] promotion and the no-precision `intervalEndsSame` path).

## QA-002/QA-003 (HIGH/MEDIUM) Collapse per
- Translator `_functions.py::_translate_collapse` now lowers `collapse(X, per)` to the new
  `collapse_intervals_per(list_json, per)` UDF instead of `collapse_intervals(expand(X, per))`.
- Python: `udf/interval.py` — `collapse_intervals(intervals_json, per_json=None)` with
  `_parse_collapse_per` + `_extend_bound_by_per`; per extends each merged interval's end by
  `per` for the overlap/meets decision only; output intervals keep ORIGINAL boundaries;
  temporal per of exactly 1 (or 0) uses precision-based meets (reference
  CollapseEvaluator.getIntervalWithPerApplied semantics); incompatible/invalid per → NULL.
- Native: `extensions/cql/src/cql_extension.cpp` `CollapseIntervalsPerFunc` mirrors the same
  algorithm (BoundValue extension; DateTime via ApplyQuantityAtInputPrecision). Registered
  2-arg; `collapse_intervals_per` added to `_PYTHON_PREFERRED_CPP_CONFLICTS` so Python
  remains the conformance authority on mixed connections.
- Rebuilt + deployed: md5 025c79edaea4af69621e5ae59060d1e3 matched across repo bundle
  (`fhir4ds/cql/duckdb/extensions/`) and site-packages; no stale ~/.duckdb cache copy.
- Stale pins corrected in `test_interval_part1_parity.py` (CollapseValidPer etc.) and new
  regression defines added (per 0/1/2, decimal, temporal 1-day/2-day, no-merge, Ends
  precision conjunct, list-except interval coercion).

## QA-004 (MEDIUM) list except scalar interval
`_operators.py` except branch: literal Interval AST operands wrapped in `list_value(...)`
before `CQLListExceptEq`; identifiers (list-typed defines) untouched (first attempt wrapped
identifiers and broke `LNumeric except { null }` — caught by test_list_part1_parity and
narrowed to `isinstance(expr._operand, Interval)`).

## Validation
- test_interval_part1_parity 18/18; part2/part3, list part1/part2, test_list_udfs,
  temporal_complex, wasm gates: all pass (27+40+154+71 cumulative).
- Master gate: ViewDefinition 144, FHIRPath 935, CQL 1706, DQM 47 — 2832/2832 (baseline
  holds). Probe1/probe2: zero engine divergences.
