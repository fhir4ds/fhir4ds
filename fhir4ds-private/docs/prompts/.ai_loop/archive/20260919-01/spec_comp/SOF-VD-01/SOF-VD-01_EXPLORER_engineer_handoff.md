# Engineer Handoff — SOF-VD-01 EXPLORER (iteration 1, 2026-08-23)

## QA-001 (HIGH) — RESOLVED
- Root cause: `FHIR_VERSION_CODES` (fhir4ds/viewdef/metadata.py) held only the
  24 top-level `[publication].[major]` codes. The required binding
  http://hl7.org/fhir/ValueSet/FHIR-version includes
  http://hl7.org/fhir/FHIR-version with no filter => all 60 concepts
  (both hierarchy levels) are valid.
- Fix: expanded the frozenset to the full 6.0.0-ballot4 codesystem concept
  list (full versions `4.0.1`/`5.0.0`/`6.0.0`, milestone suffixes
  `-cibuild`/`-snapshotN`/`-ballotN`/`-draft-final`, pre-1.0 `0.0.8x`).
- Tests: test_parser.py — `test_fhir_version_accepts_full_version_and_milestone_codes`
  (24 parametrized valid codes) and rejection set now uses genuinely-absent
  codes (`4.0.2`, `7.0.0`, `6.0.0-ballot9`, `5.0.0-rc1`, `4.0.1 `, `4.0.1-beta`).
  The old rejection test asserting `4.0.1` is invalid was inverted by the fix
  and rewritten.

## Validation
- Reproducer: `fhirVersion: ["4.0.1","6.0.0-ballot4"]` parses OK.
- viewdef pytest: 1153/1153.
- ViewDef conformance: 144/144.
- Master gate: 2832/2832 (ViewDefinition 144, FHIRPath, CQL 1706, DQM 47).
- Binaries unchanged: cql ext md5 c5b22d58310c1eb7bafa17ce7877f989,
  fhirpath ext md5 57d0634b6ee6eddee9fc06a1355bef5a — repo bundle ==
  site-packages (no native rebuild needed; fix is pure Python metadata).

## Files changed
- fhir4ds/viewdef/metadata.py
- fhir4ds/viewdef/tests/unit/test_parser.py
