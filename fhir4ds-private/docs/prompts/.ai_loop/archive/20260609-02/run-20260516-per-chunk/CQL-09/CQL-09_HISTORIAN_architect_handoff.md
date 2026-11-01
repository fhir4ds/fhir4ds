# Architect Handoff - CQL-09 HISTORIAN

## Structural Assessment

The final design is structurally sound for this chunk. Comparison operator lowering now keeps domain semantics at the translator boundary instead of falling through to raw SQL equality/comparison. The one recovery issue was architectural: a shared temporal primitive served both public CQL comparison semantics and interval-boundary normalization. That is now split with an explicit opt-in flag, preserving the stricter public comparison contract without breaking measure-facing interval windows.

## QA Audit

QA was sufficient. It used official XML comparison history, direct public SQL probes, translated SQL execution, native-loaded registration, and forced Python fallback registration. It found non-happy-path precision, decimal equivalence, and Quantity duration cases. No `RETRY_QA` is warranted.

## Issue Status

- `QA-CQL09-HISTORIAN-001`: resolved and verified.
- `QA-CQL09-HISTORIAN-002`: resolved and verified.
- `QA-CQL09-HISTORIAN-003`: resolved and verified.

## Validation

- Focused comparison/interval pytest: 5 passed.
- Official comparison operator pytest: 198 passed.
- Native C++ CQL unittest: 628 assertions passed.
- CMS2 DQM forced Python fallback and native-loaded: 36/36 in both modes.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Full `fhir4ds/` pytest: 7162 passed, 5 skipped, 9 warnings.

## Residual Risk

Native C++ `quantity_compare` was updated and the bundled extension was copied. The broader worktree contains unrelated dirty native files from other active workflows; do not infer ownership of those changes from this handoff. The CQL-09 owned native delta is the duration comparison/equivalence logic in `extensions/cql/src/cql/quantity.cpp`.

