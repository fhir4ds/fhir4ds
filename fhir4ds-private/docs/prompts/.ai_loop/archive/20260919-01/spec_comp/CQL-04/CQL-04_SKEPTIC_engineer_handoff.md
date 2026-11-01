# Engineer Handoff — CQL-04 SKEPTIC (iteration 1)

## Triage

| Issue | Category | Triage | Terminal status |
|---|---|---|---|
| QA-001 Boolean define null→FALSE at population surface | SPEC_VIOLATION (surface) | Spec-grounded analysis | INTENDED |

## QA-001 resolution

- **Reproduced**: yes (probe + new regression test).
- **Root cause**: final Boolean projection in
  `fhir4ds/cql/translator/translator.py` (~line 1378, normal mode) emits
  TRUE/FALSE from boolean-define CTE row presence; boolean CTEs carry
  patient_id only (`cte_manager.py:_wrap_expression_in_select`) and are
  consumed as EXISTS row-presence invariants across the translator and the
  DQM evaluator.
- **Spec analysis**: CQL 1.5 operator semantics (Appendix B, Table 9-A1)
  are fully honored internally — lowered SQL preserves SQL NULL for all
  null-operand combinations (verified for And/Or/Not/Xor/Implies, both
  engine paths). The population output column encodes *measure population
  membership*, for which CQL-based measure scoring requires null criteria ≡
  not-in-population; the CQL spec does not define the population-SQL output
  encoding. Reclassified **INTENDED**, not a fix candidate: converting
  boolean CTEs to value-carrying rows would corrupt every EXISTS reference
  and measure counts (high regression risk, no spec mandate).
- **Action taken**: doctrine added to /mnt/d/fhir4ds/AGENTS.md (NOT A BUG
  Registry) and pinning regression test added:
  `test_cql_logical_null_propagates_in_lowered_sql_and_collapses_to_false_at_population_surface`
  (parametrized 10 null-operand expressions; asserts expression-level NULL
  AND population-surface FALSE on both Python-supplement and C++ paths) in
  `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py`.

## Validation

- Focused: test_logical_parity.py → 52 passed; test_macros_tier1.py →
  60 passed (combined run 112 earlier).
- Full conformance `run_all.py`: see architect handoff (was running at
  handoff; result recorded there).
- No source code changes; only the regression test and docs.
