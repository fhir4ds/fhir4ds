SOF-VD-10/SKEPTIC architect handoff

Structural assessment:
- The fix preserves the intended ViewDefinition validation boundary: strict JSON parser and `ViewDefinition.from_dict()` reject malformed official JSON, while direct dataclass `None` continues to represent omitted optional metadata.
- The change is general across the affected root metadata field class and reuses the existing shared `validate_root_metadata_fields()` path after preserving present-null information.
- No new architecture drift was found. `validate_view_definition()` remains permissive, and SQL generation still revalidates direct dataclass input before emitting SQL.

Issue status:
- `SOF-VD-10-SKEPTIC-001`: VERIFIED. This also closes `REV-045-001`.

QA audit:
- QA was sufficient for this SKEPTIC pass. It attacked strict parser, `from_dict`, direct serializer, SQLGenerator preflight, official `expectError` fixtures, required-field/binding constraints, row-generator mutual exclusion, and permissive-versus-strict behavior. No `RETRY_QA` needed.

Validation reviewed:
- Fresh SOF-VD-10 probe passed.
- ViewDefinition unit/integration/spec pytest passed: 969/969.
- ViewDefinition conformance passed: 134/134.
- Full conformance passed: 2822/2822.

Recommended next work:
- None for this pass. Continue to the outer orchestrator for archiving/schedule handling.
