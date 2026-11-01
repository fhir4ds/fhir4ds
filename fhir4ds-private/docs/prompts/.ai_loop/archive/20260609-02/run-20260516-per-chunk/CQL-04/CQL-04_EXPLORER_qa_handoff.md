# QA Handoff - CQL-04 EXPLORER

Scope: fresh EXPLORER audit for CQL logical operators `And`, `Implies`, `Not`, `Or`, and `Xor`. I did not inspect archived `spec_comp/**` workflow outputs.

Spec basis: CQL reference logical operators require Boolean operands and define three-valued Boolean semantics; the CQL developer guide precedence table places `and` above `or`/`xor`, and `implies` below disjunction.

Probes run:
- Native-loaded versus forced Python fallback DuckDB truth-table parity for existing `And`/`Or`/`Xor`/`Implies`/`logicalImplies`/`Not`.
- Translated null-heavy chains, parenthesized overrides, `not` precedence, temporal precision adjacent to logic, and query `let`/`where`/`return` population SQL.
- Invalid static operands: `1 and true`, `'x' or false`, `true xor 1`, `1 implies false`, `not 1`, and `{ true, false } and true`.

Finding:
- `QA-001` MEDIUM SPEC_VIOLATION: static non-Boolean operands were translated into DuckDB SQL and sometimes silently coerced, e.g. `1 and true -> SELECT 1 AND TRUE -> true`, `not 1 -> false`, and `true xor 1 -> false`. Expected: translator rejects statically known non-Boolean logical operands before SQL execution.
