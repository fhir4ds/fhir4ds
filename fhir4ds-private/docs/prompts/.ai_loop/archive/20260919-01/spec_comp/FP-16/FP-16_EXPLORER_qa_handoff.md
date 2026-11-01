# QA Handoff — FP-16 EXPLORER launch (2026-08-18)

**Chunk**: FHIRPath §6.4 Collections — `|` (union), `in`, `contains`
**Personality**: EXPLORER (boundary/combination fuzzing)
**Probe**: `/mnt/d/fhir4ds/.temp/qa/fp16_explorer2_probe.py` (51 dual-path cases + helper-API spot checks)
**Result**: **0 parity mismatches, 0 new issues.**

## What was probed (all on native C++ AND forced Python fallback, identical output)

- Multi-operand union chains: `(3|1|3|2|1|4)` → 4 distinct, first-occurrence
  order preserved (`first()`=3, dedup order `[3,1,2,4]` confirmed at helper
  level too); field unions across heterogeneous element types dedup correctly.
- Union + `repeat()` fixpoint: `(1|2).repeat(iif($this<4,$this+1,{}))` = 3 —
  projection-only dedup per FP-04 doctrine; `(1).repeat($this|$this)` = 1.
- Error-typed operands: `1 in (1|(1/0))` → true (1/0 is `{}` not an error);
  `(1/0) in (1|2)` → empty (left empty → empty per §6.4.2);
  `(1|(1/0)) contains 2` → false. Membership does not spuriously error.
- Heterogeneous collections (string|int|bool|quantity|date): union count,
  membership hits/misses all correct.
- Boolean chains: `in`/`contains` results feeding `and`, `or`, `= true`, and
  `iif()` criterion — all correct.
- `in`/`contains` inside `where`/`select` over resource collections (obs
  elements): `status in ('final'|'preliminary')`, `valueString in (...)`,
  `('final'|'unknown') contains status`, `select(valueQuantity.value in (5|6))`
  — all correct. Note: `obs.where($this in obs)` → 0 is CORRECT — the bare
  identifier `obs` navigates from `$this` (i.e. `$this.obs` = empty), it does
  not re-resolve the outer collection.
- `contains` operator vs `contains(substring)` function in nested positions:
  `'final'.contains('in')` is the substring function (true); operator form
  only with collection left operand — disambiguation correct in `where` over
  union results.
- Null elements: `nulls.count()`=2 (count excludes nulls), `(nulls|nulls)`
  dedups nulls → 2, `(nulls|1) contains 1` → true / `contains 5` → false.
  Multi-item left `nulls in (...)` raises at core (SKEPTIC fix intact;
  helper API raises exact engine messages) and is converted to NULL by the
  DuckDB wrapper (row resilience, intended).
- Temporal partial-precision membership at all probed precision pairs
  (year/month/day/hour/minute, Time values): equal-precision hit true,
  any precision-mismatch false (empty ≠ true) — both engines.
- Quantity membership: cm/mm/m family, g/mg, calendar-vs-UCUM
  (`1 'a'` vs `1 year` → false both directions), `'s'` vs `second` → true,
  `(1 'g'|1000 'mg')` dedups to 1.
- Deep resource dedup at scale: `(deeps|deeps)` = 2 distinct (of 3 with dup),
  `deeps[0] in deeps` → true, projected union dedup over `obs.select(status)`.

## Verified strictness (engine/helper level)

- `operators.membership` multi-item left raises "in requires the left operand
  to contain at most one item"; `operators.contains` multi-item right raises
  its exact engine message. FP-16 SKEPTIC fix intact.

## Baseline

Conformance run post-probe: see `.temp/qa/fp16_explorer2_validation.log`
(expected 2832/2832; result recorded in architect handoff).

## Conclusion

No CRITICAL/HIGH/MEDIUM issues found. Chunk remains CLEAN after the third
personality launch (SKEPTIC → HISTORIAN → EXPLORER).
