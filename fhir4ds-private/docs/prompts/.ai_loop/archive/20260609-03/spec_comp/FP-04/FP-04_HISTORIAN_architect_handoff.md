# Architect Handoff: FP-04 HISTORIAN

Golden standard: `.temp/architect/golden_standard.md` defines the Section 5.2
architecture expectations for criteria strictness, projection flattening,
repeat equality de-duplication, type-specifier validation, native/fallback
parity, and bundled-extension freshness.

Audit summary: the fix is structurally sound and narrow. It preserves the
existing split between strict expression validity and row-resilient public
result UDFs: wrong `ofType` arity now fails validation, while public result
surfaces still return empty/NULL through the existing spec-error handling path.
The change is general for all missing `ofType` type arguments and does not add
resource-specific or test-specific branching.

QA quality assessment: sufficient. HISTORIAN covered every mandatory Section
5.2 function and included criteria truthiness/error cases, projection
flattening, repeat traversal/de-duplication, model type validation, and both
native C++ and forced Python fallback outputs. No `RETRY_QA` veto.

Issue counts: 1 MEDIUM SPEC_VIOLATION found and resolved; 0 open issues.
Recommended fix order: none. Do not archive in this run per user directive; the
outer orchestrator will handle archival.
