# Architect Handoff: SOF-VD-08 EXPLORER

Architectural outcome: PASS. The unionAll implementation continues to satisfy
the expected rowset abstraction: parser and direct dataclass guardrails reject
malformed branch structures, effective schemas include recursive nested select
and union output, sibling/parent composition is handled through ordinary select
rowset expansion, and execution stays aligned across native DuckDB FHIRPath and
forced Python fallback.

Golden standard written to `.temp/architect/golden_standard.md` with 12
falsifiable invariants for `select.unionAll`.

QA audit: sufficient. The fresh EXPLORER probe covered malformed parser
boundaries, direct dataclass mutation/serialization, duplicate preservation,
root/branch filter scope, `forEachOrNull`, nested `unionAll`, `repeat`, native
registration, and forced Python fallback. No `RETRY_QA` flag is warranted.

Issue count by category:

| Category | Count |
| --- | ---: |
| SPEC_VIOLATION | 0 |
| API_CONTRACT | 0 |
| DATA_HANDLING | 0 |
| REGRESSION_RISK | 0 |

Recommended fix order: none.

Validation:
- Fresh probe: PASS.
- Focused pytest: `82 passed, 258 deselected`.
- ViewDefinition conformance: `134/134`.
- Full conformance: `2822/2822`.
