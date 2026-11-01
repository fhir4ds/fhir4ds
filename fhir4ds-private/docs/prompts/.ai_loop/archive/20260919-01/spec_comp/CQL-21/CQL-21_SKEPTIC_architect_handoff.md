# Architect Handoff — CQL-21 (Clinical Operators), iteration 1

## Golden standard (audit lens)
See `.temp/architect/golden_standard.md`. Six invariants: dual-engine
lockstep, deployed-binary verification, fixtures-outrank-prose, the
scalar-or-interval VARCHAR uncertainty contract for duration-derived
scalars (with all consumers routed through cqlUncertain* UDFs), no silent
fallbacks, and class-level (not case-level) fixes.

## Audit verdict: STRUCTURALLY SOUND; QA was NOT lazy (no veto)
- The FIX correctly implemented the class: ALL age surfaces (bare
  AgeIn*(), one/two-arg AgeIn*At, CalculateAgeIn*, CalculateAgeIn*At) on
  BOTH engines now delegate to the §22.21 duration engine; comparisons,
  arithmetic, and `in Interval[a,b]` (closed AND open bounds) route through
  cqlUncertainCompare. Fixture adjudication was performed correctly (gate
  has 16 XMLs, no CqlAgeOperatorsTest.xml → spec prose governs).
- Two process findings (both self-corrected during FIX, logged as lessons):
  1. The deployed cql.duckdb_extension predated the last cql_extension.cpp
     edit (stale-binary hazard bit AGAIN — invariant 2). Rebuilt + redeployed,
     md5 82b234168290f6a6053b583d70e3d9d6 verified build == repo bundle ==
     site-packages, ~/.duckdb cache cleared.
  2. The age→VARCHAR change initially regressed the DQM suite (11 measures,
     raw SQL BETWEEN/comparison over VARCHAR) — caught at the Recovery Gate
     and root-cause-fixed in the interval-`in` lowering (both bound
     branches), restoring 47/47. Confirms the invariant that every consumer
     of duration-derived scalars must be audited when the type shape changes.
- Empirical: master gate fresh on final tree 2832/2832 (ViewDef 144,
  FHIRPath 935, CQL 1706, DQM 47). Clinical parity 51/51 incl. the new
  partial-birthDate regression (py+cpp); interval parity 60/60; age/datetime/
  arrow UDF suites pass. CQL unit suite run appended to stats when complete.
- Binaries: cql 82b234168290f6a6053b583d70e3d9d6, fhirpath
  57d0634b6ee6eddee9fc06a1355bef5a (repo == site-packages; no cache copies).

## State hygiene
QA-001 RESOLVED (tombstone in evolution.json; full evidence in
ARCHIVE_LOG.md). No new issues filed; no open CRITICAL/HIGH/MEDIUM.

## Recommended Fix Order
None — zero open issues. Exit criteria met (iteration 1 ≥ min_iterations 1,
no non-terminal CRITICAL/HIGH/MEDIUM) → CLEAN exit.
