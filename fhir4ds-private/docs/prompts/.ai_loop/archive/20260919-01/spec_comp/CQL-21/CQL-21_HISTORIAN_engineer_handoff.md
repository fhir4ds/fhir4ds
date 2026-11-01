# Engineer Handoff — CQL-21 HISTORIAN FIX (iteration 1), QA-001..003

## Root cause (shared)
The SKEPTIC uncertainty change made all age/duration-between surfaces return
§22.21 VARCHAR (crisp integer string or interval JSON) and updated comparisons,
interval-`in`, and Add/Subtract/Multiply lowerings — but four generic
lowerings still received those VARCHAR operands unprepared:
CQLListContainsEq (in-list), list_min/list_max (list Min/Max), LEAST/GREATEST
(scalar Min/Max), and SQL unary minus.

## Fixes (all dual-engine lockstep; no fallbacks, no hardcoded lists)
1. **QA-001 (HIGH, in-list)** — `_operators.py::_list_contains_call`: when the
   element is uncertainty-capable and the list is a static SQLArray literal,
   lower `x in {e1..en}` to OR of `cqlUncertainCompare(x, e, '=')` per CQL
   In(list) ≡ x=e1 or … or en (three-valued uncertainty preserved).
2. **QA-002 (MEDIUM, list Min/Max)** — new UDFs `cqlUncertainListMin/Max`
   (Python `udf/datetime.py`; native `cql_extension.cpp` via
   DEFINE_UNCERTAIN_LIST_MINMAX). Interval-aware: Min → [min of lows,
   min of highs]; Max → [max of lows, max of highs]; nulls ignored;
   collapse to crisp when determinate. Wired at the three emit sites:
   `_functions.py` list-aggregate dispatcher, `_functions.py::
   _translate_aggregate_pre`, `_lists.py` aggregate lowering.
3. **QA-003 (MEDIUM, negate + scalar Min/Max)** — unary `-x` on an
   uncertainty-capable operand now lowers to `cqlUncertainMultiply(x, '-1')`
   (replaces the old cqlDurationBetween-only BIGINT cast, which dropped
   uncertain ranges to NULL — this also fixes silent NULLing of
   `-cqlDurationBetween(...)` uncertainty); scalar Min/Max fold through new
   `cqlUncertainMin/Max` UDFs with non-uncertain operands cast to VARCHAR
   (`_functions.py::_fold_uncertain_scalar_minmax`).
4. Native extension rebuilt and deployed: md5
   `da6c07adb08ef224d0621b9d222b6bae` identical across build output, repo
   bundle, and site-packages; ~/.duckdb cache cleared. (Pre-fix: site-packages
   had drifted back to the STALE pre-SKEPTIC binary 61d8b2c1 — repaired
   before testing.)

## Spec grounding
CQL 1.5 Appendix B (age = Integer-typed duration calc, §22.21 uncertainty);
In (list) ≡ equality disjunction; Negate -x ≡ x * -1 (§16.8); Min/Max
(Appendix B) over numeric elements — interval semantics are the natural
§22.21 propagation ([min of lows, min of highs] for Min).

## Regression test
`test_clinical_operator_parity.py::
test_cql_clinical_age_in_list_negate_minmax_uncertainty_matches_cpp_registration`
— 10 assertions across crisp + partial birthDates on py fallback and native
cpp connections (in-list hit/miss/uncertain-False-at-define, negate crisp +
interval, scalar Max/Min, list Min/Max crisp + interval). 17/17 in the file.

## Validation
- Focused: test_clinical_operator_parity 17/17; test_age_udfs +
  test_datetime_udfs + test_v2_expressions 243/243.
- Manual three-engine check (py / cpp / no-Python): all 9 reproducer cases OK
  including interval negation and interval list-min.
- Master gate run_all.py on the FINAL tree (fresh, filtered): see
  GLOBAL_KNOWLEDGE stats row — recorded post-gate.
- QA-004 remains DEFERRED (pre-existing, other chunk owner).
