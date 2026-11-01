# QA Handoff — SOF-VD-12 SKEPTIC (metadata/profiles)

## Verdict: CLEAN — 12/12 fresh cases (flagged=0)

Verified: Shareable profile requires url+name+status+fhirVersion+Column.type
(all missing-field permutations -> typed ParseError via
validate_supported_view_profiles); Tabular forbids collection columns +
requires primitive types; both profiles valid when complete; canonical
metadata (url/version/status) does not break generation; unknown top-level
keys (publisher/purpose/copyright) retained through round-trip; informative
profile[] + non-canonical meta.profile entries accepted; full metadata set
executes.

Evidence: .temp/qa/speccomp2/sofvd12_skeptic_probe1.py
