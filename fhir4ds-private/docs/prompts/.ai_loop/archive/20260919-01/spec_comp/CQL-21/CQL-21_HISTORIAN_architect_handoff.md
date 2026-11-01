# Architect Handoff — CQL-21 HISTORIAN audit (iteration 1)

## Golden standard (focused)
See `.temp/architect/golden_standard.md`. The launch's diff was audited
against the CQL Translator Invariants and dual-engine lockstep rule.

## Audit findings
- **Dual-engine lockstep: PASSES.** cqlUncertainMin/Max/ListMin/ListMax
  implemented in Python (`udf/datetime.py`) and native
  (`cql_extension.cpp`, DEFINE_UNCERTAIN_ARITH/LIST_MINMAX macro family,
  registered via RegisterSpecialScalar); parity test covers py + cpp
  connections; no-Python engine verified manually (9 cases) — the new
  UDFs resolve purely natively.
- **No silent fallbacks / no SQLRaw: PASSES.** The in-list fix lowers to a
  typed OR chain of cqlUncertainCompare; negation reuses
  cqlUncertainMultiply per -x ≡ x * -1 (§16.8); no fixture-specific
  branches. The old BIGINT-cast normalization for
  `-cqlDurationBetween(...)` was REMOVED (it silently NULLed uncertain
  ranges) — strictly better.
- **Layering: PASSES with a note.** Three emit sites had to be touched for
  list Min/Max (dispatcher, `_translate_aggregate_pre`, `_lists.py`). This
  repetition is pre-existing structure (multiple aggregate lowering
  paths); recommend a future refactor consolidating list-aggregate
  lowering, out of chunk scope.
- **Residual gap (LOW, QA-005 DEFERRED):** uncertainty-capable elements
  inside DYNAMIC (non-literal) lists still lower to CQLListContainsEq and
  would not match interval-JSON values. Age is a per-patient scalar in
  practice, so no real-world CQL pattern is known; documented in AGENTS.md.
- **Deployment invariant: PASSES.** md5 da6c07adb08ef224d0621b9d222b6bae
  identical across build output, repo bundle, site-packages; ~/.duckdb
  cache cleared; fix re-verified through a fresh connection.

## QA Enforcer Gate
QA (HISTORIAN) was NOT lazy: it re-verified the SKEPTIC fix's core
semantics with fresh probes (all conformant), hunted NEW divergences
(in-list, Min/Max, negate — all real, spec-cited, dual-engine evidenced),
spotted and repaired a stale site-packages binary, and hit the eCQM-core
regression concern via the DQM gate. RETRY_QA = false.

## Validation (final tree)
run_all.py fresh: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
DQM 47/47 — OVERALL 2832/2832, baseline held. Focused: clinical parity
17/17; age+datetime+v2 units 243/243.

## Exit
Iteration 1 ≥ min_iterations 1; zero non-terminal CRITICAL/HIGH/MEDIUM
issues (QA-004, QA-005 terminal DEFERRED). Clean exit.
