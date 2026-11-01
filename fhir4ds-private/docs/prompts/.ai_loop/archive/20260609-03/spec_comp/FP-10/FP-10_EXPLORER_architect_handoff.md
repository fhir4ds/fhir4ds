# Architect Handoff: FP-10 EXPLORER

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with invariants for FP-10 string-transform parity: native/fallback agreement, UTF-8 code-point handling, exact singleton and arity behavior, regex safety parity, dynamic argument focus, and bundled extension freshness after native changes.

## Structural Audit

The fix is structurally acceptable for this remediation scope. It extends the existing native C++ case-mapping mechanism in `fn_upper`/`fn_lower` without changing parser boundaries, Python fallback behavior, DuckDB UDF signatures, or row-resilience policy. Regression coverage was added at both required levels: native sqllogictest for the C++ extension and Python integration parity for native vs forced fallback.

The underlying design remains a known fragile area: native Unicode case conversion is table-driven rather than delegated to a full Unicode case-folding library. That limitation is already documented in the affected AGENTS files and now has targeted coverage for the new EXPLORER pairs.

## QA Audit

QA was sufficient. The probe was not happy-path only: it covered chained transforms, empty-string vs empty-collection behavior, dynamic arguments/focus, regex ReDoS and malformed-regex boundaries, UTF-8 `length()`/`toChars()`, invalid arity, runtime non-string inputs, and Unicode cases outside prior coverage. No `RETRY_QA` is needed.

## Issues

- `QA-001` MEDIUM SPEC_VIOLATION: RESOLVED.
- New architect issues: none.

## Validation Reviewed

- `.temp/qa/fp10_explorer_probe_after_fix.log`: 47 cases, 0 mismatches, 0 failures.
- Focused pytest: `test_string_transform_parity.py` 4 passed.
- Native FHIRPath unittest: 478 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Bundled extension hash matches the rebuilt extension.

## Recommendation

Clean exit. No remediation retry is needed, and no archive/spec schedule changes were made per user directive.
