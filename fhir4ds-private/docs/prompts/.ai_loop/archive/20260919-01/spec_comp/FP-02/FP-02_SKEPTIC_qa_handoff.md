# QA Handoff — FP-02 SKEPTIC (iteration 1, 2026-08-16)

## Chunk
FHIRPath §4.2 Operators (equality, comparison, arithmetic incl. collection operands
and type-error behavior, `|` union, `and`/`or`/`xor`/`implies` three-valued logic,
`is`/`as`), §4.3 Function Invocations, §4.4 Null/Empty propagation, §4.5 Singleton
Evaluation of Collections.

## Method
- Spec grounding: fetched full N1 (v2.0.0) normative text for §4.2–§4.5 and the
  §6.1–§6.8 operation semantics they reference; extracted official R4 fixture
  truth tables (testBooleanLogicAnd/Or/XOr, testBooleanImplies, testPlus,
  testConcatenate, testDiv, testMod, testPrecedence) from
  `fhir4ds/fhirpath/tests/compliance/r4/tests-fhir-r4.xml` as authoritative pins.
- 163 dual-path probe cases (native extension connection vs Python fallback UDFs,
  5 result channels + `fhirpath_is_valid`), batteries in
  `/mnt/d/fhir4ds/.temp/qa/fp02_skeptic_2026_08_16/` (probe.py, probe2.py, plus
  two ad-hoc batteries: quantity-unit equality matrix, unary/union validity matrix).

## Pre-registered SKEPTIC hypotheses and outcomes
- H1 div/mod floor-vs-truncate divergence — REJECTED (both engines truncate
  correctly: -5 div 2 = -2, -5 mod 2 = -1, 5 mod -2 = 1).
- H2 implies/xor empty corners divergence — REJECTED (all 9+9 fixture truth-table
  cells correct in both paths).
- H3 comparison type errors return false — REJECTED (`t > f`, `'a' < 1`, `1 < t`
  → empty in both).
- H4 `&` coercion — REJECTED as a bug (see INTENDED below).
- H5 integer overflow wraps — REJECTED (see observation).
- H6 cross-type equality inconsistency — REJECTED (`1 = '1'` → empty both).
- H7 unary minus on non-numeric — CONFIRMED as QA-002 (validity classification).
- H8 `|` with `{}` — REJECTED (`({} | 1).count() = 1` both).

## Issues logged (evolution.json)
1. QA-001 (MEDIUM) — fallback `fhirpath_is_valid_udf` violates §6.8 precedence:
   `_has_invalid_math_literal_operands` (udf.py:1110) treats the entire textual
   side of a math operator as its operand, so valid `arith | union` mixes
   (`1 + 2 | 3`, `1 | 2 + 3`, `'a' | 'b' & 'c'`, `2 * 3 | 4`, `3 | 4 + 5`,
   `1 + 1 | 2`, `0 + 1 | 2`) return is_valid=False while native returns True and
   both engines evaluate them correctly.
2. QA-002 (LOW) — unary `+`/`-` on non-numeric literals (`-'a'`, `+'a'`) classified
   syntactically invalid in BOTH backends while equivalent binary type errors
   (`'a' - 'b'`) are valid; `_is_valid_empty_result_error` (udf.py:2343) misses the
   unary message. Native `fhirpath_is_valid` needs the same classification check.
3. QA-003 (HIGH) — Quantity `*`/`/` result units never merge exponents:
   `12 'cm2' / 3 'cm'` → `0.04 'm2/m'` (spec example: `4.0 'cm'`) so
   `= 4 'cm'` is EMPTY; `3 'cm' * 12 'cm2'` → `0.000036 'm.m2'` (spec: `36 'cm3'`);
   user-written `1 'm2/m' = 1 'm'` also EMPTY. Python root: nodes.py
   `__mul__`/`__truediv__` string-concatenate base units; C++ mirrors.

## Verified clean (high-value negative results)
- Spec §6 preamble examples: `{} = {}` → empty, `{} != 'dummy'` → empty,
  `true > {}` → empty (both paths).
- §4.3: `(4+5).count()` = 1, `('a'|'b').count()` = 2, `{}.count()` = 0,
  chaining on operator outputs (`(1+2).abs()`, `('a'+'b').upper()`).
- §4.4: empty propagation through all math ops, `indexOf`/`substring`/`power`/
  `startsWith` args; `|` union with `{}` per §4.4.1.
- §4.5: multi-item operands to boolean ops / `not()` / `is` / unary → error → empty;
  single Integer/Quantity node in Boolean context → true (§4.5 branch 2);
  `iif(zero, ...)` → then-branch.
- §6.8 precedence: `2 + 3 * 4` = 14, `true or false implies false` → false,
  `{} = {} or true` → true, `-3.abs()` = -3 vs `(-3).abs()` = 3, `2 - -3` = 5,
  `- 2 * 3` = -6, `1 | 2 is Integer` → {1,true}.
- §6.1: ordered multi-item `=` vs unordered `~`; count mismatch → false;
  `1 = 1.0` true.

## INTENDED / observations (no issue)
- `1 & 2` → '12' (both): reference implementations coerce singleton non-strings via
  toString for `&` — official fixture testConcatenate4's expected text `'1,2,3b'`
  (invalid only for multi-item) proves the reference converts integer items to
  strings. Keep as intended.
- Integer overflow promotes to Decimal: `2147483647 + 1` → `2147483648.0` (both).
  Matches Java-RI-style promotion; §6.6 "overflow → empty" not triggered since
  Decimal represents the value.
- `'abc'.substring(1, {})` → 'bc': §5.6.2 explicitly overrides §4.4.1 for empty
  length ("same as if length had not been provided").
- `1 < 2 | 3` is_valid=False (both): designed — singleton violations are invalid per
  udf.py doctrine (distinct from type-incompatible operands).
- §4.5 branch-1 (explicit String/Integer→Boolean conversion: `boolText and true`
  where boolText='false', `zero and true`) vs branch-2 (non-convertible single node
  → true): no official fixture pins convertible nodes in Boolean context; repo
  pins branch-2 for nodes and errors for literals (testIif6). Left for HISTORIAN
  to re-examine with reference-implementation evidence.

## Suggested FIX anchors
- QA-001: udf.py `_has_invalid_math_literal_operands` — split top-level `|`
  segments first and recurse per segment before locating math operators.
- QA-002: udf.py `_is_valid_empty_result_error` + native is_valid classification.
- QA-003: nodes.py `FP_Quantity.__mul__`/`__truediv__` (and C++ evaluator mirror):
  merge base-unit exponents ('m2/m' → 'm', 'm.m2' → 'm3') at composition and in
  `conv_unit_to_base` parsing so reduced and unreduced spellings compare.
