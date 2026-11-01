# Architect Handoff - CQL-08 EXPLORER

Phase: ARCHITECT

## Structural Health

The remediation is architecturally sound. Both fixes stay inside the CQL translator boundary, preserve the existing DuckDB helper/macro surface, and do not introduce resource-specific, measure-specific, or implementation-guide-specific logic. The main subtlety was preserving two invariants at once: static non-Boolean `IsTrue`/`IsFalse` inputs must not use SQL truthiness, while dynamic FHIR Boolean fields must still be extracted through `fhirpath_bool` before predicate evaluation.

## QA Assessment

QA was sufficient for the EXPLORER role. It tested mixed static operands, invalid signatures, direct public DuckDB helper calls, native-loaded versus forced Python fallback connections, and the remediation added the missing population-SQL dynamic Boolean regression after conformance exposed that edge. No `RETRY_QA` requested.

## Issue Status

- `QA-001`: VERIFIED. Infix and direct `IsTrue`/`IsFalse` now use Boolean-only helper semantics with Boolean-context operand translation.
- `QA-002`: VERIFIED. Scalar `Coalesce` arity is validated against the CQL signatures; list overloads remain valid.

## Validation

- Focused nullological parity pytest: `6 passed`
- Adjacent CQL pytest subset: `162 passed`
- Full conformance: ViewDefinition `134/134`, FHIRPath R4 `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`
- Full pytest: `7160 passed, 5 skipped, 9 warnings`

## Recommended Fix Order

No further fixes are required for this personality run.
