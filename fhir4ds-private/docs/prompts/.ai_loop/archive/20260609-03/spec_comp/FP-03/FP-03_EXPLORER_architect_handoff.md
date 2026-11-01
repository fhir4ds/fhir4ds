# Architect Handoff - FP-03 EXPLORER

Golden standard:
- Written to `.temp/architect/golden_standard.md`.
- Key invariants: native and forced Python DuckDB FHIRPath surfaces must stay in parity; criteria functions must bind and restore `$this`/`$index`; `exists(criteria)` must preserve the `where(criteria).exists()` contract; validation helpers must distinguish operators from function calls without weakening unknown-function rejection.

Audit result:
- No new architecture issues found.
- `QA-001` fix is structurally sound: native `evalExists` now validates all criteria results, preserves public row resilience through typed errors, and restores scope after normal and exceptional exits.
- `QA-002` fix is structurally sound: fallback unknown-function detection now uses token context for operator keywords and keeps actual unknown calls invalid.
- QA quality was sufficient for EXPLORER: the probe targeted chained/pathological §5.1 behavior, native-vs-forced-fallback parity, criteria lambdas, empty propagation, and equality/set boundaries. No `RETRY_QA` veto.

Issue count:
- MEDIUM resolved: 2
- Open CRITICAL/HIGH/MEDIUM: 0

Validation reviewed:
- Full conformance summary in `validation_summary.log`: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Recommended next action:
- Clean exit for this inner loop.
