# Engineer Handoff — CQL-20 Aggregate Functions (HISTORIAN, iteration 1)

All four actionable issues fixed at root cause; no workaround shims; translator-only
change — native binaries untouched (cql 3e7d4167143e01907fdd8561db43b7d7, fhirpath
57d0634b6ee6eddee9fc06a1355bef5a, repo bundle == site-packages verified).

## Files changed
- `fhir4ds/cql/translator/expressions/_functions.py`
  - `_translate_aggregate_pre` CQLQuery branch: numeric-returning queries
    ({Integer, Long, Decimal} element types) now materialize the per-patient
    element LIST and dispatch through `_translate_list_aggregate_dispatch`
    (QA-001) — exact typed widths instead of `SUM(TRY_CAST(x AS DOUBLE))`.
  - `_translate_list_aggregate_dispatch`: Decimal Sum/Product results
    TRY_CAST to DECIMAL(38,8) — CQL 1.5 §2.3 Decimal exactness even when
    elements were lowered through DOUBLE (dynamic JSON numerics).
  - `_static_list_element_types`/`_element_type`: new inference —
    (a) Boolean-result operators (is null/is true/not, and/or/xor,
    comparisons, in/is/like) yield element type Boolean (QA-002: dynamic
    non-numeric aggregate operands now fail at translation with the typed
    CQL error, matching the literal path);
    (b) arithmetic result types per CQL promotion (Integer/Long/Decimal,
    `/` always Decimal) so derived numeric elements route to the exact
    lowering. Placement note: these branches must stay AFTER the existing
    `as`-cast branch (an earlier placement short-circuits choice-casts).
- `fhir4ds/cql/translator/expressions/_operators.py`
  - Untyped-identifier × numeric-literal arithmetic no longer hardcodes
    TRY_CAST(... AS INTEGER): target follows the identifier's inferred
    static type, else the literal kind (float → DECIMAL(38,8)) (QA-004).
- Tests: `fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py`
  (+3 tests: exact-typed dynamic numeric aggregates end-to-end py/cpp/nopy,
  exact dynamic Decimal Sum {0.1,0.2}+0.0 = 0.3, typed errors for dynamic
  Boolean aggregate operands).

## Validation
- Reproducers: `.temp/qa/cql20agg_historian/` probe_literal.py (86 cases, 0
  failures/divergences), probe_dynamic.py (42 cases, all 3-engine parity OK).
- Focused suites: aggregate parity 33/33; arithmetic part1+2 29/29; v2
  expressions 147/147; list part1+2 65/65.
- Master gate: see architect handoff (final tree, incl. DQM final-state).

## Terminal classification
- QA-001 RESOLVED, QA-002 RESOLVED, QA-004 RESOLVED (pre-existing, found by
  git-stash bisect during remediation), QA-003 INTENDED (CQL-05 adjudication),
  QA-005 DEFERRED (pre-existing Ratio accessor failure in
  test_temporal_complex_parity.py — fails identically with this session's
  changes stashed; out-of-chunk CQL-03 surface; flagged for the owner chunk /
  milestone reconciliation).
