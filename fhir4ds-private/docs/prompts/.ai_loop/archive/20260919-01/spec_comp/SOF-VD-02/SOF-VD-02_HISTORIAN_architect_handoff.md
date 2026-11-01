# Architect Handoff — SOF-VD-02 (HISTORIAN), iteration 1 — exit CLEAN

## Golden Standard (chunk-scoped invariants, verified)
1. Constant value[x] substitution must always emit a *valid FHIRPath literal* (int32 range for integers; plain fixed-point decimals; escaped strings) or raise a typed ConstantResolutionError — HOLDS after this launch (integer64 guard from SKEPTIC + decimal plain-notation fix).
2. Authored constant precision must survive parse → substitute end-to-end (FHIR decimal 18 digits) — HOLDS (`parse_float=Decimal`).
3. Validation lives at dataclass/parser/generator boundaries with typed errors; no fixture-specific branches in `resolve_constant` — HOLDS (fix is fully generic; `repr()` float path is shortest-round-trip, not test-tuned).
4. Engines may not diverge: fix is in textual substitution upstream of both engines; native + fallback probed in agreement.

## Audit findings
- QA-001, QA-002 RESOLVED→VERIFIED (see tombstones in evolution.json; full evidence archived to ARCHIVE_LOG.md). Fix quality good: root-cause, minimal footprint, 9 new focused tests, spec_compliance decimal assertion correctly migrated to Decimal.
- AR-001 LOW DEFERRED: extreme-exponent valueDecimal (1e999999999) expands to ~1GB literal in ~1s (memory amplification; author-controlled input; no spec magnitude bound). Recommend a ConstantResolutionError guard mirroring integer64 when adopted.
- QA Enforcer Gate: no veto. HISTORIAN launch found 2 new MEDIUM spec violations the SKEPTIC pass missed, verified the IG live, reproduced end-to-end in both engines, and re-verified the prior integer64 fix regression-free.

## Validation evidence (final tree, PYTHONPATH=repo)
ViewDef pytest 1168/1168; master gate ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832. fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a (repo == site-packages, unchanged). Site-packages Python copy of constants.py is stale relative to repo — harmless for repo-gated runs.

## Structural health
Constants chunk (SOF-VD-02) now spec-conformant across parse/validate/substitute/execute in both engines. Exit: CLEAN at iteration 1 (>= min_iterations 1, zero open CRITICAL/HIGH/MEDIUM).
