# Architect Handoff: SOF-VD-08 EXPLORER

## Structural Health
- No new architectural findings.
- QA was sufficient for this EXPLORER pass: it covered duplicate preservation, schema mismatch rejection, nested union recursion, branch/parent `where` scope, `repeat` interaction, and normal C++ registration versus forced Python fallback parity.
- No `RETRY_QA` needed.

## Golden Standard
- Wrote `.temp/architect/golden_standard.md` with unionAll invariants for rowset composition, duplicate preservation, schema compatibility, iterator/filter scope, native/fallback parity, and legacy helper API alignment.

## Resolved Issue Summary
- `QA-001` MEDIUM RESOLVED: `UnionGenerator.validate_union_columns()` used name-only validation. It now compares the shared effective branch schema `(name, type, collection)` used by the executable union paths.

## Files Changed In This Inner Workflow
- `fhir4ds/viewdef/union.py`
- `fhir4ds/viewdef/tests/unit/test_union.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd_08_explorer_probe.py`
- `.temp/architect/golden_standard.md`
- `.ai_loop` state, handoffs, archive log, and global knowledge files

## Validation Reviewed
- Fresh QA probe: passed, including normal C++ registration and forced Python fallback comparisons.
- Focused unit/integration tests: `25 passed` for `test_union.py`; focused union/generator subset `7 passed`.
- ViewDefinition conformance: `134/134`.
- ViewDefinition pytest: `854 passed`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.
- Full package pytest: `7393 passed, 5 skipped, 9 warnings`.

## Recommended Fix Order
- None. All SOF-VD-08 EXPLORER issues are terminal.
