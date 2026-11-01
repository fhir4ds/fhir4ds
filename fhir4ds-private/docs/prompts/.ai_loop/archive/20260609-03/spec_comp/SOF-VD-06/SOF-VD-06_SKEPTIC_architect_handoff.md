# Architect Handoff: SOF-VD-06/SKEPTIC

Golden standard:
- ViewDefinition parser boundaries must distinguish absent optional fields from present invalid JSON values.
- `forEach` and `forEachOrNull` are optional `0..1 string` FHIRPath primitives.
- Row-generation behavior must preserve native/default and forced Python fallback parity for flattening, null-row preservation, nested focus, and built-in variables.

Audit result:
- Structural health is sound after remediation.
- The fix is localized to strict JSON parsing in `parser.py`; it does not change direct dataclass omission semantics or SQL generation behavior.
- Parser regression coverage now includes present-null iterator fields.
- Fresh probe coverage is adequate for the chunk: malformed/null/non-string iterator fields, mutual exclusion, row multiplication/suppression, `forEachOrNull` null-row preservation, nested iterator focus, `%context`, `%resource`, `%rootResource`, and `%rowIndex` under native/default and forced Python fallback.

Issue status:
- `SOFVD06-SKEPTIC-001`: VERIFIED.
- No new architecture findings.
- `RETRY_QA`: not needed.

Validation reviewed:
- Fresh SOF-VD-06 probe: PASS.
- Targeted parser/forEach/DuckDB pytest: `268 passed`.
- Full ViewDefinition pytest: `950 passed`.
- ViewDefinition conformance: `134/134`.
- Full conformance: `2822/2822`.

Notes:
- `ARCHIVE_LOG.md` was intentionally not modified because this bounded pass was instructed not to archive or touch schedule/archive files.

