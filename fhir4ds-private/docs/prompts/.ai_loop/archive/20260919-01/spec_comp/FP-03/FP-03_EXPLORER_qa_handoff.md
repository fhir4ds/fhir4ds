# QA Handoff — FP-03 EXPLORER (iteration 1, 2026-08-17)

## Chunk
FHIRPath §5.1 Existence: empty(), exists([criteria]), all(criteria), allTrue(),
anyTrue(), allFalse(), anyFalse(), subsetOf(other), supersetOf(other), count(),
distinct(), isDistinct().

## Method
- Spec grounding: cached normative spec at
  `/mnt/d/fhir4ds/.temp/qa/fp07_fhirpath_spec.md` (§5.1 function table,
  scoped-function criteria semantics, `exists(criteria)` ≡
  `where(criteria).exists()` shorthand), reused SKEPTIC/HISTORIAN spec pins.
- Dual-path probes (native DuckDB extension vs Python fallback UDFs, 5 result
  channels + fhirpath_is_valid), run with `PYTHONPATH=/mnt/d/fhir4ds`:
  - `probe.py` (89 cases): E1 chaining onto §5.1 outputs, E2 distinct/
    isDistinct on nested lists / resources / key-order objects / mixed types,
    E3 subsetOf/supersetOf with nested/quantity/mixed/self collections,
    E4 count()+dedup interactions, E5 empty() null propagation, E6
    element-level criteria errors, E7 arity/grammar abuse.
  - `probe2.py` (18 cases): boolean operator chaining — `X.and(Y)` vs
    `X and Y`, `.or()/.xor()/.not()` chains.
  - `probe3.py` (43 cases): criteria singleton violations (`all(nums)`,
    `exists($this+1)`), empty-literal `{}` interactions, other-argument
    errors for subsetOf/supersetOf, derived-unit distinctness
    (`180 'cm'|1.8 'm'`), deep self-chaining (distinct³, count().count(),
    isDistinct().isDistinct()).
  Total: 150 fresh dual-path evaluations. Workspace:
  `/mnt/d/fhir4ds/.temp/qa/fp03_explorer_2026_08_17/`.

## Results — ZERO parity diffs, ZERO new spec violations
- All 150 cases native == fallback across all 6 channels.
- Chaining: `empty().not()`, `distinct().subsetOf()`, `count().convertsToInteger()`,
  `exists().and()` (infix form), `trace()` passthrough, `first()` after
  distinct, `iif()` over isDistinct — all correct and parity-clean.
- Nested/resource distinctness: deep-equal lists dedup, identical contained
  resources dedup, key-order-different JSON objects dedup, `1/1.0/'1'/true`
  → 3 distinct — correct in both.
- subsetOf/supersetOf: self-subset true, partial coverage false, boolean-other
  (`supersetOf(nums.count())` → {3} membership) correct, quantity literal
  `qtys.subsetOf(180 'cm')` true, `180 'cm'|1.8 'm'` → 1 distinct.
- count()+dedup: navigation keeps duplicates (qtys.count()=2,
  distinct().count()=1), `|` dedups at construction, combine() then distinct
  correct, JSON-null array elements skipped by count.
- Null propagation: `n.empty()` true for null value, `n.empty().empty()` false,
  `iif(n.empty(),1,2)` → 1, nulls in all/exists criteria behave as not-true.
- Criteria errors: unknown function, `+` type errors, time-string ordering →
  empty (SKEPTIC QA-001/QA-002 fixes still intact); exists(c) ≡
  where(c).exists() coherence maintained even for non-Boolean criteria
  (`nums.exists(nums)` false == `nums.where(nums).exists()` convention).
- Grammar/arity: all malformed arities rejected by is_valid on both surfaces.

## NOT A BUG registry addition
- `X.and(Y)` / `X.or(Y)` / `X.xor(Y)` (dotted form) are INVALID FHIRPath —
  `and`/`or`/`xor` are reserved infix keyword operators, not invocable
  function names. Both engines correctly return empty + is_valid=False, while
  the infix `X and Y` form evaluates correctly. (`.not()` IS a function and
  works.)

## Suggested FIX anchors
None — no issues to fix.
