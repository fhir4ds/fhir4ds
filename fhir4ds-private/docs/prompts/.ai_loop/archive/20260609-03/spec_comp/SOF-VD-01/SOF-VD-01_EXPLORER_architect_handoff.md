# Architect Handoff: SOF-VD-01 EXPLORER

Golden standard written/updated at `.temp/architect/golden_standard.md`.

Structural audit result: healthy for this SOF-VD-01 scope. The parser,
serializer, direct dataclass guardrails, generator validation, shared-table
resourceType predicate, and DuckDB execution path now share the same
single-root-resource contract for `ViewDefinition.resource`, while `profile`
and `fhirVersion` remain validated/preserved logical-model declarations that
do not alter row-producing SQL semantics.

QA quality audit: sufficient. The probe covered malformed root metadata,
direct dataclass bypasses, parser/serializer round trips, shared mixed-resource
execution, zero-row filters, multi-row expansion, null-preserving
`forEachOrNull`, and native/fallback FHIRPath registration. No `RETRY_QA`
needed.

Issues by category:

- SPEC_VIOLATION: 0
- API_CONTRACT: 0
- DATA_HANDLING: 0
- REGRESSION_RISK: 0

Recommended fix order: none. The pass is clean.

Validation summary:

- `.temp/qa/sof_vd01_explorer_probe.py`: PASS.
- Focused ViewDefinition pytest: 65 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: 2822/2822.

Operational note: this handoff did not modify `spec_schedule.json` or
`ARCHIVE_LOG.md`; outer orchestration should archive/finalize the pass.
