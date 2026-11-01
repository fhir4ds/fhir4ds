# Engineer Handoff — CQL-04 HISTORIAN (iteration 1, 2026-08-20)

## QA-001 (HIGH) — unary `not` parsed at wrong precedence — RESOLVED

### Root cause
`fhir4ds/cql/parser/parser.py` consumed `not` inside
`parse_unary_expression` — the deepest precedence tier — so `not` bound
tighter than equality/comparison/membership/`between`. The CQL 1.5 grammar
(HL7/cql v1.5.3 `cql.g4` `expression` rule alternative ordering) places
`'not' expression` (#notExpression) between `and` and the comparison
alternatives: `not` binds looser than comparisons, tighter than
and/or/xor/implies. Result: spec-canonical `not X in Y` / `not A = B` were
parsed as `(not X) in Y` and rejected with TranslationError.

### Fix (surgical, parser-level, single root cause)
1. Added `parse_not_expression()` between `parse_and_expression` and
   `parse_equality_expression`: on `NOT`, operand =
   `parse_not_expression()` recursion; otherwise fall through to
   `parse_equality_expression()`. Docstring cites the grammar.
2. `parse_and_expression` now parses operands via `parse_not_expression`.
3. Removed `NOT` handling from `parse_unary_expression` (with a NOTE
   docstring pointing to the new location).

Both engine paths share this Python parser, so the fix covers native/C++
and Python-fallback surfaces equally; no extension rebuild needed
(parser-only, no evaluator.cpp change).

### Verification
- Reproducer `/mnt/d/fhir4ds/.temp/qa/cql04_historian2_2026_08_20/probe.py`:
  all 6 precedence cases now evaluate spec-correct on BOTH paths
  (`not 5 in {1,2}`=true, `not 1 = 2`=true, `not 3 < 2`=true, etc.).
- Extra probes: `not 5 between 1 and 10`=false, `not 0 between 1 and 10`=true,
  `not (true) and false`=false, `not true xor false`=false, `not 1` still
  TranslationError — all spec-correct.
- Focused regression test added:
  `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py::test_cql_not_precedence_looser_than_comparisons_per_grammar`
  (11 asserts, py+cpp parity). File total: 53/53 passed.
- Full CQL pytest: 5710 passed, 9 skipped (no regressions).
- Full conformance (`conformance/scripts/run_all.py`): **2832/2832** —
  ViewDef 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47. Baseline
  (PROC_VALIDATION.md) holds.

## Files changed
- `fhir4ds/cql/parser/parser.py` (fix)
- `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py` (regression test)
