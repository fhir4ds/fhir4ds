# Architect Handoff: SOF-VD-11 / EXPLORER

## Golden Standard
- Updated `.temp/architect/golden_standard.md` for this EXPLORER pass.
- Key invariant: iterator aliases may use physical JSON guards where FHIRPath `type().name` metadata is backend-dependent, but they must still enforce declared `column.type` boundaries.

## Structural Audit
- No new architectural findings.
- The remediation stays within `SQLGenerator`'s existing column-boundary responsibility: it does not add ViewDefinition-specific behavior to FHIRPath engines and does not hardcode resource/profile knowledge.
- The physical JSON guard is a narrow fallback for iterator contexts where the code already disables metadata guards; normal root-resource type checks still use FHIRPath `type().name`.
- `%rowIndex` validation is static and general: it enforces the environment variable's integer-valued contract rather than checking a specific fixture.

## QA Audit
- QA was sufficient. It tested the requested EXPLORER combinations: iterator aliases, `$this`, `%rowIndex`, declared SQL result types, native C++ registration, and forced Python fallback.
- No `RETRY_QA` needed.

## Issue Status
- `SOF-VD-11-EXPLORER-001`: VERIFIED.

## Validation Reviewed
- Fresh EXPLORER probe: PASS on native and forced fallback.
- Focused regression tests: `2 passed`.
- ViewDefinition tests: `979 passed`.
- ViewDefinition conformance: `134/134`.
- Full conformance: `2822/2822`.

State hygiene note: `ARCHIVE_LOG.md` was intentionally not modified because this bounded inner pass was instructed not to archive or touch outer-orchestrator bookkeeping.
