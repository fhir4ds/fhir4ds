# Architect Handoff — Iteration 9 (FIX + ARCHITECT → QA)

**Verdict**: PASSED
**Phase**: ARCHITECT → QA (iteration 10)
**Conformance**: 2737/2821 (97.0%) — matches baseline

## Iteration 9 Fix Review

Two fixes from QA9/FIX9 were reviewed against all 12 architecture invariants:

| Fix | Severity | Files Changed | Invariants Checked | Verdict |
|-----|----------|---------------|--------------------|---------|
| QA9-001 Undefined definition fail-fast | MEDIUM | `_core.py` | INV-01,02,03,04,09,12 | ✅ CLEAN |
| QA9-002 Unknown function fail-fast | MEDIUM | `_functions.py` | INV-01,02,03,04,09,12 | ✅ CLEAN |

**All fixes comply.** Both are pure error-detection paths that raise `TranslationError` before any SQL generation. No new SQLRaw, no to_sql() mid-pipeline, no silent fallbacks — these fixes *eliminate* silent fallbacks (INV-03, INV-04).

### QA9-001: Undefined definition references (MEDIUM)
- Error raised at the identifier translator's terminal fallback (line ~847 in `_core.py`).
- Error message includes the unresolved name AND up to 10 available definitions — actionable diagnostics.
- **Guard 1**: Only fires during real library translations (`_definition_names` populated). Bare-context unit tests retain the old `SQLIdentifier` fallback.
- **Guard 2**: Skipped when library has includes — inlined function bodies may reference symbols from included libraries. This is a known limitation (see ARCH note below).
- No SQL types produced on the error path — purely control-flow (INV-01/02).

### QA9-002: Unknown function calls (MEDIUM)
- Error raised at the function translator's terminal fallback (line ~551 in `_functions.py`).
- Same guard pattern as QA9-001.
- Error message includes function name and arity.

### QA9-003/004: DEFERRED
No code changes — assessment only.
- QA9-003: DuckDB validates dates at runtime with clear error messages. Low ROI for translation-time validation.
- QA9-004: Contained resource resolve() is net-new functionality. Current workaround (`contained.where(id='x')`) is adequate.

## Conformance (verified — no regression)

```
ViewDefinition:    134/134   (100.0%)
FHIRPath (R4):     935/935   (100.0%)
CQL:               1626/1706 (95.3%)
DQM (QI Core):     42/46     (91.3%)
─────────────────────────────────────
OVERALL:           2737/2821 (97.0%) — AT BASELINE
```

## CQL Unit Tests

```
4220 passed, 2 failed (pre-existing), 88 skipped, 2 xpassed, 135 warnings
```

Pre-existing failures:
- `test_bp_profile_includes_component_columns` (ARCH-004)
- `test_full_conversion_example` (patient alias naming)

QA9-specific tests: 7/7 passed (`test_undefined_reference_errors.py`).

## 12 Invariants — All Holding

| Invariant | Description | Status |
|-----------|-------------|--------|
| INV-01 | No SQLRaw mid-pipeline | ✅ No new violations |
| INV-02 | No to_sql() mid-pipeline | ✅ No new violations |
| INV-03 | No silent fallbacks | ✅ Both fixes REDUCE silent fallbacks |
| INV-04 | Fail fast on errors | ✅ Both fixes are fail-fast guards |
| INV-05 | Hardcoded resources externalized | ✅ Not affected |
| INV-06 | No new Strategy 2 templates | ✅ Not affected |
| INV-07–08 | Type safety / parameter binding | ✅ Not affected |
| INV-09 | Layer separation | ✅ Errors use TranslationError from errors.py |
| INV-10–11 | CTE naming / dedup | ✅ Not affected |
| INV-12 | Test coverage for fixes | ✅ 7 new tests |

INV-06 (Strategy 2 templates) remains KNOWN_DEBT — no change.

## Architecture Note: Cross-Library Reference Limitation

The QA9-001/002 guards cannot fire when the library has `includes` because inlined function bodies may reference symbols (codes, concepts, definitions) from their origin library that aren't registered in the main translation context. This is a pre-existing architectural limitation in the function inliner — it doesn't propagate included library scopes. The DQM pipeline (42/46 measures) relies on this fallback behavior.

**Recommendation**: Future iteration should improve the function inliner to propagate included library code/concept definitions into the translation context when expanding function bodies. This would allow the QA9-001/002 guards to fire unconditionally.

## Open ARCH Issues (unchanged)

| ID | Severity | Summary |
|----|----------|---------|
| ARCH-001 | MEDIUM | Strategy 2 body_sql templates (KNOWN_DEBT, blocked Task C4) |
| ARCH-002 | MEDIUM | Profile registry silent fallback |
| ARCH-004 | MEDIUM | Stale unit test (test_bp_profile_includes_component_columns) |
| ARCH-009 | MEDIUM | UDF broad exception catches |
| ARCH-005 | LOW | Broad exception in fhirpath_is_valid |
| ARCH-006 | LOW | ViewDef module-level array load |
| ARCH-007 | LOW | ViewDef string-based SQL generation |
| ARCH-008 | LOW | Context profile registry warning fallback |

No new ARCH issues introduced. No CRITICAL or HIGH open findings.

## Cumulative Progress (30 RESOLVED across 9 iterations)

| Iteration | Issues Found | Fixed | Deferred/Intended | Net New |
|-----------|-------------|-------|-------------------|---------|
| 1 | 30 | 5 | 12 | 13 open |
| 2 | 0 | 3 | 0 | 10 open |
| 3 | 0 | 3 | 7 | 0 new |
| 4 | 4 | 4 | 0 | 0 new |
| 5 | 2 | 2 | 0 | 0 new |
| 6 | 1 | 0 | 1 | 0 new |
| 7 | 3 | 3 | 0 | 0 new |
| 8 | 5 | 2 | 3 | 0 new |
| 9 | 4 | 2 | 2 | 0 new |

## Convergence Assessment

The evolution loop continues to converge:
- Iterations 4–9 found only MEDIUM/LOW issues — no HIGH/CRITICAL since iter 8.
- All fixes are clean against invariants. No cascading breakage.
- Conformance holds steady across all 9 iterations.
- The codebase is stable. QA10 should confirm exit readiness.

## Next Phase

QA iteration 10. If QA10 finds no new CRITICAL/HIGH findings, the loop should exit.
