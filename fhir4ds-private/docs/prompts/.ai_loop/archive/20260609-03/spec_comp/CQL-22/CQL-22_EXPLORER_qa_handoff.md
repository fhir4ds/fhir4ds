# QA Handoff - CQL-22 EXPLORER

## Scope
- Chunk: CQL-22, Errors and Messaging.
- Personality: EXPLORER.
- Target item: `Message(source, condition, code, severity, message)`.
- Spec anchor: CQL 1.5.3 Reference Appendix B, Errors and Messaging. The current signature is `Message(source T, condition Boolean, code String, severity String, message String) T`; source is returned unchanged unless a true condition with Error severity raises a runtime error.

## Probe
- Created and ran `.temp/qa/cql22_explorer_probe.py`.
- Covered non-String `code`, invalid `condition` hidden by `as Any` / `convert ... to Any`, invalid `severity` and `message` hidden by aliases, Boolean condition allowed through `as Any`, primitive/list/Quantity/tuple source preservation, dynamic `Patient.active` condition, and Python fallback/native-loaded/no-Python parity.

## Finding
- `CQL22-EXPLORER-001` HIGH: translated `Message(...)` rejected non-Boolean conditions and non-String severity/message operands, but accepted statically known non-String `code` operands such as `Message('src', true, 400, 'Warning', 'boom')` and `define C: 400 as Any; Message('src', true, C, 'Warning', 'boom')`.
- Actual behavior: translation succeeded and allowed the SQL/runtime helper to cast the code.
- Expected behavior: translation should fail before SQL lowering because the published CQL signature declares the code operand as String.

## Validation Snapshot
- Fresh probe now passes after the focused remediation.
