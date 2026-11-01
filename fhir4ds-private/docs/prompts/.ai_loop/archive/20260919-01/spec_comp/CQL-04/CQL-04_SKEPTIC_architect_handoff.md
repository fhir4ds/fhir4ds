# Architect Handoff — CQL-04 SKEPTIC (iteration 1)

## Structural audit (scope: CQL logical operators, both engine paths)

Golden standard invariants written to
`/mnt/d/fhir4ds/.temp/architect/golden_standard_cql04.md`. Audit results:

- **Invariant compliance: good.** Logical lowering is AST-only (no SQLRaw in
  macros/logical.py or the live translator path); parser accepts only
  infix and/or/xor/implies + prefix not (function-call forms correctly
  ParseError); non-Boolean operands rejected at translate time; macro and
  UDF truth-table comments match CQL 1.5 Table 9-A/9-A1 (including
  null implies null → null).
- **QA-001 classification endorsed**: the null→FALSE collapse at the
  population output surface is the documented row-presence membership
  architecture (EXISTS-referenced boolean CTE invariant; DQM consumer).
  Expression-level 3VL is fully spec-correct. INTENDED with doctrine +
  dual-path pinning regression test — no rework mandated.
- **QA Enforcer Gate**: QA was NOT lazy — full 9-combination matrices per
  operator on both paths, precedence/chaining, non-Boolean rejection,
  function-form vs keyword distinction, dead-branch error propagation,
  spec verified against cql.hl7.org (and correctly contradicted the outer
  prompt's erroneous "null implies null → true" claim with citation).
  No RETRY_QA.
- **QA-002 (LOW, DEFERRED)**: duplicated logical-operator lowering logic —
  `fhir4ds/cql/translator/operators.py:translate_binary_op` (and/or/xor/
  implies branches) shadows the live path in
  `translator/expressions/_operators.py` (~line 1891). Both are
  spec-correct today (identical semantics: xor via macro vs SQL-composite,
  implies NOT A OR B), but the duplicate is divergence debt.
  `translate_binary_op` is only invoked from unit tests for arithmetic
  ops. Deferred: consolidation is a refactor with no spec driver.

## Empirical validation

- Conformance: **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47)
  — baseline held.
- Focused: test_logical_parity.py 52 passed (incl. new pinning test),
  test_macros_tier1.py 60 passed.

## Recommended fix order

None required. Optional follow-up: consolidate operators.py logical
branches into the single live lowering path (QA-002, DEFERRED).

## Loop control

Iteration 1 ≥ min_iterations(1); zero non-terminal CRITICAL/HIGH/MEDIUM
issues (QA-001 INTENDED, QA-002 LOW DEFERRED). Clean exit recommended.
