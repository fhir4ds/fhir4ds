# Architect Handoff — SOF-SQ-01, HISTORIAN launch (iteration 1)

## Structural audit of this launch's fixes

Golden-standard invariants applied (from AGENTS.md doctrine + chunk mandate):
verbatim roundtrip fidelity; typed rejection paths; model knowledge
data-driven; no silent fallbacks; minimal footprint.

Findings:
- QA-001/002 fix (extra_fields bags at all four levels + verbatim
  meta/type_concept) is structurally correct: merge order guarantees modeled
  keys win over extras, extras can never collide with modeled keys because
  the parser excludes them at capture time, and repr/compare=False keeps the
  bags out of equality semantics. Matches the §G-3 ViewDefinition
  extra_fields doctrine.
- QA-003 fix routes parameter.type validation through the existing
  fhir_type_to_duckdb registry — data-driven, no new hardcoded type list.
  The parser→viewdef.types import mirrors the existing runner dependency;
  acceptable coupling (both are spec-layer type registries).
- QA-004/005 fixes enforce base-Resource and fixed-code-system constraints
  with typed errors; no behavior branches on specific resources.
- No test-driven hacks, no silent fallbacks introduced. One pre-existing
  minor wart observed (not new): SQLRelatedArtifact.resource_type is never
  set by the parser (always None) — dead field, LOW cosmetic, not logged.

## Empirical validation

- fhir4ds/sqlquery/tests: 70/70.
- Master gate: OVERALL 2832/2832 (PROC_VALIDATION.md baseline held).
- Binary md5s (repo == site-packages, unchanged): cql c5b22d58310c1eb7bafa17ce7877f989,
  fhirpath 57d0634b6ee6eddee9fc06a1355bef5a. No native changes this launch.

## QA Enforcer Gate

QA (HISTORIAN) performed a genuine full-differential walk of
library-profiles.fsh beyond the SKEPTIC's probes, with reproducer evidence
for every issue and machine-artifact citations. No veto. RETRY_QA not set.

## Iteration summary (compressed)

QA found 5 new divergences (1 HIGH roundtrip data loss, 1 MEDIUM canonical
rewrite, 3 LOW parse-time enforcement gaps); engineer fixed all 5 at root
cause in types.py/parser.py with 15 new regression tests; sqlquery suite
grew 55→70, master gate 2832/2832. Clean exit at iteration 1 (min 1, zero
non-terminal CRITICAL/HIGH/MEDIUM).
