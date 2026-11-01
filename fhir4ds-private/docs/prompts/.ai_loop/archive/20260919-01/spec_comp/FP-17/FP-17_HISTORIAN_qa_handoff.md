# QA Handoff — FP-17 HISTORIAN (iteration 1, 2026-08-18)

## Chunk
FHIRPath §6.5 Boolean Logic: `and`, `or`, `not()`, `xor`, `implies`.

## Method
Dual-path probe (native C++ extension vs forced Python fallback) at
`.temp/qa/fp17_historian_2026_08_18/probe.py` (56 expression cases + 10
is_valid cases). HISTORIAN angle: NEW divergence hypotheses beyond the prior
SKEPTIC launch's truth-table/fixture coverage.

## New angles probed (vs SKEPTIC)
- H1: chained `implies` associativity; long and/or/xor chains; parenthesized
  equivalents to disambiguate.
- H2: boolean logic inside `where()`/`select()`/`iif()`/`exists()`/`all()`
  contexts, incl. unqualified-identifier resolution against `$this`.
- H3: rich comparisons feeding boolean ops (date literals, `!=`, `in`,
  division-by-zero propagation, `>=` on fields).
- H4: `not()` arity misuse (`t.not(false)`), bare `not(...)` chains,
  double/triple `.not()` nesting, polarity mixed with boolean ops.
- H5: iteration + `$this` boolean logic (`.where($this)`, `.where($this.not())`).
- H6: deep parenthesized nesting.
- H7: explicit JSON `null` field vs absent field through all 5 operators.

## Results
- 0 parity diffs between native and fallback across all cases.
- 0 spec violations. 16 initial expectation mismatches were ALL resolved as
  my expectation errors after verifying the official grammar; key resolutions:
  - **Chained `implies` is LEFT-associative and that is correct.** The
    official FHIRPath ANTLR grammar (hl7.org/fhirpath grammar page, mirrored in
    repo `fhir4ds/fhirpath/parser/FHIRPath.g4`) puts and/or/xor/implies in ONE
    left-recursive expression tier — no separate implicationExpression rule
    (that is CQL's grammar, a Historian trap). Engines' `false implies false
    implies false` = false matches left-assoc `(false implies false) implies
    false`; right-assoc would give true. NOT A BUG.
  - Unqualified identifiers inside `where()`/`select()` resolve against `$this`
    (the item), NOT the resource root: `names.where(primary and t)` → []
    because `t` → name.t = {} → `primary and {}` = {}. Correct.
  - `obs.select(value > 2 and t)` → [false]: obs[0] gives `true and {}` = {}
    (row dropped), obs[1] gives `false and {}` = false. Correct 3VL.
  - Bare `not(...)` (e.g. `not(not(false))`) errors → wrapper NULL on both
    engines — reconfirms SKEPTIC's function-form-only pin.
  - `not()` at root: focus = resource (truthy non-boolean singleton) → false.
    Correct per §4.5.
  - `t.not(false)` (wrong arity) → is_valid=false on both engines; `not()`
    (0 args, implicit focus) → is_valid=true. Both consistent with the
    arity-invariant doctrine.
  - `(n in arr) and true` → false: 3 vs booleans are unequal non-empty →
    membership false (not empty). Consistent with pinned doctrine.
  - `any()` is not a FHIRPath function (CQL-ism): correctly unknown → empty.
- Observation (out of chunk scope, membership not §6.5): `'hello' in s`
  (string rhs) returns true on both engines — string-rhs `in` semantics are
  unspecified in FHIRPath; both engines agree; logged only.

## Baseline
2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — no regression.

## Issues
None. Zero non-terminal CRITICAL/HIGH/MEDIUM issues -> clean exit eligible at
min_iterations=1.
