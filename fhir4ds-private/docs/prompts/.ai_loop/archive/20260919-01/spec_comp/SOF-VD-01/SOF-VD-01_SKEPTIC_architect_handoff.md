# Architect Handoff — SOF-VD-01 (2026-08-23, iteration 1)

## Structural health: SOUND (audit PASS)
Golden standard (`.temp/architect/golden_standard_sof_vd01_2026_08_23.md`):
6 falsifiable invariants for the chunk — root-binding metadata centralized in
`viewdef/metadata.py`, FHIR_VERSION_CODES matching the IG's actual binding
edition, profile/fhirVersion non-row-producing, shared strict/permissive
boundary split, root-row-only resourceType filter, no hardcoded model
knowledge. All six hold post-fix. No duplicate FHIR-version allowlists exist
(CQL's `using FHIR version '4.0.1'` literals are a different, correct spec
surface). No new drift-log entries; no RETRY_QA (QA was rigorous: 7
pre-registered hypotheses, live spec/code-system fetching across R4/R4B/R5/R6
+ IG sushi-config, both binding directions, DuckDB execution, official
fixtures incl. expectError semantics).

## Handoff compression
QA (SKEPTIC) probed resource 1..1 binding (9 malformed shapes), profile
canonical validation + informative non-filtering runtime semantics, fhirVersion
binding, shared-table root-row resourceType filtering (incl. unionAll branches,
contained same-type non-leakage), zero/multi-row + forEachOrNull semantics,
default per-type table, generator-reuse state, official view_resource.json
end-to-end. One HIGH: stale R4B-era FHIR_VERSION_CODES rejected spec-valid
two-segment codes and accepted out-of-binding three-segment/milestone codes.
Engineer fixed at the single choke point (metadata.py), updated ~12 stale test
expectations, added 9 regression tests. Gate discipline held: probe 39/39,
ViewDef pytest 1127/1127, ViewDef conformance 144/144, master gate 2832/2832;
binaries unchanged and repo == site-packages (cql c5b22d58..., fhirpath
57d0634b...).

## Issues by category
- SPEC_VIOLATION: 1 (QA-001 HIGH) — RESOLVED, verified iteration 1 (archived).
- Open: 0.

## Exit
iteration 1 >= min_iterations 1; zero non-terminal CRITICAL/HIGH/MEDIUM →
CLEAN exit. Recommended next: none for this chunk; refresh FHIR_VERSION_CODES
from build.fhir.org when FHIR publishes new versions (noted in AGENTS.md).
