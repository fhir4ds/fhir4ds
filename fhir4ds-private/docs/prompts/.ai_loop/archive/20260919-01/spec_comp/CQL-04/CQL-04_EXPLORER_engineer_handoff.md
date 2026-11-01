# Engineer Handoff — CQL-04 EXPLORER (iteration 1, 2026-08-20)

All three QA issues CONFIRMED and RESOLVED. Reproducers pass; baselines hold.

## QA-001 (HIGH) — `not` precedence per official grammar
- Root cause: CQL-04 HISTORIAN launch misread ANTLR alternative ordering
  (earlier alternatives bind TIGHTER, not looser) and moved `not`'s
  operand to the equality tier — the fix itself was a spec regression.
- Fix (surgical, `fhir4ds/cql/parser/parser.py`):
  - `parse_not_operand()`: `not`'s own operand parsed at the
    typeExpression tier (looser than `is [not] null/true/false`/`is`/`as`,
    tighter than between/set/inequality/equality/membership).
  - `parse_equality_operand()` + `parse_comparison_expression(left=...)`:
    NOT primaries are consumed as equality/comparison operands, so
    `not true = false` → `(not true) = false`, `not 5 in {1,2}` →
    `(not 5) in {1,2}`, `not 3 < 2` → `(not 3) < 2` — each now a
    TranslationError ("CQL logical operator 'not' requires Boolean
    operands; got Integer") when the operand is non-Boolean, matching the
    official cql.g4 parse.
  - Unchanged and still correct: `not X is null`, `not not X`,
    `not true and false`, `not exists ...`, parenthesized forms.
- Test: `test_cql_not_precedence_tighter_than_comparisons_per_grammar`
  (replaces HISTORIAN's inverted test).

## QA-002 (HIGH) — case first-match vs later literal-true when
- Root cause: `_translate_case_expression`
  (fhir4ds/cql/translator/expressions/_lists.py) returned the branch of
  ANY literal-true when immediately, discarding earlier dynamic whens.
- Fix: literal-true when short-circuits only when no earlier whens remain;
  otherwise it becomes the fallback (else) and later items are dropped as
  unreachable (`reached_true_tail` guard).
- Test: `test_cql_case_first_match_semantics_with_later_literal_true_when`.

## QA-003 (HIGH) — Boolean define alias destroyed 3VL via EXISTS
- Root cause: `_classify_definition_ref`
  (fhir4ds/cql/translator/expressions/__init__.py) routed ALL
  BOOLEAN-usage define references to EXISTS. Value-bearing per-patient
  CTEs (`define F: Patient.active`) keep a row (with NULL) for every
  patient, so EXISTS was always-true.
- Fix: BOOLEAN usage on a non-boolean-scalar, value-bearing define now
  returns CORRELATED_SCALAR; both lookup builders in `_core.py`
  (`_build_promoted_definition_lookup`, inline definition branch) emit
  `CAST((SELECT sub.col ...) AS BOOLEAN)` so the VALUE participates in
  3VL. EXISTS is unchanged for row-presence boolean CTEs and EXISTS
  usage.
- Test: `test_cql_boolean_define_alias_feeds_logic_by_value`.

## Files changed
- `fhir4ds/cql/parser/parser.py` (QA-001)
- `fhir4ds/cql/translator/expressions/_lists.py` (QA-002)
- `fhir4ds/cql/translator/expressions/__init__.py`, `_core.py` (QA-003)
- `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py`
  (3 regression tests; HISTORIAN's inverted precedence test rewritten)

## Validation
- All QA probes pass on BOTH engine paths (Python supplements + C++
  extension), py==cpp on every case.
- `pytest fhir4ds/cql`: **5713 passed, 9 skipped** (pre-existing env skips).
- Conformance: **ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47 — OVERALL 2832/2832** (baseline held; no regression).

No new issues discovered during remediation. All issues terminal
(RESOLVED). Handing off to Architect.
