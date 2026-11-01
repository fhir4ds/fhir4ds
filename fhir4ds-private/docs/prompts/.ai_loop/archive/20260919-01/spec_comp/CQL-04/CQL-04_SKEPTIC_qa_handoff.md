# QA Handoff — CQL-04 SKEPTIC (iteration 1)

Chunk: CQL 1.5 Logical Operators — And, Or, Not, Xor, Implies.
Personality: SKEPTIC. Workspace: `/mnt/d/fhir4ds/.temp/qa/cql04_skeptic_2026_08_20/probe.py`.

## Spec anchor (verified against cql.hl7.org Appendix B + developer guide precedence table)

- Kleene 3VL tables: And (false and null → false, true and null → null),
  Or (true or null → true, false or null → null), Not null → null,
  Xor (any null operand → null unless…: null always → null),
  Implies: false implies X → true; null implies true → true;
  null implies false → null; null implies null → **null**;
  true implies null → null.
  NOTE: the campaign prompt's "null implies null → true" contradicts the
  spec (Table 9-A1 / Appendix B: "null implies false/null → null").
  Implementation matches the SPEC, not the prompt.
- Precedence: not > and > or/xor > implies; within a category,
  left-to-right ("order of appearance in the expression, left to right").

## Probed surfaces (all dual-path: Python supplements vs C++ extension)

1. SQL macro truth tables And/Or/Xor/Implies/Not + logicalImplies — full
   9-combination matrices, cpp vs py parity AND spec values: ALL PASS
   (81+ checks). Includes null implies null → null, false and null → false.
2. End-to-end `translate_library_to_population_sql` + DuckDB execution for
   25 infix literal expressions incl. all null rows, chained
   `a or b and c`, `true xor true or true`, `true implies false implies true`
   (left-to-right per spec), `not true or true`: py-vs-cpp parity OK;
   all spec-correct EXCEPT QA-001 below (null-literal results reported FALSE).
3. Non-Boolean operands (8 cases: `1 and true`, `not 1`, `1 xor true`,
   `'a' and 'b'`, `1 + 1 and true`, `not 'yes'`, …): all raise
   `TranslationError` with a clear message. Matches CQL static typing.
4. Function-call forms in CQL source: `And(...)/Or(...)/Xor(...)/Implies(...)`
   are ParseErrors — CORRECT, CQL grammar defines logical operators as
   infix/prefix only; the quoted "And"/"Or"/"Xor"/"Implies"/"Not" macros are
   internal SQL lowering surfaces (parity-tested, not CQL syntax).
   `Not(false)` parses as unary not + parenthesized operand → `NOT FALSE` ✓.
5. Dead-branch error propagation: `false and (1 / 0 = 1)` → False (no
   DuckDB div-by-zero error surfaces; row filtered, correct).
6. Focused suites: test_logical_parity.py + test_macros_tier1.py → 112 passed.

## Findings

- QA-001 (MEDIUM, OPEN): Boolean define output surface collapses null to
  FALSE. `define R: null and true` (also true implies null, null xor true,
  not null, …) reports R=False; spec value is null. Root cause: final
  projection `CASE WHEN "R".patient_id IS NOT NULL THEN TRUE ELSE FALSE END`
  (translator.py ~line 1378) + boolean CTE row-presence design
  (`_wrap_expression_in_select` cte_manager.py:1751 — "drops rows when
  false", referenced via EXISTS throughout). Internal 3VL is correct
  everywhere; measure population membership (null → not in population) is
  measure-correct. This is an architectural value-surface trade-off, not an
  operator-level defect — remediation should classify (fix vs INTENTED +
  doctrine + pinning regression test).

No other divergences found. Baseline conformance re-run in progress at
handoff time (see architect phase record).
