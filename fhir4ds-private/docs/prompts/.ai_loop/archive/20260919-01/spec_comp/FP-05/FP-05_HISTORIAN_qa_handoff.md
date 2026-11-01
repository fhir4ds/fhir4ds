# QA Handoff — FP-05 HISTORIAN, iteration 1 (2026-08-17)

**Chunk**: FHIRPath §5.3 Subsetting + §5.4 Combining.
**Personality**: HISTORIAN (systematic spec-verifier; fresh angles, not re-runs).
**Spec**: FHIRPath N1 §5.3/§5.4 (normative semantics verified via behavior probes
against both execution surfaces).

## SKEPTIC fix re-verification (QA-001, prior launch)

- `fhirpath_is_valid` now returns True for statically-known wrong-typed §5.3
  arguments (`skip('x')`, `take(true)`, `[1.5]`, `'abc'['x']`, plus new edges
  `skip(@2020-01-01)`, `take(@2020)`, `[@2020]`) on BOTH surfaces; singleton and
  multi-item variants (`skip((1|2))`, `take((1|2))`, `[(1|2)]`) remain False;
  genuinely invalid forms stay False (`skip()`, `take(1,2)`, `single(1)`,
  `first(0)`, `foo()`, `[1.5].foo()`, `skip(%context, 1)`). **No
  over-acceptance regression from the newly added message prefixes.**
- SKEPTIC regression test `...test_subsetting_argument_type_error_validity_
  classification_fp05_skeptic`: 15 passed.

## Fresh probes (all dual-path: native ext vs forced Python fallback)

Probes at `/mnt/d/fhir4ds/.temp/qa/fp05_historian_2026_08_17/`
(probe.py 47 eval + 15 is_valid; probe2.py 20 eval + 8 is_valid).
**Zero parity diffs across all cases.** Highlights, all spec-correct:

- Computed/expression-valued num and index (`skip(1+1)`, `take(2*2)`,
  `skip(0-2)` → input, `take(0-2)` → empty, `[(1|1).single()]` → element,
  `skip(count()-1)` on data fields).
- `skip(1.0)`/`take(2.0)`: Integer-valued Decimals are still Decimals —
  execution type error → empty in both engines (consistent with §5.3
  `num: Integer` + the accepted execution-type-error doctrine).
- Overflow: `[2147483647]`/`[2147483648]` → empty; `skip/take(2147483648)`
  → error→empty; both engines agree.
- Strings: `'abc'[1]`/`'abc'.skip(1)`/`'abc'.tail()` → empty, `'abc'.first()`
  → ["abc"] — strings are singletons, not char collections; consistent in both.
- FP-02 derived-unit equality flows through §5.4 exactly as through `=`:
  `1 'kJ'` intersects/excludes/is-deduped-by `1000 'J'`; `combine` never
  dedups (count 2); `1 'm2/m'` = `2 'm'`-class collapse via intersect.
- Cross-type equality: `true.union(1)` → 2 items; `1` ≠ `'1'` for
  intersect/exclude.
- Objects as members: `name.intersect(name)` dedups to the same 2 objects;
  `exclude(self)` → empty; `combine(self)` keeps 4.
- Error propagation: `(1|2).single().first()` → empty; union/exclude/
  intersect with `{}.single()` (empty, NOT error) as operand behave as the
  empty-operand corners; `skip($this)` / `skip($index)` → error→empty.
- is_valid doctrinal consistency: `skip(1)` on empty focus and `skip(skip)`
  are True on both engines — grammatically valid, evaluate to empty;
  consistent with the validity-not-emptiness doctrine (probe-authoring
  "want" guesses, not violations).

## Issues found

None. Zero new CRITICAL/HIGH/MEDIUM issues.

## Validation

Full conformance (context-protected summary): ViewDefinition 144/144,
FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832 — baseline
holds. Recommend CLEAN exit at min_iterations=1.
