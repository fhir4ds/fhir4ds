# QA Handoff — FP-03 HISTORIAN (iteration 1, 2026-08-17)

## Chunk
FHIRPath §5.1 Existence: empty(), exists([criteria]), all(criteria),
allTrue(), anyTrue(), allFalse(), anyFalse(), subsetOf(other),
supersetOf(other), count(), distinct(), isDistinct().

## Method
- Spec grounding: N1 v2.0.0 §5.1.1–§5.1.12, §5.2.1 criteria singleton
  rules, §4.5 singleton evaluation, §6.1.1 (`=` for membership/distinct),
  §6.2 (type-error vs spec-mandated-empty doctrine), reused from the
  SKEPTIC pass's fetched spec plus institutional memory.
- Dual-path probes (native extension vs Python fallback, 5 channels +
  fhirpath_is_valid), run with `PYTHONPATH=/mnt/d/fhir4ds`:
  - `probe.py`: 64 pre-registered HISTORIAN cases (R1 fix re-verification,
    H1 FP-01 calendar-equality interactions, H2 FP-02 derived/exponent-unit
    interactions, H3 decimal/negzero/overflow distinctness, H4
    equality-empty membership corners, H5 criteria conversion/empty-vs-
    error, H6 count on quantities, H7 scope restoration).
  - Battery 2 (35 cases): JSON-null collections, resource-node membership,
    other-argument errors, duplicate corners, trace passthrough.
  - Battery 3 (42 cases): exists(c) ≡ where(c).exists() shorthand
    equivalence (incl. empty and error criteria), negation in criteria,
    supersetOf duplicate/coverage corners, partial subsetOf coverage,
    decimal JSON values in criteria, is_valid arity oddities.
  Total: 141 fresh dual-path evaluations. Workspace:
  `/mnt/d/fhir4ds/.temp/qa/fp03_historian_2026_08_17/`.

## Results — ZERO parity diffs, ZERO new spec violations
- R1: both SKEPTIC fixes verified intact on both engines: mixed-type
  comparison errors inside all/exists/where/iif → empty (QA-001), and
  time-string ordering coercion removed in the fallback (QA-002), plus
  6 neighbor variants (bool ordering, where().count(), error chains).
- H1 (institutional-memory target): FP-01 calendar-equality flows
  correctly into §5.1 — `1 month subsetOf (30 days|7 days)` true,
  `1 year|365 days distinct().count()`=1, `1 'wk'|1 week`→1,
  `1 month|1 'mo'` stays 2 (fixture-pinned empty equality), `1 'mo'
  subsetOf 29 days` false.
- H2: FP-02 derived units (`1 'kJ'|1000 'J'`→1 distinct) and exponent
  merge (`1 'm2/m'|1 'm'`→1; `12 'cm2'/3 'cm' subsetOf 4 'cm'` true)
  flow correctly into membership/distinctness in both engines.
- H3: `(1.0|1.00000).distinct()`→1, `(-0.0|0.0)`→1, overflow-promoted
  `2147483647+1` dedups with `2147483648.0`; §5.1.12 shorthand holds via
  `combine`.
- H4: equality-EMPTY members behave as "not a member / still distinct"
  (offset temperatures, g-vs-cm, @2012 vs @2012-01) — consistent in both.
- H5/H6/H7: exists(c)≡where(c).exists() equivalence verified on true/
  false/empty/error criteria; `all(missing)`→false (not vacuous true);
  criteria errors propagate as empty; count() Integer, empty→0, JSON-null
  array elements skipped; $index exposure + scope restoration intact;
  is_valid rejects all malformed arities on both surfaces.
- Spec-checked non-findings (documented shared conventions, both engines
  agree, out-of-chunk grammar scope): prefix `not (...)` inside criteria
  → empty (unary `not` is not FHIRPath grammar; `.not()` works);
  bare root paths like `nums` inside criteria resolve against $this, not
  the root, so `nums.exists($this = nums.count())` is false.
- Regression validation: `test_existence_parity.py` 16/16 passed; full
  conformance 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).

## Issues logged
None. Zero non-terminal CRITICAL/HIGH/MEDIUM/LOW issues. Clean-exit
criteria met at iteration 1 (min_iterations=1).
