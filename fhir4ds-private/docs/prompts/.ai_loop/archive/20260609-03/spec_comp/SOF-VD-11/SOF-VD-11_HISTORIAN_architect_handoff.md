# Architect Handoff: SOF-VD-11/HISTORIAN

Golden standard written to `.ai_loop/.temp/architect/golden_standard.md`.

Structural assessment:
- The fix is appropriately narrow and preserves the intended architecture: ViewDefinition SQL generation still delegates FHIRPath evaluation to DuckDB UDFs, while the generator owns SQL result typing for declared ViewDefinition columns.
- `SOF-VD-11-HISTORIAN-001` was a legitimate boundary issue, not a new abstraction need. The `%rowIndex` direct fast path was the only path bypassing the existing declared primitive cast table.
- Native C++ and forced Python fallback behavior remain aligned because the change is in generated SQL around the shared `%rowIndex` SQL expression, not in backend-specific FHIRPath evaluation.
- QA was sufficient for HISTORIAN scope: it covered official spec_tests, Patient/Observation examples, address unrolling, filters, keys, boundary functions, type coercion, root `where`, and backend parity. No `RETRY_QA` needed.

Issue count:
- 1 MEDIUM SPEC_VIOLATION found and verified.
- 0 open issues remain for this pass.

Validation reviewed:
- Focused regression: 1 passed.
- Fresh HISTORIAN probe: official native/fallback backend-runs 268/268 and focused examples passed.
- ViewDefinition tests: 977 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Recommended fix order:
- None. This bounded pass is complete and clean.
