# Architect Handoff: SOF-VD-09 / SKEPTIC

## Golden Standard

Wrote `.temp/architect/golden_standard.md` for root `where` behavior. The core
invariant is that root `ViewDefinition.where` is a shared logical-model
boundary: parser, `ViewDefinition.from_dict()`, `ViewDefinition.to_dict()`,
nested `Select.to_dict()`, and `SQLGenerator.generate()` must use the same
condition validation before official JSON or SQL is produced.

## Structural Audit

The implemented fix is structurally sound. It reuses the existing
`validate_where_conditions()` helper at the missing root serializer boundary,
matching parser and generator behavior without adding parallel rules or
runtime special cases. The change preserves valid `where.description` metadata,
keeps empty in-memory root `where` as absence/no filter, and keeps runtime row
filtering unchanged.

QA quality was sufficient. The fresh probe attacked missing/null/non-string
shape boundaries, root serializer/generator parity, constants in root `where`,
every-constraint-true semantics, false/empty/non-Boolean exclusion, shared
resource filtering, and root-resource scope under `forEach`, with native-loaded
and forced Python fallback execution.

## Issue Status

- `SOFVD09-SKEPTIC-001`: VERIFIED. No open SOF-VD-09/SKEPTIC issues remain.
- `REV-045-002`: closed for the root `ViewDefinition.where` portion by this
  fix. The nested `Select.where` portion was already closed by SOF-VD-05
  EXPLORER.
- `REV-045-001`: still open and intentionally not fixed in this bounded pass.

## Validation Reviewed

- Fresh probe: `PASS: SOF-VD-09 root where probe`
- Focused parser/where/DuckDB pytest: `285 passed`
- Full ViewDefinition pytest: `960 passed`
- ViewDefinition conformance: `134/134`
- Full conformance: `2822/2822`

## Recommended Fix Order

No further fixes for this pass. Continue with the outer spec compliance
orchestrator to archive SOF-VD-09/SKEPTIC and launch the next requested pass.
