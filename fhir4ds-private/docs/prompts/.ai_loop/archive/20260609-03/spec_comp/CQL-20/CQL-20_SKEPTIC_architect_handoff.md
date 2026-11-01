# Architect Handoff: CQL-20 SKEPTIC

Structural result: passed. No new architectural findings were opened and no
`RETRY_QA` flag is needed.

The aggregate fixes are aligned with the golden standard in
`.temp/architect/golden_standard.md`: CQL signature validation now happens at
the AST/type boundary for statically known list operands, public SQL macros
guard direct numeric/statistical list inputs, query-produced scalar rows are
folded to list values for `GeometricMean`, and DuckDB row aggregate names such
as `Count`, `Sum`, `Avg`, `Min`, and `Max` remain unshadowed so
`COUNT(DISTINCT ...)`, `FILTER`, and row aggregate syntax still work.

Issue disposition: `QA-001` and `QA-002` are verified. Recommended fix order:
none for this pass; proceed to the next CQL-20 personality.
