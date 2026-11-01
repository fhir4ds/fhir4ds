# Scribe — v0.0.20 release commit drafts

## Commit 1: release bump + docs + WASM surfaces (everything currently staged/committed on dev since the campaign start)

```
chore(release): v0.0.20 — perf optimizations, DuckDB 1.5.6, serve layer, terminology provenance

RELEASE HIGHLIGHTS:

Performance (Phase 1+2, measured on 5k-patient Synthea cohorts):
- Shared per-resourceType retrieve CTEs (AS MATERIALIZED): CMS130 scans
  43->10, amplification 42x->9x; CMS130 -79% (DuckDB 1.5.5) / -98% (2.0.0)
- _patients CTE rebuilt as single Patient scan
- in_valueset global-mutex serialization fixed (8.3x hot path, C++ ext)
- Conditional CTE materialization by reference count
- All 27 measure/rung cells population-identical to baseline

DuckDB 1.5.6 support:
- 1.5.6 breaks the 1.5.5 extension ABI; wheel now bundles THREE binaries
  per extension (v1.5.5, v1.5.6 .duckdb156_extension, v2.0 .duckdb2_extension)
- Loader dispatch now patch-aware on the 1.5 line; plain pip install
  fhir4ds on duckdb 1.5.6 loads native C++ (no silent Python fallback)
- Base pin stays >=1.5.5,<2; 2.0.0 remains opt-in via [duckdb2] extra
  (upstream 2.0 optimizer pathology on CMS2-class SQL, duckdb#28181)
- v1.5.6-ABI binaries: fhirpath d97399d8, cql 9368557e (C++ source port
  for the 1.5.6 API: vector headers merged, ToUnifiedFormat count param,
  scalar-bind signature, pthread-rwlock shared_mutex shim)

FHIR serve layer (fhir4ds.serve, phases 1-3):
- FHIR R4 HTTP surface: search, $cql facade, library/viewdefinition
  endpoints, typed search, conditional create/update
- FHIR-native writes + append-only publish store
- Container image (deploy/docker/fhir4ds-serve)
- 235 serve tests + container smoke; 7 independent review findings landed

VD form editor (cleanroom):
- Guarded Form <-> Raw editing for ViewDefinitions
- Unsupported fields flagged, never dropped

Terminology:
- medterm4ds pin 0.0.7->0.0.8 (licensing/canonical release; integration
  surfaces unchanged, re-verified against the PyPI wheel)
- Provenance rule: in-process terminology search pins
  MEDTERM4DS_LAYOUT=terminology (import-free filesystem check) so serving
  binds the HuggingFace fhir4ds/terminology release; no silent fallback
  to stale legacy caches

QA:
- Full 12-domain x 3-personality evolution pass (zero engine defects)
- Structural-cost benchmark suite (benchmarks/scaling/) with EXPLAIN
  ANALYZE attribution and ranked optimization candidates
- DQM conformance 48/48 at 100%

Version surfaces: pyproject + 9 subpackage __version__ -> 0.0.20; ALL
WASM examples rebuilt + redeployed at 0.0.20 (wasm-demo, cql-cleanroom,
cql-clinic, viewing-room, bulk-publisher); notebooks re-executed;
release notes + PRODUCT_VERSION badge; website build clean.
```

## What's already on dev (from the campaign, in order):

1. `cfa5167` chore(deps): medterm4ds pin 0.0.7->0.0.8
2. `0f53e84` qa(v0.0.20): evolution D1-D2 CLEAN
3. `467cffd` qa(v0.0.20): evolution COMPLETE 12/12 CLEAN
4. `0cb915d` fix(terminology): pin medterm4ds search provenance
5. `e0783fd` feat(extensions): DuckDB 1.5.6 support
6. (merge commits: docs-matrix, serve-layer, vd-form-editor)
7. `0fb26fa` fix(deps): duckdb base pin <2
8. `80fef08` test/chore: QA-016 guard + ruff
9. Release commit: version bump + docs + WASM + notebooks

All commits are on local dev; nothing pushed. Joel reviews and pushes.
