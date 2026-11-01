# QA Handoff — CQL-04 HISTORIAN (iteration 1, 2026-08-20)

Chunk: CQL 1.5 Logical Operators — And, Or, Not, Xor, Implies.
Personality: HISTORIAN. Workspace: `/mnt/d/fhir4ds/.temp/qa/cql04_historian2_2026_08_20/probe.py`.

## Spec anchor (verified against official grammar, not prose)

Downloaded the official CQL 1.5 grammar (HL7/cql tag v1.5.3,
`input/images/cql/cql.g4`) and read the `expression` rule alternative
ordering: `'not' expression` (#notExpression) appears BEFORE
inequalityExpression / equalityExpression / membershipExpression /
andExpression / orExpression / impliesExpression. In ANTLR precedence
semantics this means **`not` binds looser than comparisons, membership,
`between`, `is null`, and union/set ops, but tighter than `and`/`or`/`xor`/
`implies`**. So `not X in Y` = `not (X in Y)`, `not A = B` = `not (A = B)`.

## Probe strategy (built on SKEPTIC's institutional memory)

SKEPTIC verified expression-level Kleene 3VL truth tables exhaustively on
both engine paths. HISTORIAN hunted NEW divergences at the grammar/precedence
layer instead, plus data-derived null propagation. All probes dual-path
(Python supplements vs C++ extension) with parity assertions.

## Findings

### QA-001 (HIGH, OPEN): unary `not` parsed at wrong precedence

`fhir4ds/cql/parser/parser.py` handled `not` in `parse_unary_expression`
(deepest level), binding it tighter than EVERYTHING. Spec-correct CQL
therefore failed to translate:

- `not 5 in { 1, 2 }` → TranslationError "not requires Boolean operands;
  got Integer" (parsed `(not 5) in {1,2}`). Spec: `not (5 in {1,2})` = true.
- Same for `not 1 = 2`, `not 1 != 2`, `not 3 < 2`, `not 2 <= 3`.
- Canonical CQL style (`not X in ...`) is broken at translation time.
- Both engine paths affected (single Python parser feeds both).

### Verified correct (no issue)

- `not X is null` (is-null postfix binds tighter than not — matches grammar).
- `not (5 between 1 and 10)` → False, `not (0 between 1 and 10)` → True.
- `not not true` → True; `not true and false` → False (not tighter than and);
  `not true xor false` → False.
- `not 1` (bare non-Boolean operand) → TranslationError — still correct.
- Null-valued defines (`not not null`, `Patient.active and null`,
  `Patient.active implies null`, `not Patient.active xor null`) report FALSE
  on the population surface — the pinned null→FALSE membership doctrine
  from the SKEPTIC launch (INTENDED, not re-lodged).
- py-vs-cpp parity on every probe.

No other new divergences found.
