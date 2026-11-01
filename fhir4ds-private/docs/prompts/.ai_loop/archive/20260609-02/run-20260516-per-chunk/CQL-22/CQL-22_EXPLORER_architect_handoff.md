# Architect Handoff - CQL-22 EXPLORER

Structural audit result: CLEAN.

Golden standard captured in
`fhir4ds-private/docs/prompts/.ai_loop/.temp/architect/golden_standard.md`.
The remediation stays in the intended DuckDB adapter boundary: translated CQL
still emits `CQLMessage` only when runtime behavior is needed, the public helper
remains a typed macro that preserves the physical SQL type of `source`, and the
fix only coalesces nullable diagnostic text before `error(...)` so `Error`
severity cannot be converted into SQL NULL.

QA audit: Adequate. EXPLORER tested pathological NULL diagnostic operands,
condition/severity variants, source shape preservation, direct helper calls,
translated CQL, forced Python fallback, and native-loaded DuckDB registration.
No `RETRY_QA` needed.

Issue summary:
- `QA-001` HIGH resolved and verified.
- No new architectural findings.

Validation reviewed:
- Focused Message parity pytest: 5 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
- Full pytest: 7233 passed, 5 skipped, 9 warnings.

Recommended fix order: none. The active evolution workflow can clean-exit.
