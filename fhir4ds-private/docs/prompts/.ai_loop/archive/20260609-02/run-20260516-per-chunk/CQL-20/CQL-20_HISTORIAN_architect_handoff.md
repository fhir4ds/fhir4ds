# Architect Handoff - CQL-20 HISTORIAN Aggregate Functions

Audit result: PASSED.

Golden standard written:
- `.temp/architect/golden_standard.md`
- `fhir4ds-private/docs/prompts/.ai_loop/.temp/architect/golden_standard.md`

Structural assessment:
- The remediation is scoped to the aggregate boundary and preserves the
  translator's AST pipeline. CTE-backed row aggregates remain patient-correlated,
  while structural list-literal query sources are no longer misclassified as
  patient tables.
- The new `CQLListMode` helper is a pure SQL macro, so translated CQL remains
  executable in no-Python/browser-style runtimes. Direct raw DuckDB `Mode(...)`
  row aggregate compatibility remains untouched.
- QA quality was sufficient for HISTORIAN: it tested spec examples, null-only
  boundaries, query-shaped list sources, Quantity aggregates, and all three
  DuckDB execution surfaces. No `RETRY_QA` veto is needed.

Verified issues:
- `QA-001`: VERIFIED.
- `QA-002`: VERIFIED.

Validation:
- Fresh probe passed.
- Aggregate parity and nearby macro/list pytest passed `119 passed`.
- Targeted unit/aggregate rerun passed `6 passed`.
- Full conformance passed `2822/2822`.
- Full pytest passed `7220 passed, 5 skipped, 9 warnings`.
- Targeted diff hygiene and evolution JSON validation passed.

Recommended fix order:
- None. No open CRITICAL/HIGH/MEDIUM issues remain in this inner run.
