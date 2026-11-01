# Architect Handoff — SOF-VD-01 EXPLORER (iteration 1, 2026-08-23)

## Summary
EXPLORER QA probed the full SOF-VD-01 edge matrix (resource case/whitespace/
empty/unicode/long forms; fhirVersion across every natural code form and
duplicates; profile canonical edges incl. relative, `|version`, urn, `#frag`,
duplicates, 150 entries; resourceType filtering with contained and
bundle-nested same-type resources; profile-informative semantics; zero-row
VDs through where/forEach; fhirVersion-declared-but-R6-path stance; multiple
VDs in one DuckDB session; end-to-end execution). One HIGH found and fixed:
`FHIR_VERSION_CODES` covered only the 24 top-level codes, rejecting valid
`4.0.1`/`5.0.0`/`6.0.0`/milestone codes. Engineer expanded the set to the
full 60-code codesystem list (fhir4ds/viewdef/metadata.py), inverted the
now-wrong rejection test, added a 24-case acceptance parametrization plus a
genuinely-invalid rejection set (test_parser.py). Validation: reproducer
passes, viewdef pytest 1153/1153, ViewDef conformance 144/144, master gate
2832/2832; binaries unchanged and md5-matched (cql c5b22d58…, fhirpath
57d0634b…). QA-001 RESOLVED.

## Structural health
- Golden standard (10 invariants, `.temp/architect/golden_standard_sof_vd_01.md`)
  re-audited post-fix: all hold. Binding knowledge remains centralized in
  metadata.py (data-driven doctrine). No architecture drift logged.
- QA Enforcer Gate: QA was thorough; no veto (RETRY_QA not set).

## Issues
- QA-001 HIGH -> RESOLVED (tombstoned in evolution.json; archived).

## Recommended fix order
None — no open issues. Clean exit at min_iterations=1.
