# Architect Handoff — FP-20 EXPLORER

Golden standard written to `.temp/architect/golden_standard.md`. The FP-20 EXPLORER remediation is structurally narrow: it corrects one native primitive metadata classification, adds native/fallback parity tests, adds native SQL assertions, and refreshes the bundled extension.

Architectural assessment: no new chunk-blocking architecture issue. The implementation touches the existing native `fhirFieldType()` metadata table, which is already covered by review-15 `REV-005` model-knowledge debt. That broader generated/shared metadata registry remains the correct long-term fix, but it is already tracked outside this chunk and does not leave an open FP-20 EXPLORER defect.

QA quality audit: adequate. The EXPLORER probe covered edge combinations beyond the prior SKEPTIC/HISTORIAN passes, including external constants with hidden tokens, scoped environment variables, TypeInfo chaining, invalid/qualified types, URI/media/code fields, row-resilient invalid expressions, direct fallback helpers, and native/fallback wrapper parity. No `RETRY_QA` veto.

Issue summary: 1 MEDIUM `SPEC_VIOLATION` found and resolved (`QA-001`). Recommended fix order: none remaining for this pass.

Validation evidence: fresh probe 81 cases and 16 validity checks with 0 mismatches; focused pytest 9 passed; native fhirpath sqllogictest 356 assertions passed; full conformance 2822/2822.
