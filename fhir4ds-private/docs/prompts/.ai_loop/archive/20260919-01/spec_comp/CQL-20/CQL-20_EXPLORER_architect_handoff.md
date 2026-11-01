# CQL-20 EXPLORER Architect Handoff (iteration 1)

## Golden-standard invariants applied (CQL aggregate surface)
1. CQL Decimal results (§2.3, Appendix B) must be computed with DECIMAL-class
   precision; DOUBLE is only acceptable where the result is irrational (sqrt).
2. Dual-engine lockstep: a semantic fix must hold on py, cpp, and no-python
   surfaces (pure SQL macros satisfy this without extension rebuilds).
3. No silent fallbacks masking errors; explicit type guards error loudly.
4. Lowering helpers must respect DuckDB structural constraints (no subqueries
   in lambda bodies).

## Audit of this iteration's fix (QA-001)
- **Conforms.** The shifted-decimal form is general (no value/test-specific
  branches), applies uniformly at the translator static site and the SQL
  macros, and the dispatch site is correctly restricted to SQLArray operands
  so dynamic subquery lists never embed anchors in lambdas (invariant 4).
- **Duplication observation (LOW, deferred):** the shifted expression now
  exists at three sites (static branch, dispatch branch, macros). This
  extends the pre-existing "lowering duplication" DEFERRED theme from
  SKEPTIC's launch. A shared `_shifted_decimal_statistical(...)` SQL builder
  would consolidate; deferred to avoid churn on a DQM-sensitive surface.
- No hardcoding, no schema/IG knowledge leaked, no silent fallback added
  (DOUBLE path retained for dynamic/integral operands is documented,
  behavior-preserving).

## QA quality gate (EXPLORER)
Sufficient. Probed: full null/empty/all-null matrix for all 15 aggregates
against the fetched spec text; single-element stats; GeometricMean
zero/negative/huge; Min/Max equal dates and quantities; Integer/Long Sum
overflow; nested aggregates; union sources; multi-patient retrieve isolation
through population SQL; statistical precision at DECIMAL(38,8) boundaries
(mandated item — this is where the find landed). Three engine modes
throughout. No RETRY_QA.

## Terminal state
- QA-001 RESOLVED (verified: aggregate parity 35/35; full gate 2832/2832).
- QA-002 LOW DEFERRED (GeometricMean double artifact ≥1e13; needs decimal
  ln/exp/sqrt).
- QA-003 MEDIUM DEFERRED (query-as-query-source; CQL-05 QA-107 family,
  query-plumbing chunk owner).
- Zero non-terminal CRITICAL/HIGH/MEDIUM; iteration 1 >= min_iterations 1.
- exit_reason CLEAN; workflow null.

## Final-state validation (GATE DISCIPLINE review-35)
- `run_all.py` on final tree: ViewDef 144/144, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, OVERALL 2832/2832 — no DQM ERRORs, no retry needed.
- Extension binaries untouched; md5 repo == ~/.local site-packages:
  cql 3e7d4167143e01907fdd8561db43b7d7,
  fhirpath 57d0634b6ee6eddee9fc06a1355bef5a.
- Pre-existing (stash-bisect verified, not this launch): 2 failures in
  test_audit_mode.py TestMinMaxAttribution.
