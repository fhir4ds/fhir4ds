# Architect Handoff: CQL-18 HISTORIAN

## Audit Result

- Golden standard: `.temp/architect/golden_standard.md`.
- QA audit quality: adequate. The probe used current source, official spec/XML grounding, and fresh forced Python/native/no-Python comparisons; it did not rely on archived workflow output.
- Issue status: `QA-001` verified; no open issues.
- `RETRY_QA`: false.

## Structural Validation

The fix preserves the intended boundary between scalar CQL list values and row-producing retrieve/query collections. List-typed identifiers are now recognized through metadata before interval, SQL subquery, and SQL set-operation fallbacks, while retrieve/query paths remain row-shaped.

The added helper surface keeps CQL list semantics in the DuckDB layer rather than depending on raw DuckDB list equality/set behavior. Runtime list equivalence is available across the same public surfaces used by generated SQL.

## Verification

- Fresh CQL-18 HISTORIAN probe passed.
- Focused list Part 1 parity pytest passed.
- Targeted unit regression for direct `exists` list literal rendering passed.
- Full pytest passed: 7212 passed, 5 skipped, 9 warnings.
- Full conformance passed at 100%: ViewDefinition 134/134, FHIRPath R4 935/935, CQL 1706/1706, DQM 47/47.

## Completion

The active workflow can return to the outer orchestrator with `workflow: null` and `exit_reason: CLEAN`. The outer orchestrator should handle archival.
